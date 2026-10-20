"""FastAPI application entry point.

Run with:  uvicorn backend.main:app --reload
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.api.books import router as books_router
from backend.config import settings
from backend.database import create_tables, engine
from backend.services.book_service import NotFoundError, WorkflowError, book_service
from backend.services.llm_service import LLMError, llm_service

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("backend")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()  # idempotent: creates only missing tables/columns
    if interrupted := book_service.recover_interrupted_jobs():
        logger.warning("Marked %d interrupted chapter job(s) as failed; they can be retried", interrupted)
    logger.info("%s v%s started (LLM provider: %s)", settings.APP_NAME, settings.APP_VERSION,
                llm_service.active_provider())
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Generate books with an LLM using a human-in-the-loop workflow: "
        "**outline → chapters → final review → .docx compilation**. "
        "Every stage waits for editor approval before continuing."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------- error handling
@app.exception_handler(NotFoundError)
async def _not_found(_: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(WorkflowError)
async def _workflow_error(_: Request, exc: WorkflowError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(LLMError)
async def _llm_error(_: Request, exc: LLMError):
    logger.error("LLM failure: %s", exc)
    return JSONResponse(status_code=503, content={"detail": f"LLM service unavailable. {exc}"})


# ------------------------------------------------------------------ routes
app.include_router(books_router)


@app.get("/health", tags=["System"], summary="Health check")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001
        logger.error("Database health check failed: %s", exc)
        database = "unavailable"
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": settings.APP_VERSION,
        "database": database,
        "llm_provider": llm_service.active_provider(),
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
