from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./suitespot.db"
    SECRET_KEY: str = "change-me-to-a-random-secret"
    ENVIRONMENT: str = "development"
    APP_VERSION: str = "0.1.0"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
