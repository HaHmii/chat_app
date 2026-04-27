from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    rc_base_url: str = "http://localhost:3000"
    rc_user_id: str
    rc_auth_token: str
    rc_bot_username: str = "bot.ai"
    rc_webhook_url: str

settings = Settings()
