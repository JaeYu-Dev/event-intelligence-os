from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Event Intelligence OS API"
    debug: bool = True

    database_url: str = "postgresql://eios:eios@localhost:5432/eios"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "eios"
    s3_secret_key: str = "eioseios"
    s3_bucket: str = "eios-raw"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    sec_user_agent: str = "EventIntelligenceOS contact@example.com"

    enable_live_trading: bool = False
    allow_autonomous_orders: bool = False
    default_mode: str = "paper"
    min_evidence_grade_for_trade: str = "E2"
    require_human_approval: bool = True
    max_llm_calls_per_thesis_per_day: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
