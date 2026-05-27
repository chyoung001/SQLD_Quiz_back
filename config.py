from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    db_name: str = "sqld_quiz"
    # 쉼표 구분 문자열로 환경변수 주입
    # 예) CORS_ORIGINS=https://sqld.vercel.app,http://localhost:5173
    cors_origins: str = "http://localhost:5173"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    # 관리자 엔드포인트(/api/admin/*) 보호용 토큰. 미설정 시 admin API 비활성화
    admin_token: str = ""
    # LLM 생성 엔드포인트 IP당 분당 최대 호출 수
    llm_rate_limit_per_minute: int = 3

    @property
    def cors_origins_list(self) -> list[str]:
        """쉼표로 구분된 문자열을 리스트로 변환"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env"}


settings = Settings()
