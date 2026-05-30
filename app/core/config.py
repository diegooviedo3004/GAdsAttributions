from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Google OAuth (shared by Google Ads)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_developer_token: str = ""

    # Google Ads defaults (can be overridden per request)
    google_ads_mcc_id: str = "7436168443"
    google_ads_customer_id: str = "7217144043"
    google_ads_conversion_action_callrail: str = ""
    google_ads_conversion_action_call: str = "customers/7436168443/conversionActions/6895663361"

    # App
    log_level: str = "INFO"
    environment: str = "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
