"""
📄 ARCHIVO: backend/main.py
"""
import logging, os, sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

for _lib in ["sqlalchemy", "sqlalchemy.engine", "sqlalchemy.engine.Engine",
             "sqlalchemy.pool", "sqlalchemy.dialects", "sqlalchemy.orm",
             "watchfiles", "httpcore", "httpx", "chromadb", "groq",
             "asyncio", "uvicorn.access", "uvicorn.error", "uvicorn",
             "multipart", "starlette", "passlib"]:
    logging.getLogger(_lib).setLevel(logging.CRITICAL)
logging.basicConfig(level=logging.CRITICAL)

CYAN="\033[36m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"
GREY="\033[90m"; BOLD="\033[1m"; RESET="\033[0m"

class _Fmt(logging.Formatter):
    _MAP = {logging.DEBUG:(GREY,"·"), logging.INFO:(CYAN,"›"),
            logging.WARNING:(YELLOW,"⚠"), logging.ERROR:(RED,"✗")}
    def format(self, r):
        c, ic = self._MAP.get(r.levelno, (GREY,"·"))
        return f"{c}  {ic}  {r.getMessage()}{RESET}"

_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(_Fmt())
log = logging.getLogger("mall_bot")
log.setLevel(logging.INFO); log.addHandler(_h); log.propagate = False

from config import get_settings
from models.database import create_tables, get_db, SessionLocal
from models import conversation, store, event, user_profile, order, user
from routers import webhook
from routers.api    import router as api_router
from routers.orders import router as orders_router
from routers.auth   import router as auth_router
from services.rag   import load_stores_to_rag
from services.analytics import get_weekly_summary
from services.auth  import create_default_admin

settings = get_settings()

_SKIP = {"/health", "/favicon.ico", "/"}
_SKIP_PFX = ("/_next", "/static", "/docs", "/openapi")
_SC = {2: GREEN, 3: CYAN, 4: YELLOW, 5: RED}

async def _log_req(request: Request, call_next):
    path = request.url.path
    if path in _SKIP or any(path.startswith(p) for p in _SKIP_PFX):
        return await call_next(request)
    resp = await call_next(request)
    sc   = resp.status_code
    col  = _SC.get(sc // 100, GREY)
    qs   = f"?{request.url.query}" if request.url.query else ""
    print(f"  {col}{sc}{RESET}  {GREY}{request.method:<6}{RESET}  {path}{qs}")
    return resp

@asynccontextmanager
async def lifespan(app: FastAPI):
    sep = f"{GREY}  {'─'*46}{RESET}"
    print(f"\n{BOLD}{CYAN}  🛍️  {settings.APP_NAME}{RESET}")
    print(sep)
    create_tables()
    print(f"{GREEN}  ✓  Base de datos lista{RESET}")
    db = SessionLocal()
    try:
        create_default_admin(db)
        load_stores_to_rag(db)
        print(f"{GREEN}  ✓  RAG cargado{RESET}")
    except Exception as e:
        print(f"{YELLOW}  ⚠  RAG no cargó: {e}{RESET}")
    finally:
        db.close()
    print(sep)
    print(f"  {CYAN}🌐  Backend{RESET}  →  http://localhost:8000")
    print(f"  {CYAN}📊  Panel{RESET}    →  http://localhost:3000")
    print(f"  {CYAN}📖  Docs{RESET}     →  http://localhost:8000/docs")
    print(f"{sep}\n")
    yield
    print(f"\n{GREY}  ─  Servidor detenido{RESET}\n")

app = FastAPI(title=settings.APP_NAME, version="3.0.0", lifespan=lifespan,
              docs_url="/docs" if settings.DEBUG else None)

app.middleware("http")(_log_req)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(webhook.router)
app.include_router(api_router)
app.include_router(orders_router)
app.include_router(auth_router)

static_path = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def root(): return {"status": "online", "app": settings.APP_NAME}

@app.get("/chat")
async def chat_ui(): return FileResponse(os.path.join(static_path, "chat.html"))

@app.get("/health")
async def health(): return {"status": "healthy"}

@app.get("/analytics/summary")
async def analytics_summary(db: Session = Depends(get_db)):
    return get_weekly_summary(db)

@app.get("/analytics/heatmap")
async def analytics_heatmap(days: int = 7, db: Session = Depends(get_db)):
    from services.analytics import get_hourly_heatmap
    return get_hourly_heatmap(db, days=days)

@app.get("/analytics/top-stores")
async def analytics_top_stores(days: int = 7, db: Session = Depends(get_db)):
    from services.analytics import get_top_stores
    return get_top_stores(db, days=days)

@app.get("/analytics/top-words")
async def analytics_top_words(days: int = 7, db: Session = Depends(get_db)):
    from services.analytics import get_top_words
    return get_top_words(db, days=days)

@app.get("/analytics/categories")
async def analytics_categories(days: int = 7, db: Session = Depends(get_db)):
    from services.analytics import get_top_categories
    return get_top_categories(db, days=days)

@app.post("/run-profiling")
async def run_profiling(db: Session = Depends(get_db)):
    from services.profiling import run_profiling_job
    count = await run_profiling_job(db)
    return {"ok": True, "profiles_updated": count}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000,
                reload=True, log_level="critical", access_log=False)