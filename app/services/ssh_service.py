import paramiko
import os
import json
import re
import logging
from app.services.ai_service import get_ai_service

logger = logging.getLogger(__name__)


class SSHService:
    def __init__(self):
        self.ai_service = get_ai_service()

    def execute_command(self, host_info: dict, command: str):
        """Execute remote command"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=host_info['ip'],
                port=host_info.get('port', 22),
                username=host_info['username'],
                password=host_info['password'],
                timeout=15
            )
            
            stdin, stdout, stderr = ssh.exec_command(command)
            output = stdout.read().decode(errors="ignore")
            error = stderr.read().decode(errors="ignore")
            try:
                exit_status = stdout.channel.recv_exit_status()
            except Exception:
                exit_status = None
            ssh.close()
            
            return {
                "success": (exit_status == 0) if exit_status is not None else (error.strip() == ""),
                "output": output,
                "error": error,
                "exit_status": exit_status
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "exit_status": None
            }

    def test_connection(self, host_info: dict):
        """Test SSH connection"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=host_info['ip'],
                port=host_info.get('port', 22),
                username=host_info['username'],
                password=host_info['password'],
                timeout=5
            )
            ssh.close()
            return {"success": True, "message": "连接成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def generate_plan(self, task_description: str, host_context: str = ""):
        """
        AI生成执行计划，基于用户需求
        改进的提示词让AI更好地理解用户意图，避免答非所问
        """
        # 改进的系统提示词：更清晰地说明任务和要求，严格禁止答非所问
        system_prompt = f"""你是一个经验丰富的Linux运维专家。你的任务是理解用户的运维需求，并生成准确、可执行的命令计划。

当前目标主机IP: {host_context if host_context else "未指定"}

**⚠️ 核心原则（必须严格遵守）**：
1. **严格按用户需求生成，禁止添加任何用户没有明确要求的内容**
   - 如果用户问"查找graf容器"，就只生成查找容器的命令，不要额外检查配置、日志、网络、进程等
   - 如果用户问"查看README.md"，就只生成查看文件的命令，不要额外搜索、分析、统计等
   - 如果用户问"检查文件是否存在"，就只生成检查文件是否存在的命令，不要额外查看文件内容

2. **禁止过度扩展和联想**
   - 不要因为用户问了A，就自动添加B、C、D相关的检查
   - 不要"为了完整性"而添加用户没有要求的内容
   - 不要"以防万一"而添加额外的验证步骤（除非用户明确要求）

3. **准确理解用户意图**
   - 仔细分析用户的需求描述，理解用户真正想要做什么
   - 如果用户需求不明确，生成最直接、最简单的实现方式
   - 不要自作主张添加"可能有用"的额外步骤

**❌ 错误示例（答非所问）**：
用户需求："查找包含graf关键字的容器"
错误输出（包含用户没有要求的内容）：
{{
  "steps": [
    {{"desc": "查找容器", "cmd": "docker ps --filter 'name=graf' ..."}},
    {{"desc": "检查容器配置", "cmd": "..."}},  // ❌ 用户没有要求检查配置
    {{"desc": "查看容器日志", "cmd": "..."}}   // ❌ 用户没有要求查看日志
  ]
}}

**✅ 正确示例（只回答用户问的）**：
用户需求："查找包含graf关键字的容器"
正确输出（只包含用户要求的内容）：
{{
  "steps": [
    {{"desc": "查找包含graf关键字的容器", "cmd": "docker ps --filter 'name=graf' --format '{{{{.Names}}}} {{{{.ID}}}} {{{{.Ports}}}}' 2>&1 || echo '无匹配容器: graf'"}}
  ]
}}

**输出格式要求**：
必须返回有效的JSON格式，结构如下：
{{
  "steps": [
    {{
      "desc": "步骤说明（中文）",
      "cmd": "单条可执行的shell命令"
    }}
  ]
}}

**命令编写规范**：
- 每个cmd只包含一条可执行的shell命令，可以包含前置变量赋值（如 C=$(docker ps ...)）
- 必须非交互式执行，禁止使用 -it 参数
- 默认追加 2>&1 捕获错误输出
- 禁止破坏性命令（如 rm -rf /、格式化磁盘等）
- 容器名不确定时，先用 docker ps 进行模糊匹配
- 如果命令可能无输出，在命令中添加 echo 提示（如：|| echo "无匹配结果"）
- 不要返回Markdown代码块标记，不要添加编号前缀，不要将多条命令堆在一行

**示例**：
用户需求："查找包含graf关键字的容器"
正确输出：
{{
  "steps": [
    {{
      "desc": "查找包含graf关键字的容器",
      "cmd": "docker ps --filter 'name=graf' --format '{{{{.Names}}}} {{{{.ID}}}} {{{{.Ports}}}}' 2>&1 || echo '无匹配容器: graf'"
    }}
  ]
}}

用户需求："检查grafana容器的配置"
正确输出：
{{
  "steps": [
    {{
      "desc": "查找grafana容器",
      "cmd": "C=$(docker ps --filter 'name=grafana' --format '{{{{.Names}}}}' | head -1) && if [ -n \"$C\" ]; then echo \"找到容器: $C\"; else echo \"未找到grafana容器\" && exit 1; fi 2>&1"
    }},
    {{
      "desc": "检查容器内的grafana配置文件",
      "cmd": "C=$(docker ps --filter 'name=grafana' --format '{{{{.Names}}}}' | head -1) && if [ -n \"$C\" ]; then docker exec $C cat /etc/grafana/grafana.ini 2>&1 || echo '配置文件不存在'; else echo '未找到容器'; fi"
    }}
  ]
}}

现在请根据用户需求生成执行计划。"""

        user_prompt = f"""用户需求：{task_description}

⚠️ 重要提醒：
- 请严格按照用户需求生成命令计划
- 只生成用户明确要求的内容，不要添加任何额外的检查、验证、分析步骤
- 如果用户只要求做一件事，就只生成做这一件事的命令
- 禁止因为"可能有用"而添加用户没有要求的内容

请生成执行计划："""

        try:
            # 调用AI服务
            text = await self.ai_service.invoke(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1
            )
            
            logger.info(f"AI返回原始文本: {text[:200]}...")
            
            # 解析JSON
            steps = self._parse_steps(text, task_description)
            
            if steps:
                logger.info(f"成功解析到 {len(steps)} 个步骤")
                return steps
            else:
                logger.warning("无法解析AI返回的JSON，尝试回退处理")
                # 回退：如果模型给的不是JSON，尝试提取命令
                return self._fallback_parse(text, task_description)
        
        except Exception as e:
            logger.error(f"生成计划失败: {e}", exc_info=True)
            # 返回一个基本的错误提示步骤
            return [{
                "desc": "生成计划时出错",
                "cmd": f"echo '错误: {str(e)}' 2>&1"
            }]

    def _parse_steps(self, raw_text: str, task_description: str) -> list:
        """
        从AI返回的文本中解析steps数组
        改进的解析逻辑，更好地处理各种格式
        """
        if not raw_text:
            return []
        
        # 清理文本：移除代码块标记、多余空白等
        text = raw_text.strip()
        text = re.sub(r'```(?:json|shell)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text)
        text = text.lstrip('$ ').strip()
        
        # 如果以"json"开头，移除它
        if text.lower().startswith("json"):
            text = text[4:].strip()
        
        # 尝试找到JSON对象
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = text
        
        try:
            data = json.loads(json_str)
            
            # 支持多种可能的字段名
            steps = None
            if isinstance(data, dict):
                steps = data.get("steps") or data.get("plan") or data.get("commands")
            elif isinstance(data, list):
                steps = data
            
            if isinstance(steps, list) and len(steps) > 0:
                cleaned = []
                for s in steps:
                    if not isinstance(s, dict):
                        continue
                    
                    # 支持多种字段名
                    cmd = str(s.get("cmd") or s.get("command") or s.get("shell") or "").strip()
                    desc = str(s.get("desc") or s.get("description") or s.get("step") or "").strip()
                    
                    # 清理命令中的代码块标记
                    cmd = cmd.replace("```", "").replace("`", "").strip()
                    
                    if cmd:
                        if not desc:
                            desc = f"执行: {task_description}"
                        cleaned.append({"cmd": cmd, "desc": desc})
                
                if cleaned:
                    return cleaned
        
        except json.JSONDecodeError as e:
            logger.debug(f"JSON解析失败: {e}, 原始文本: {text[:200]}")
        
        return []

    def _fallback_parse(self, text: str, task_description: str) -> list:
        """
        回退解析：当无法解析JSON时，尝试提取命令
        """
        if not text:
            return []
        
        # 移除代码块标记
        text = text.replace("```", "").replace("`", "").strip()
        
        # 尝试提取看起来像命令的行
        lines = text.split('\n')
        commands = []
        
        for line in lines:
            line = line.strip()
            # 跳过空行、注释、说明性文字
            if not line or line.startswith('#') or line.startswith('//'):
                continue
            
            # 如果行包含常见的shell命令模式
            if re.search(r'\$|docker|kubectl|systemctl|ps|grep|find|cat|curl|wget|ssh|scp', line, re.IGNORECASE):
                # 移除命令提示符
                cmd = re.sub(r'^\$?\s*', '', line)
                if cmd and len(cmd) > 3:  # 至少3个字符才认为是有效命令
                    commands.append(cmd)
        
        if commands:
            return [{"cmd": cmd, "desc": f"执行: {task_description}"} for cmd in commands[:5]]  # 最多5条
        
        # 如果还是找不到，返回原始文本作为单条命令
        if text and len(text) < 500:  # 避免过长的文本
            return [{"cmd": text, "desc": f"执行: {task_description}"}]
        
        return []
