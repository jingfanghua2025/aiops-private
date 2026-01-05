from app.api.agent_endpoints import router as agent_router
from app.api.cloud_endpoints import router as cloud_router
import os
import sys
from dotenv import load_dotenv
from app.models.user import init_db

# 加载 .env 文件
load_dotenv(dotenv_path="/data/aiops/.env")

# 初始化数据库
init_db()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.endpoints import router as api_router
from app.api.auth_endpoints import router as auth_router
from app.api.streaming_endpoints import router as streaming_router

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

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Global error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})

from fastapi.responses import JSONResponse

app.mount("/static", StaticFiles(directory="/app/static"), name="static")

@app.get("/")
async def root():
    return FileResponse("/app/static/index.html")

@app.get("/health")
async def health():
    return {"status": "alive", "engine": "GPT-4o"}
