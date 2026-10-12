"""LLM error classification, redaction and retry policy. Pure Python: no model client, no network, no LangChain.

Used by the agent (nidaan.graph), the one-shot baseline (through nidaan.graph.retry_delay_s) and the dashboard
(to explain a stopped run). The only retry layer is the caller's loop: provider SDK retries stay disabled
(nidaan.llm sets max_retries=0), so retries are never multiplied across layers.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import asdict, dataclass

import config

# ---- redaction -----------------------------------------------------------------------------------------
_SECRET_RES = (
    (re.compile(r"(gsk_|AIza|sk-|AQ\.)[A-Za-z0-9_\-.]{6,}"), "<redacted-key>"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_\-.=]+"), r"\1<redacted>"),
    (re.compile(r"org_[A-Za-z0-9]+"), "org_<redacted>"),
    (re.compile(r"req_[A-Za-z0-9]+"), "req_<redacted>"),
)


def redact(msg: str) -> str:
    """Remove credentials and account/request identifiers that provider error messages may contain."""
    for rx, repl in _SECRET_RES:
        msg = rx.sub(repl, msg)
    return msg


# ---- provider retry guidance -----------------------------------------------------------------------------
_GEMINI_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?([\d.]+)s|retry in ([\d.]+)s")
# Groq: "Please try again in 7.5s" / "450ms" / "1m2.5s" / "2h3m4s"
_GROQ_DELAY_RE = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)(ms|s))?")
# Groq: "on tokens per minute (TPM): Limit 8000, Used 7758, Requested 2191."
_GROQ_LIMIT_RE = re.compile(r"on (tokens|requests) per (minute|day) \((\w+)\): Limit (\d+), Used (\d+), Requested (\d+)")


def provider_retry_after_s(msg: str) -> float | None:
    """The wait the provider asked for, in seconds, or None if the message gives none."""
    m = _GEMINI_DELAY_RE.search(msg)
    if m:
        return float(m.group(1) or m.group(2))
    m = _GROQ_DELAY_RE.search(msg)
    if m and any(m.groups()):
        h, mins, num, unit = m.groups()
        return int(h or 0) * 3600 + int(mins or 0) * 60 + float(num or 0) / (1000 if unit == "ms" else 1)
    return None


# ---- classification --------------------------------------------------------------------------------------
RATE_LIMIT = "rate_limit"            # per-minute limit: clears within seconds, worth waiting for
QUOTA_EXHAUSTED = "quota_exhausted"  # per-day limit: will not clear within a run
TRANSIENT = "transient"              # 5xx / unavailable / timeout
FATAL = "fatal"                      # anything else (bad request, auth, ...): retrying cannot help

_TRANSIENT_MARKERS = ("Error code: 500", "Error code: 502", "Error code: 503", "503 ", "UNAVAILABLE", "DEADLINE",
                      "timed out", "timeout", "Timeout", "APIConnectionError", "InternalServerError")


@dataclass(frozen=True)
class LLMError:
    kind: str
    message: str                  # redacted provider message (with exception type)
    retry_after_s: float | None   # provider guidance, if any
    scope: str | None = None      # e.g. "tokens per minute"
    limit: int | None = None
    used: int | None = None
    requested: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def classify(raw: str) -> LLMError:
    """Classify a provider error message (redacted before anything else is done with it)."""
    msg = redact(raw)
    after = provider_retry_after_s(msg)
    scope = limit = used = requested = None
    m = _GROQ_LIMIT_RE.search(msg)
    if m:
        what, per, _abbr, lim, use, req = m.groups()
        scope, limit, used, requested = f"{what} per {per}", int(lim), int(use), int(req)
    is_rate = ("429" in msg or "RateLimit" in msg or "RESOURCE_EXHAUSTED" in msg or "rate limit" in msg.lower()
               or "Rate limit" in msg)
    if is_rate:
        daily = (scope or "").endswith("per day") or "PerDay" in msg or "per day" in msg.lower()
        too_long = after is not None and after > config.LLM_MAX_RETRY_DELAY_S
        kind = QUOTA_EXHAUSTED if (daily or too_long) else RATE_LIMIT
    elif any(t in msg for t in _TRANSIENT_MARKERS):
        kind = TRANSIENT
    else:
        kind = FATAL
    return LLMError(kind, msg, after, scope, limit, used, requested)


# ---- retry policy ----------------------------------------------------------------------------------------
def backoff_s(attempt: int, rng=random.random) -> float:
    """Bounded exponential backoff with jitter: base * 2**attempt, capped, scaled into [50%, 100%]."""
    cap = min(config.LLM_BACKOFF_MAX_S, config.LLM_BACKOFF_BASE_S * 2 ** attempt)
    return cap * (0.5 + 0.5 * rng())


def next_delay_s(err: LLMError, rate_retries: int, other_retries: int, waited_s: float,
                 rng=random.random) -> float | None:
    """Seconds to wait before the next attempt, or None to stop.
    rate_retries / other_retries: retries already made for this call, by kind. waited_s: total already waited.
    Provider guidance is honoured (plus a small margin); without it, jittered exponential backoff is used.
    Every path is bounded by a retry count and by a total-wait budget, so the loop always ends."""
    if err.kind in (FATAL, QUOTA_EXHAUSTED):
        return None
    if err.kind == RATE_LIMIT:
        if rate_retries >= config.LLM_RATE_LIMIT_RETRIES:
            return None
        delay = (err.retry_after_s + config.LLM_RETRY_MARGIN_S if err.retry_after_s is not None
                 else backoff_s(rate_retries, rng))
    else:  # TRANSIENT
        if other_retries >= config.LLM_RETRIES:
            return None
        delay = (err.retry_after_s + config.LLM_RETRY_MARGIN_S if err.retry_after_s is not None
                 else backoff_s(other_retries, rng))
    if delay > config.LLM_MAX_RETRY_DELAY_S or waited_s + delay > config.LLM_MAX_TOTAL_RETRY_WAIT_S:
        return None
    return delay


# ---- proactive pacing for a tokens-per-minute limit ------------------------------------------------------
class TokenPacer:
    """Client-side model of the provider's tokens-per-minute limit as a token bucket that drains continuously at
    limit/60 tokens per second. This matches Groq's own retry guidance: for "Limit 8000, Used 7758, Requested 2191"
    it asks for (7758 + 2191 - 8000) / (8000/60) = 14.6 s, and for "Used 5641, Requested 2522" 1.2 s.

    Before a call, wait_s(estimate) says how long to wait so that current usage plus the estimated request stays
    under `headroom` x limit. It only ever delays a call; it never changes, drops or truncates anything sent.
    The provider remains the authority: a 429 is still handled by the retry policy."""

    def __init__(self, tpm_limit: int | None, headroom: float = 0.9, clock=time.monotonic):
        self.limit, self.headroom, self.clock = tpm_limit, headroom, clock
        self.rate = tpm_limit / 60.0 if tpm_limit else 0.0
        self._level, self._t = 0.0, None

    def _drain(self) -> None:
        now = self.clock()
        if self._t is not None:
            self._level = max(0.0, self._level - self.rate * (now - self._t))
        self._t = now

    def record(self, tokens: int | None) -> None:
        if self.limit and tokens:
            self._drain()
            self._level += int(tokens)

    def wait_s(self, estimate: int) -> float:
        if not self.limit or self._t is None:
            return 0.0
        self._drain()
        excess = self._level + estimate - self.limit * self.headroom
        return min(max(0.0, excess / self.rate), 60.0)


# ---- user-facing explanation (dashboard) -----------------------------------------------------------------
def explain(err: LLMError) -> dict:
    """Plain-language title, explanation and next step for a stopped run. No secrets: built from a redacted error."""
    if err.kind == RATE_LIMIT:
        scope = err.scope or "per-minute"
        nums = (f" (limit {err.limit:,}, already used {err.used:,}, this request {err.requested:,})"
                if err.limit is not None else "")
        title = "Stopped by the model provider's rate limit"
        text = (f"The provider rejected the request because of its {scope} limit{nums}. Nidaan waited and retried "
                "as far as its retry budget allows, then stopped.")
        hint = (f"The provider suggested retrying after about {err.retry_after_s:.1f} s. " if err.retry_after_s else "")
        action = hint + "Wait a minute before starting another run; the limit is a sliding one-minute window."
    elif err.kind == QUOTA_EXHAUSTED:
        title = "Stopped: the provider's daily quota is used up"
        text = "The provider rejected the request because a per-day limit has been reached."
        action = "Try again after the provider's daily limit resets; waiting minutes will not help."
    elif err.kind == TRANSIENT:
        title = "Stopped: the model provider was unavailable"
        text = "Requests failed with a temporary provider error (for example a timeout or a 5xx response)."
        action = "Try again later."
    else:
        title = "Stopped: the model provider rejected the request"
        text = "The request failed with an error that retrying cannot fix (for example a bad request)."
        action = "See the details below."
    return {"title": title, "text": text, "action": action}
