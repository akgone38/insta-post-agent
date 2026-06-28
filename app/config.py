"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """All configuration for the Instagram posting agent."""

    # Telegram
    telegram_bot_token: str

    # Hugging Face
    huggingface_api_token: str
    huggingface_api_base: str = "https://router.huggingface.co/v1"
    huggingface_vision_models: str = "Qwen/Qwen3-VL-8B-Instruct,CohereLabs/aya-vision-32b"

    # Instagram Graph API
    instagram_account_id: str
    instagram_access_token: str

    # Facebook Page Settings
    facebook_page_id: str
    facebook_page_access_token: str

    # Server
    webhook_base_url: str

    # Instagram API version
    instagram_api_version: str = "v22.0"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",  # Ignores extra fields in env file
    }

    @property
    def telegram_webhook_url(self) -> str:
        """Full webhook URL for Telegram to call."""
        return f"{self.webhook_base_url}/webhook/telegram"

    @property
    def image_serve_base_url(self) -> str:
        """Base URL for serving uploaded images publicly."""
        return f"{self.webhook_base_url}/images"

    @property
    def vision_models_list(self) -> list[str]:
        """Convert comma-separated model names into a list."""
        return [m.strip() for m in self.huggingface_vision_models.split(",") if m.strip()]


# Singleton
settings = Settings()
