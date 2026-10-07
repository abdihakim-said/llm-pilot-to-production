from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything that defines a release comes from here (image + env)."""

    model_config = SettingsConfigDict(env_prefix="ASSISTANT_")

    release: str = "dev"
    prompt_version: str = "v1"
    model_url: str = "http://model-server-v1.llm:8000"
    model_name: str = "qwen2.5-0.5b-instruct"
    model_timeout_s: float = 60.0
    max_tokens: int = 300
    temperature: float = 0.1

    prompts_dir: Path = Path(__file__).parent.parent / "prompts"
    policy_dir: Path = Path(__file__).parent.parent / "policy"
    podinfo_dir: Path = Path("/etc/podinfo")

    max_input_chars: int = 2000
    rate_limit_per_minute: int = 20
    retrieval_k: int = 3

    mlflow_tracking_uri: str = ""
    mlflow_experiment: str = "lending-assistant"

    @cached_property
    def system_prompt(self) -> str:
        return (self.prompts_dir / f"system-{self.prompt_version}.md").read_text().strip()


settings = Settings()
