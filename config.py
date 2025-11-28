import os
from dataclasses import dataclass


@dataclass
class Settings:
    # SiliconFlow API with DeepSeek model
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
    llm_api_key: str = os.environ.get("LLM_API_KEY", "sk-iqfgbworfeelwmdjfmiclxtwfoyfhvgpodsthgcbcancyjnt")
    llm_model: str = os.environ.get("LLM_MODEL", "Pro/deepseek-ai/DeepSeek-R1")
    request_timeout: int = int(os.environ.get("LLM_TIMEOUT", "120"))


settings = Settings()


__all__ = ["settings", "Settings"]
