from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.models.user import User, SSHHost, UsageLog
from app.api.endpoints import get_current_user, get_db, TROUBLESHOOT_BASE_POINTS
from app.services.enhanced_ssh_service import EnhancedSSHService
from app.services.enhanced_rag_service import stream_ai_response
from typing import List, Dict, Optional
from pydantic import BaseModel
import json
import logging
import asyncio

router = APIRouter()
enhanced_ssh_service = EnhancedSSHService()
logger = logging.getLogger(__name__)

class AgentChatSchema(BaseModel):
    host_ids: List[int]
    message: str
    conversation_id: Optional[str] = None
    execution_history: Optional[List[Dict]] = None

@router.post("/ssh/agent/chat")
async def agent_chat(
    req: AgentChatSchema,
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    交互式运维 Agent 接口 (流式)
    """
    # 1. 获取主机信息
    hosts = db.query(SSHHost).filter(SSHHost.id.in_(req.host_ids), SSHHost.owner_id == user.id).all()
    if not hosts:
        raise HTTPException(status_code=404, detail="未找到指定主机")
    
    host_context = ", ".join([f"{h.name}({h.ip})" for h in hosts])
    
    # 2. 扣费逻辑 (简化：每次对话扣 1 点，或者首次扣点)
    # 这里暂不扣费，鼓励交互
    
    # 3. 构造 Prompt
    # 既然我们要流式，就不能直接调 enhanced_ssh_service.chat_ops (它返回 str)
    # 我们需要手动构建 Prompt 并调用 stream_ai_response
    
    system_prompt = f"""你是一个高级 Linux SRE 运维专家 (AIOps Agent)。
你的工作方式是**交互式、分步骤**地帮助用户完成运维任务。

**当前目标主机**: {host_context}

**你的核心行为准则**：
1.  **像 Cursor 一样思考**：不要一次性抛出所有步骤。根据用户的需求，先给出**当前最需要执行**的 1-3 条命令。
2.  **代码块即动作**：凡是需要用户执行的命令，必须包裹在 ```bash ... ``` 代码块中。前端会自动识别并提供“运行”按钮。
3.  **阅读执行结果**：用户执行完命令后，会将结果（输出/报错）发回给你。你必须根据结果来决定下一步：
    *   如果**成功**：继续下一步操作。
    *   如果**失败**：分析错误原因，给出修复命令（Fix），而不要盲目继续。
4.  **环境感知**：在进行复杂部署（如 K8S）前，优先检查环境（系统版本、防火墙、Swap、内核模块等），确保成功率。
5.  **不要废话**：解释要简练，重点放在 Command 上。不要解释 "我将执行...", 直接给代码块。

**回复格式示例**：
用户：部署 K8S
你：
好的，我们先检查环境配置。请在所有节点执行以下命令关闭 Swap 并加载模块：
```bash
sudo swapoff -a
sudo modprobe br_netfilter
lsmod | grep br_netfilter
```

(用户执行并反馈结果后...)

你：
环境检查通过。接下来安装 containerd...
```bash
...
```
"""

    full_user_prompt = req.message
    if req.execution_history:
        history_text = "\n".join([
            f"[主机 {h.get('host_ip','unknown')}] Cmd: {h['cmd']} | Exit: {h['exit_code']} | Out: {h['output'][:500]}..." 
            for h in req.execution_history
        ])
        full_user_prompt += f"\n\n【上一步执行结果】:\n{history_text}\n\n请根据执行结果，给出下一步指示（成功则继续，失败则修复）。"

    async def generate():
        try:
            # 模拟思考延迟
            # yield "思考中..." 
            
            async for chunk in stream_ai_response(
                prompt=full_user_prompt,
                system_prompt=system_prompt,
                temperature=0.1
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Agent Chat Error: {e}")
            yield f"\n\n[System Error]: {str(e)}"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
