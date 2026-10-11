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

# Transient-error retry with exponential backoff (seconds: 2, 4, 8, 16)
LLM_RETRIES = 4
LLM_BACKOFF_BASE_S = 2
