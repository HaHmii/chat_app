from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str
    openai_model: str
    openai_summary_model: str # cheap model for history summarization

    llamacloud_api_key: str
    llamacloud_index_id: str

    database_url: str

    rc_url: str
    rc_bot_user_id: str
    rc_auth_token: str
    rc_webhook_url: str

    web_service_url: str
    internal_api_key: str = "ai-internal-key-change-me"

    rc_support_channel: str = ""
    rc_support_department_id: str = ""
    rc_livechat_secret: str

    ai_mode: str
    session_timeout_hours: int = 24
    memory_window_size: int = 20


settings = Settings()
