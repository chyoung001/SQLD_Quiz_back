from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    db_name: str = "sqld_quiz"
    # 쉼표 구분 문자열로 환경변수 주입 가능
    # 예) CORS_ORIGINS=https://sqld.vercel.app,http://localhost:5173
    cors_origins: list[str] = ["http://localhost:5173"]
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """문자열로 들어온 경우 쉼표로 분리"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = {"env_file": ".env"}


settings = Settings()
