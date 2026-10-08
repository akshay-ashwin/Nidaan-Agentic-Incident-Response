"""Single source of model configuration."""
MODEL_NAME = "gemini-3.8-flash"  # confirmed by real call in Phase 0; see PROGRESS.md
TEMPERATURE = 0
# SPEC §4 asks for minimal thinking. gemini-3.8-flash rejects "minimal" (400); "low" is the
# lowest level it accepts (0 reasoning tokens observed on a trivial prompt).
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
