from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # WhatsApp
    WHATSAPP_TOKEN: str = "PENDIENTE"
    WHATSAPP_PHONE_ID: str = "PENDIENTE"
    VERIFY_TOKEN: str = "mall_puente_2026"

    # Groq — modelo actualizado (agosto 2026: llama-3.3-70b-versatile fue
    # descontinuado por Groq el 17/06/2026, migrado al reemplazo oficial)
    GROQ_API_KEY: str = "PENDIENTE"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_VISION_MODEL: str = "qwen/qwen3.6-27b"  # para el bot que ve fotos

    # Base de datos
    DATABASE_URL: str = "sqlite:///./mall_bot_dev.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # App
    APP_NAME: str = "Chatbot Mall El Puente"
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()