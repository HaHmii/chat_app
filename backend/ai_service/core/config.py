from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str
    openai_model: str = "gpt-4o-mini"

    llamacloud_api_key: str
    llamacloud_index_id: str

    database_url: str

    rocketchat_url: str
    rocketchat_bot_user_id: str
    rocketchat_auth_token: str
    rocketchat_webhook_url: str

    web_service_url: str

    ai_mode: str = "router"
    session_timeout_hours: int = 24
    memory_window_size: int = 20


settings = Settings()
