"""TrustDocs FastAPI application factory.

Assembles all routers, database lifecycle, frontend serving,
and WebSocket endpoints into a single FastAPI app.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from trustdocs.config import config
from trustdocs import database as db

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App startup/shutdown lifecycle."""
    # Try to connect to PostgreSQL, fall back to in-memory
    await db.init_db(config.db_dsn)
    Path(config.storage_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"TrustDocs started on Node {config.node_id}")
    yield
    await db.close_db()
    logger.info("TrustDocs shut down")


app = FastAPI(
    title="TrustDocs",
    description="Secure P2P Document Collaboration — Powered by TrustFlow",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ─────────────────────────────────────────────────────────

from trustdocs.auth.routes import router as auth_router
from trustdocs.documents.routes import router as documents_router
from trustdocs.comments import router as comments_router
from trustdocs.chat import router as chat_router, websocket_document
from trustdocs.admin import router as admin_router, admin_websocket

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(comments_router)
app.include_router(chat_router)
app.include_router(admin_router)

# ── WebSocket endpoints ──────────────────────────────────────────────────────

@app.websocket("/ws/documents/{doc_id}")
async def ws_document(ws: WebSocket, doc_id: str):
    await websocket_document(ws, doc_id)


@app.websocket("/ws/admin")
async def ws_admin(ws: WebSocket):
    await admin_websocket(ws)


# ── Frontend (React/Vite) ────────────────────────────────────────────────────

_frontend_dir = Path(__file__).resolve().parent.parent / "trustdocs-ui" / "dist"

if _frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dir / "assets")), name="assets")

@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend(full_path: str):
    """Serve the Vite React frontend. Falls back to index.html for client-side routing."""
    # Whitelist API endpoints to avoid swallowing 404s
    if full_path.startswith("api/") or full_path.startswith("auth/") or full_path.startswith("documents/") or full_path.startswith("admin/") or full_path.startswith("ws/"):
        return HTMLResponse("Not Found", status_code=404)
        
    index_file = _frontend_dir / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return HTMLResponse(
        "<h1>TrustDocs UI Not Found</h1><p>Run <code>npm run build</code> in trustdocs-ui directory first.</p>"
    )
