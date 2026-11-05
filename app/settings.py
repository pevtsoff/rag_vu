from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    upload_path: str = "./media/documents"
    rag_vu_api_base_url: str = "http://localhost:8080"
    mcp_transport: str = "http"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001


settings = Settings()
