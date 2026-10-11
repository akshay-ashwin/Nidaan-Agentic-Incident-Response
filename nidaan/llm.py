"""Chat model factory. The provider and model are chosen in config.py; keys come from the environment."""
from __future__ import annotations

import config


def make_chat_model(provider: str | None = None, model: str | None = None):
    """Unbound chat model with SDK retries disabled (callers retry and log each attempt)."""
    provider = provider or config.PROVIDER
    if provider not in config.MODELS:
        raise ValueError(f"unknown provider {provider!r}")
    model = model or config.MODELS[provider]
    if provider == "groq":
        from langchain_groq import ChatGroq
        # include_reasoning=False: the model's reasoning text is not returned, so it cannot be stored.
        return ChatGroq(model=model, temperature=config.TEMPERATURE,
                        reasoning_effort=config.THINKING_LEVEL, max_retries=0,
                        timeout=config.LLM_TIMEOUT_S, model_kwargs={"include_reasoning": False})
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, temperature=config.TEMPERATURE,
                                      thinking_level=config.THINKING_LEVEL, max_retries=0,
                                      timeout=config.LLM_TIMEOUT_S)
    raise ValueError(f"no factory for provider {provider!r}")
