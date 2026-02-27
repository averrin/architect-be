from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # Firebase
    FIREBASE_SERVICE_ACCOUNT_JSON: str | None = None
    FIREBASE_PROJECT_ID: str | None = None

    # Scheduling
    WEATHER_INTERVAL_MINUTES: int = 60
    NEWS_INTERVAL_MINUTES: int = 30
    BUXFER_INTERVAL_MINUTES: int = 60

    GITHUB_WATCHER_INTERVAL_SECONDS: int = 10
    GITHUB_WATCHER_SLOW_INTERVAL_MINUTES: int = 2

    JULES_INTERVAL_SECONDS: int = 10
    JULES_SLOW_INTERVAL_MINUTES: int = 5

    DASHBOARD_DISCOVERY_INTERVAL_MINUTES: int = 5
    DASHBOARD_STATUS_INTERVAL_SECONDS: int = 10

    FCM_HEARTBEAT_INTERVAL_MINUTES: int = 1
    FORECAST_HOUR: int = 7
    MODELS_SYNC_INTERVAL_HOURS: int = 24
    COMMAND_POLL_INTERVAL_SECONDS: int = 5

    # Job Control Flags
    ENABLE_WEATHER_JOB: bool = False
    ENABLE_NEWS_JOB: bool = False
    ENABLE_BUXFER_JOB: bool = False
    ENABLE_GITHUB_JOB: bool = False
    ENABLE_JULES_JOB: bool = False
    ENABLE_FORECAST_JOB: bool = False
    ENABLE_MODELS_SYNC_JOB: bool = False
    ENABLE_FCM_HEARTBEAT_JOB: bool = True

    # Optional: Default API keys (fallback if user doesn't provide)
    DEFAULT_GEMINI_API_KEY: str | None = None
    DEFAULT_NEWS_API_KEY: str | None = None

    # Google OAuth
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "debug"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

@lru_cache
def get_settings():
    return Settings()
