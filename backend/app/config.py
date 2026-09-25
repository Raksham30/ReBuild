"""
Central configuration.

Every external service is optional and independently toggled via
its own use_* property. If its env vars are absent, the app falls back
to a local/offline implementation where applicable.

Embeddings run exclusively on Google Gemini API (gemini-embedding-001).
"""
from __future__ import annotations
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # --- Firebase Auth (end-user auth; deliberately not an Azure service) ---
    firebase_service_account_path: str | None = None

    # --- Cosmos DB ---
    cosmos_db_uri: str | None = None
    cosmos_db_key: str | None = None
    cosmos_db_database: str = "ResearchDB"

    # --- Blob Storage ---
    blob_storage_connection_string: str | None = None
    blob_container_name: str = "papers"

    # --- Document Intelligence ---
    document_intelligence_endpoint: str | None = None
    document_intelligence_key: str | None = None

    # --- Azure AI Search ---
    ai_search_url: str | None = None
    ai_search_admin_key: str | None = None
    ai_search_index_name: str = "paper-chunks"

    # --- Azure OpenAI (direct, used for chat completions + extraction) ---
    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    azure_openai_chat_deployment: str | None = None
    azure_openai_api_version: str = "2024-10-21"

    # --- Gemini (sole embedding provider) ---
        # --- Gemini (sole embedding provider) ---
    gemini_api_key: str | None = None
    gemini_embedding_model: str = "models/gemini-embedding-001"
    gemini_embedding_dim: int = 3072
    gemini_chat_model: str = "gemini-flash-latest"

    # --- Azure AI Foundry Agent Service (orchestration) ---
    foundry_project_endpoint: str | None = None   # https://<account>.services.ai.azure.com/api/projects/<project>
    foundry_agent_name: str = "research-assistant-agent"

    # --- Local paths (always used as fallback / cache) ---
    local_data_dir: str = os.path.join(os.path.dirname(__file__), "..", "data")
    local_upload_dir: str = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
    local_index_dir: str = os.path.join(os.path.dirname(__file__), "..", "data", "local_index")
    local_metadata_path: str = os.path.join(os.path.dirname(__file__), "..", "data", "metadata.json")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def use_firebase(self) -> bool:
        return bool(self.firebase_service_account_path)

    @property
    def use_cosmos(self) -> bool:
        return bool(self.cosmos_db_uri and self.cosmos_db_key)

    @property
    def use_blob(self) -> bool:
        return bool(self.blob_storage_connection_string)

    @property
    def use_docint(self) -> bool:
        return bool(self.document_intelligence_endpoint and self.document_intelligence_key)

    @property
    def use_azure_search(self) -> bool:
        return bool(self.ai_search_url and self.ai_search_admin_key)

    @property
    def use_azure_openai(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_key and self.azure_openai_chat_deployment)

    @property
    def use_gemini_embeddings(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def use_foundry_agent(self) -> bool:
        return bool(self.foundry_project_endpoint)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    os.makedirs(s.local_upload_dir, exist_ok=True)
    os.makedirs(s.local_index_dir, exist_ok=True)
    return s
