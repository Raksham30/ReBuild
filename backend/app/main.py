from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api import workspaces, papers, chat, research, flags
from app.config import get_settings
from app.services.generation import LLMUnavailableError

app = FastAPI(title="Research Paper Assistant", version="0.2.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

@app.exception_handler(LLMUnavailableError)
async def llm_unavailable_handler(_: Request, exc: LLMUnavailableError):
    # Quota/overload is an expected condition, not a server bug: return a
    # readable message the frontend can show instead of a 500 traceback.
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


app.include_router(workspaces.router)
app.include_router(papers.router)
app.include_router(chat.router)
app.include_router(research.router)
app.include_router(flags.router)


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "mode": {
            "auth": "firebase" if settings.use_firebase else "dev-mode (insecure, local only)",
            "metadata_db": "cosmos-db" if settings.use_cosmos else "local-json-fallback",
            "file_storage": "blob-storage" if settings.use_blob else "local-disk-fallback",
            "document_intelligence": "azure" if settings.use_docint else "local-fallback",
            "embeddings": "gemini" if settings.use_gemini_embeddings else "NOT CONFIGURED (set GEMINI_API_KEY)",
            "chat_generation": "azure-openai" if settings.use_azure_openai else "NOT CONFIGURED (set AZURE_OPENAI_KEY & AZURE_OPENAI_ENDPOINT)",
            "search_index": "azure" if settings.use_azure_search else "local-fallback",
            "agent_orchestration": "foundry-agent-service" if settings.use_foundry_agent else "azure-openai",
        },
    }
