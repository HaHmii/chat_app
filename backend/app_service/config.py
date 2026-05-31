from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    internal_api_key: str = "ai-internal-key-change-me"
    rc_base_url: str
    rc_bot_username: str
    rc_bot_user_id: str       # bot user ID
    rc_bot_auth_token: str    # bot auth token — dùng để set livechat status
    rc_webhook_url: str
    rc_livechat_department_id: str


settings = Settings()
