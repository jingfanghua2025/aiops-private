import os
import sys

from dotenv import load_dotenv


def _load_env() -> None:
    """
    兼容多种私有化部署路径：
    - 优先使用 AIOPS_ENV_FILE 指定的 .env
    - 否则依次尝试：/data/aiops/.env、/opt/aiops/.env、项目根目录下 .env
    """
    candidates: list[str] = []
    env_file = os.getenv("AIOPS_ENV_FILE")
    if env_file:
        candidates.append(env_file)
    candidates.extend(
        [
            "/data/aiops/.env",
            "/opt/aiops/.env",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        ]
    )
    for p in candidates:
        try:
            if p and os.path.exists(p):
                load_dotenv(dotenv_path=p)
                return
        except Exception:
            # 环境加载失败不应阻断启动，交由后续配置校验处理
            continue


# 注意：必须在导入任何 app.api.*（会触发服务初始化）之前加载 .env
_load_env()

from app.models.user import init_db

# 初始化数据库（可能依赖 .env 中的数据库连接串）
init_db()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.api.agent_endpoints import router as agent_router
from app.api.auth_endpoints import router as auth_router
from app.api.cloud_endpoints import router as cloud_router
from app.api.endpoints import router as api_router
from app.api.streaming_endpoints import router as streaming_router
from app.api.system_endpoints import router as system_router

app = FastAPI(title="AIOps+ Real AI Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(api_router, prefix="/api/v1", tags=["Ops"])
app.include_router(streaming_router, prefix="/api/v1", tags=["Streaming"])
app.include_router(agent_router, prefix="/api/v1", tags=["Agent"])
app.include_router(cloud_router, prefix="/api/v1", tags=["Cloud"])

app.include_router(system_router, prefix="/api/v1/system", tags=["System"])

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


# 静态目录：在容器内通常是 /app/static；在宿主机部署通常是 <项目根>/static
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# 兼容一些历史部署路径
if not STATIC_DIR.exists():
    for cand in (Path("/data/aiops/static"), Path("/app/static")):
        if cand.exists():
            STATIC_DIR = cand
            break

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.warning(f"Static directory not found, skip mounting: {STATIC_DIR}")



@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"detail": "index.html not found"}



@app.get("/health")
async def health():
    return {"status": "alive", "engine": "GPT-4o"}


# ---- License middleware (offline / private deployment) ----
from app.core.license import ensure_license_state, is_request_exempt, license_block_response


@app.middleware("http")
async def license_middleware(request, call_next):
    # 静态资源与免检路径直接放行
    if is_request_exempt(request.url.path):
        return await call_next(request)

    # 确保存在 trial/license 状态，并判断是否允许访问
    try:
        ok, detail = ensure_license_state()
        if not ok:
            return license_block_response(detail=detail)
    except Exception as exc:
        # 授权模块异常时给出明确错误，避免无响应
        logger.error(f"License check error: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "License模块异常，请联系管理员"})

    return await call_next(request)
