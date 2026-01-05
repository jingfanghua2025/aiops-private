"""
流式输出端点 - 像Cursor一样实时显示处理过程
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.models.user import User, UsageLog
from app.models.user import SessionLocal
from app.services.enhanced_rag_service import EnhancedRAGService
from app.services.enhanced_ssh_service import EnhancedSSHService
from app.models.user import SSHHost
from app.core.auth import oauth2_scheme, SECRET_KEY, ALGORITHM
from jose import jwt
from typing import Optional
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
enhanced_rag_service = EnhancedRAGService()
enhanced_ssh_service = EnhancedSSHService()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """从token获取当前用户"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def stream_ai_response(prompt: str, system_prompt: str, ai_service, temperature=0.3):
    """
    流式生成AI响应，像Cursor一样逐字显示
    """
    try:
        # 发送"思考中"状态
        yield f"data: {json.dumps({'type': 'status', 'message': '思考中...', 'status': 'thinking'})}\n\n"
        await asyncio.sleep(0.1)
        
        # 发送"生成中"状态
        yield f"data: {json.dumps({'type': 'status', 'message': '正在生成回答...', 'status': 'generating'})}\n\n"
        await asyncio.sleep(0.1)
        
        # 调用AI服务（这里需要支持流式输出）
        # 注意：如果AI服务不支持流式，我们需要模拟流式输出
        response = await ai_service.invoke(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature
        )
        
        # 模拟流式输出（逐字显示）
        full_text = response if isinstance(response, str) else response.get('content', '')
        
        # 发送开始标记
        yield f"data: {json.dumps({'type': 'start', 'message': ''})}\n\n"
        
        # 逐字发送（模拟打字效果）
        words = full_text.split(' ')
        for i, word in enumerate(words):
            chunk = word + (' ' if i < len(words) - 1 else '')
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
            await asyncio.sleep(0.02)  # 控制速度
        
        # 发送完成标记
        yield f"data: {json.dumps({'type': 'done', 'message': ''})}\n\n"
        
    except Exception as e:
        logger.error(f"流式输出失败: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@router.get("/ask/stream")
async def ask_question_stream(
    question: str,
    conversation_id: str = None,
    mode: str = "qa",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    流式问答接口 - 像Cursor一样实时显示回答
    """
    try:
        # 记录使用日志
        log = UsageLog(user_id=user.id, task=f"问答(流式): {question[:40]}", cost=0.0)
        db.add(log)
        db.commit()
        
        # 构建提示词
        system_prompt = enhanced_rag_service._build_system_prompt([])
        if mode == "code":
            system_prompt += "\n**代码编写模式**：用户需要可运行的代码，请直接输出代码，可以包含必要的注释。"
        
        async def generate():
            async for chunk in stream_ai_response(
                prompt=question,
                system_prompt=system_prompt,
                ai_service=enhanced_rag_service.ai_service,
                temperature=0.3
            ):
                yield chunk
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        logger.error(f"流式问答失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ssh/propose/stream")
async def propose_ops_stream(
    host_id: int,
    task: str,
    conversation_id: str = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    流式排障计划生成 - 实时显示生成过程
    """
    try:
        host = db.query(SSHHost).filter(SSHHost.id == host_id, SSHHost.owner_id == user.id).first()
        if not host:
            raise HTTPException(status_code=404, detail="主机不存在")
        
        # 检查余额
        from app.api.endpoints import TROUBLESHOOT_BASE_POINTS
        if user.balance < TROUBLESHOOT_BASE_POINTS:
            raise HTTPException(status_code=402, detail="排障点数不足，请充值后重试")
        
        user.balance -= TROUBLESHOOT_BASE_POINTS
        log = UsageLog(
            user_id=user.id,
            task=f"排障计划(流式): {task[:60]}",
            cost=TROUBLESHOOT_BASE_POINTS,
        )
        db.add(log)
        db.commit()
        
        async def generate():
            # 发送状态更新
            yield f"data: {json.dumps({'type': 'status', 'message': '分析用户需求...', 'status': 'analyzing'})}\n\n"
            await asyncio.sleep(0.2)
            
            yield f"data: {json.dumps({'type': 'status', 'message': '生成执行计划...', 'status': 'generating'})}\n\n"
            await asyncio.sleep(0.2)
            
            # 生成计划
            plan = await enhanced_ssh_service.generate_plan(
                task_description=task,
                host_context=host.ip,
                user_id=user.id,
                conversation_id=conversation_id
            )
            
            # 发送计划
            yield f"data: {json.dumps({'type': 'plan', 'plan': plan, 'host_ip': host.ip, 'conversation_id': conversation_id})}\n\n"
            
            # 发送完成
            yield f"data: {json.dumps({'type': 'done', 'message': '计划生成完成'})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        logger.error(f"流式计划生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

