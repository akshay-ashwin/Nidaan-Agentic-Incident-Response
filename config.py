"""Single source of model configuration."""
# Provider switch. The API key is read from .env by the provider's own integration
# (GROQ_API_KEY for groq, GOOGLE_API_KEY for gemini); it is never passed or logged here.
PROVIDER = "groq"
MODELS = {
    "groq": "openai/gpt-oss-120b",  # production model with tool use on Groq; see PROGRESS.md
    "gemini": "gemini-3.8-flash",   # Phases 0-2; confirmed by real call in Phase 0
}
MODEL_NAME = MODELS[PROVIDER]
MODEL_ID = f"{PROVIDER}:{MODEL_NAME}"  # provider-qualified name written to the run logs
TEMPERATURE = 0
# SPEC §4 asks for minimal thinking. Gemini: gemini-3.8-flash rejects "minimal" (400); "low" is the
# lowest level it accepts. Groq: sent as reasoning_effort; gpt-oss accepts low/medium/high only.
THINKING_LEVEL = "low"

# SPEC §1 run limits
MAX_LLM_STEPS = 30
MAX_NUDGES = 2
MAX_VERIFIER_RETRIES = 2

LLM_TIMEOUT_S = 60  # per request; a timeout is treated as transient and retried

LLM_MAX_RETRY_DELAY_S = 120  # server-requested delays longer than this are not waited out

# Retry policy (nidaan/llm_errors.py). The application loop is the only retry layer (SDK retries are disabled).
LLM_RETRIES = 4              # transient errors (5xx, timeout): retries per call
LLM_RATE_LIMIT_RETRIES = 8   # per-minute rate limits (HTTP 429): retries per call
LLM_BACKOFF_BASE_S = 2       # exponential backoff with jitter when the provider gives no retry time
LLM_BACKOFF_MAX_S = 30
LLM_RETRY_MARGIN_S = 1       # added to the provider's suggested wait
LLM_MAX_TOTAL_RETRY_WAIT_S = 300  # total waiting per call; past this the run stops (no infinite loop)

# Proactive pacing under the provider's tokens-per-minute limit (None disables). Groq on_demand tier for
# openai/gpt-oss-120b reported "Limit 8000" tokens per minute in its 429 responses (see PROGRESS.md).
LLM_TPM_LIMITS = {"groq": 8000, "gemini": None}
LLM_TPM_LIMIT = LLM_TPM_LIMITS.get(PROVIDER)
