import pytest

import config
from nidaan.graph import redact, retry_delay_s
from nidaan.llm import make_chat_model


def test_model_is_single_nonpreview_model_of_selected_provider():
    assert config.PROVIDER in config.MODELS
    assert config.MODEL_NAME == config.MODELS[config.PROVIDER]
    assert config.MODEL_ID == f"{config.PROVIDER}:{config.MODEL_NAME}"
    assert "preview" not in config.MODEL_NAME
    assert "flash" in config.MODELS["gemini"]


def test_temperature_zero():
    assert config.TEMPERATURE == 0


def test_groq_factory_builds_without_network_and_hides_reasoning(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_dummy_for_offline_test")
    llm = make_chat_model("groq")
    assert type(llm).__name__ == "ChatGroq"
    params = llm._default_params
    assert params["model"] == config.MODELS["groq"]
    assert params["reasoning_effort"] == config.THINKING_LEVEL
    assert params["include_reasoning"] is False
    assert llm.max_retries == 0


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        make_chat_model("nope")


@pytest.mark.parametrize("text,expected", [
    ("Please try again in 7.5s.", 8.5),
    ("Please try again in 450ms.", 1.45),
    ("Please try again in 1m2.5s.", 63.5),
])
def test_groq_retry_delay_parsed(text, expected):
    msg = f"RateLimitError: Error code: 429 - rate_limit_exceeded. {text}"
    assert retry_delay_s(msg, 0) == pytest.approx(expected)


def test_groq_long_delay_not_waited_out():
    assert retry_delay_s("Error code: 429 - tokens per day (TPD). Please try again in 2h3m4s.", 0) is None


def test_gemini_retry_delay_unchanged():
    assert retry_delay_s("429 RESOURCE_EXHAUSTED {'retryDelay': '35s'}", 0) == 36
    assert retry_delay_s("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProject retryDelay: 9s", 0) is None


def test_org_id_redacted():
    assert "org_01abcDEF" not in redact("Rate limit reached in organization `org_01abcDEF`")
