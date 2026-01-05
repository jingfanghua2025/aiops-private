"""
增强的SSH服务 - 更精确的命令生成，100%专注用户需求
像Cursor一样精准理解用户意图
"""
import paramiko
import os
import json
import re
import logging
from typing import Optional, Dict, List
from app.services.ai_service import get_ai_service
from app.services.conversation_service import get_conversation_service

logger = logging.getLogger(__name__)


class EnhancedSSHService:
    """增强的SSH服务，更精确的命令生成"""
    
    def __init__(self):
        self.ai_service = get_ai_service()
        self.conversation_service = get_conversation_service()

    def execute_command(self, host_info: dict, command: str):
        """Execute remote command"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Key 认证支持
            pkey = None
            if host_info.get('private_key'):
                from io import StringIO
                try:
                    pkey = paramiko.RSAKey.from_private_key(StringIO(host_info['private_key']))
                except Exception:
                    # Try other key types if needed, or just fail
                    pass
            
            connect_kwargs = {
                'hostname': host_info['ip'],
                'port': host_info.get('port', 22),
                'username': host_info['username'],
                'timeout': 15,  # execute_command timeout
                'banner_timeout': 30
            }
            if pkey:
                connect_kwargs['pkey'] = pkey
            else:
                connect_kwargs['password'] = host_info.get('password')
            
            ssh.connect(**connect_kwargs)

            
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

            # Key 认证支持
            pkey = None
            if host_info.get('private_key'):
                from io import StringIO
                try:
                    pkey = paramiko.RSAKey.from_private_key(StringIO(host_info['private_key']))
                except Exception:
                    # Try other key types if needed, or just fail
                    pass
            
            connect_kwargs = {
                'hostname': host_info['ip'],
                'port': host_info.get('port', 22),
                'username': host_info['username'],
                'timeout': 5,  # execute_command timeout
                'banner_timeout': 30
            }
            if pkey:
                connect_kwargs['pkey'] = pkey
            else:
                connect_kwargs['password'] = host_info.get('password')
            
            ssh.connect(**connect_kwargs)

            ssh.close()
            return {"success": True, "message": "连接成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _analyze_user_intent(self, task_description: str) -> Dict:
        """分析用户意图，提取关键信息"""
        intent = {
            "action": None,  # 主要动作：find, check, view, create, delete, etc.
            "target": None,   # 目标对象：container, file, service, etc.
            "keywords": [],   # 关键词
            "scope": "single"  # 范围：single, multiple, all
        }
        
        task_lower = task_description.lower()
        
        # 识别动作
        action_patterns = {
            "find": ["查找", "找", "搜索", "find", "search", "locate"],
            "check": ["检查", "查看", "check", "view", "show", "list", "查看"],
            "create": ["创建", "新建", "create", "add", "new"],
            "delete": ["删除", "移除", "delete", "remove", "rm"],
            "restart": ["重启", "restart", "reload"],
            "start": ["启动", "start"],
            "stop": ["停止", "stop"],
            "read": ["读取", "查看内容", "read", "cat", "查看"],
            "execute": ["执行", "运行", "execute", "run"]
        }
        
        for action, patterns in action_patterns.items():
            if any(p in task_lower for p in patterns):
                intent["action"] = action
                break
        
        # 识别目标
        target_patterns = {
            "container": ["容器", "container", "docker"],
            "file": ["文件", "file", "文件"],
            "service": ["服务", "service"],
            "process": ["进程", "process", "进程"],
            "log": ["日志", "log", "日志"]
        }
        
        for target, patterns in target_patterns.items():
            if any(p in task_lower for p in patterns):
                intent["target"] = target
                break
        
        # 提取关键词（如容器名、文件名等）
        # 查找引号内的内容
        quoted = re.findall(r'["\']([^"\']+)["\']', task_description)
        if quoted:
            intent["keywords"] = quoted
        
        # 查找常见的命名模式
        name_patterns = [
            r'([a-zA-Z0-9_-]+)容器',
            r'容器([a-zA-Z0-9_-]+)',
            r'文件([a-zA-Z0-9_./-]+)',
            r'([a-zA-Z0-9_./-]+)文件',
        ]
        for pattern in name_patterns:
            matches = re.findall(pattern, task_description)
            if matches:
                intent["keywords"].extend(matches)
        
        return intent

    async def chat_ops(
        self,
        task_description: str,
        host_context: str = "",
        user_id: Optional[int] = None,
        conversation_id: Optional[str] = None,
        execution_history: List[Dict] = None
    ):
        """
        交互式运维对话 Agent：像 Cursor 一样一步步引导用户
        """
        # 构建对话上下文
        conversation_context = []
        if user_id and conversation_id:
            conv = self.conversation_service.get_or_create_conversation(user_id, conversation_id)
            conversation_context = conv.get_recent_messages(max_messages=10)
            
            # 将最新的用户输入添加到历史
            if not execution_history: # 只有纯用户输入才记录，避免执行结果重复记录
                conv.add_message("user", task_description, {"type": "ops_chat"})

        system_prompt = f"""你是一个高级 Linux SRE 运维专家 (AIOps Agent)。
你的工作方式是**交互式、分步骤**地帮助用户完成运维任务（如部署 K8S、排障、安装软件等）。

**当前目标主机**: {host_context if host_context else "未指定"}

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

        # 构建包含执行历史的 User Prompt
        full_user_prompt = task_description
        if execution_history:
            history_text = "\n".join([
                f"[执行记录] Cmd: {h['cmd']} | Exit: {h['exit_code']} | Out: {h['output'][:300]}..." 
                for h in execution_history
            ])
            full_user_prompt = f"{task_description}\n\n【上一步执行结果】:\n{history_text}\n\n请根据执行结果，给出下一步指示（成功则继续，失败则修复）。"

        # 调用 AI
        return await self.ai_service.invoke(
            prompt=full_user_prompt,
            system_prompt=system_prompt,
            temperature=0.1
        )

    async def generate_plan(
        self, 
        task_description: str, 
        host_context: str = "",
        user_id: Optional[int] = None,
        conversation_id: Optional[str] = None
    ):
        """
        生成精确的执行计划，100%专注用户需求
        
        :param task_description: 用户需求描述
        :param host_context: 主机IP
        :param user_id: 用户ID（用于对话上下文）
        :param conversation_id: 对话ID（用于多轮对话）
        """
        # 分析用户意图
        intent = self._analyze_user_intent(task_description)
        
        # 获取对话上下文（如果有）
        conversation_context = []
        if user_id and conversation_id:
            conv = self.conversation_service.get_or_create_conversation(user_id, conversation_id)
            conversation_context = conv.get_recent_messages(max_messages=4)
            conv.add_message("user", task_description, {"type": "ops_plan"})
        
        # 构建系统提示词
        system_prompt = self._build_system_prompt(host_context, intent, conversation_context)
        
        # 构建用户提示词
        user_prompt = self._build_user_prompt(task_description, intent, conversation_context)
        
        try:
            # 调用AI生成计划
            text = await self.ai_service.invoke(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1  # 低温度确保精确性
            )
            
            logger.info(f"AI返回原始文本: {text[:200]}...")
            
            # 解析JSON
            steps = self._parse_steps(text, task_description)
            
            if steps:
                logger.info(f"成功解析到 {len(steps)} 个步骤")
                # 保存到对话上下文
                if user_id and conversation_id:
                    conv.add_message("assistant", json.dumps(steps, ensure_ascii=False), {"type": "ops_plan"})
                return steps
            else:
                logger.warning("无法解析AI返回的JSON，尝试回退处理")
                return self._fallback_parse(text, task_description)
        
        except Exception as e:
            logger.error(f"生成计划失败: {e}", exc_info=True)
            return [{
                "desc": "生成计划时出错",
                "cmd": f"echo '错误: {str(e)}' 2>&1"
            }]

    def _build_system_prompt(
        self, 
        host_context: str, 
        intent: Dict,
        conversation_context: List[Dict]
    ) -> str:
        """构建系统提示词"""
        prompt = f"""你是一个经验丰富的Linux运维专家。你的任务是理解用户的运维需求，并生成准确、可执行的命令计划。

当前目标主机IP: {host_context if host_context else "未指定"}

**⚠️ 核心原则（必须严格遵守）**：

1. **100%专注用户需求，只生成最直接、最少的必要步骤**
   - 如果用户问"查找graf容器"，就只生成1条查找容器的命令，不要额外检查配置、日志、网络等
   - 如果用户问"查看README.md"，就只生成1条查看文件的命令，不要额外搜索、分析、统计等
   - 如果用户问"mysql root密码是多少"，就只生成1-2条命令：找到容器 + 查看环境变量，不要生成9条命令检查各种地方
   - 如果用户问"检查文件是否存在"，就只生成1条检查文件是否存在的命令，不要额外查看文件内容

2. **查询类问题：生成最少的必要步骤**
   - 查询密码：找到容器（1步）+ 查看环境变量（1步）= 最多2步
   - 查询配置：找到容器（1步）+ 查看配置文件（1步）= 最多2步
   - 查询状态：1条命令即可
   - **禁止生成超过3步的查询计划**

3. **精确理解用户意图**
   - 分析用户真正想要做什么
   - 识别用户需求的核心动作和目标
   - 不要过度解读或扩展用户需求
   - **对于查询类问题，直接给出答案路径，不要生成大量检查步骤**

4. **禁止过度扩展**
   - 不要因为"可能有用"而添加额外的检查步骤
   - 不要"为了完整性"而添加用户没有要求的内容
   - 不要"以防万一"而添加额外的验证步骤
   - **查询类问题：只生成最直接的查询命令，不要生成验证、检查、排查等步骤**

**用户意图分析**：
- 主要动作：{intent.get('action', '未识别')}
- 目标对象：{intent.get('target', '未识别')}
- 关键词：{', '.join(intent.get('keywords', [])) or '无'}

**输出格式要求**：
必须返回有效的JSON格式，结构如下：
{{
  "steps": [
    {{
      "desc": "步骤说明（中文，简洁明确）",
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

用户需求："查看README.md文件内容"
正确输出：
{{
  "steps": [
    {{
      "desc": "查看README.md文件内容",
      "cmd": "cat README.md 2>&1 || echo '文件不存在'"
    }}
  ]
}}

用户需求："mysql root密码是多少"
正确输出（只生成2步，不要生成9步）：
{{
  "steps": [
    {{
      "desc": "查找MySQL容器",
      "cmd": "C=$(docker ps --filter 'name=mysql' --format '{{{{.Names}}}}' | head -1) && if [ -n \"$C\" ]; then echo \"找到容器: $C\"; else echo \"未找到MySQL容器\" && exit 1; fi 2>&1"
    }},
    {{
      "desc": "查看MySQL root密码",
      "cmd": "C=$(docker ps --filter 'name=mysql' --format '{{{{.Names}}}}' | head -1) && if [ -n \"$C\" ]; then docker exec $C env | grep MYSQL_ROOT_PASSWORD 2>&1 || docker inspect $C | grep -A1 MYSQL_ROOT_PASSWORD 2>&1; else echo \"未找到MySQL容器\"; fi"
    }}
  ]
}}

**❌ 错误示例（过度扩展）**：
用户需求："mysql root密码是多少"
错误输出（生成了9步，包含大量不必要的检查）：
{{
  "steps": [
    {{"desc": "查找mysql容器", "cmd": "..."}},
    {{"desc": "查找mariadb容器", "cmd": "..."}},  // ❌ 用户只问了mysql，不要检查mariadb
    {{"desc": "查找所有数据库容器", "cmd": "..."}},  // ❌ 用户只问了mysql，不要查找所有
    {{"desc": "检查环境变量", "cmd": "..."}},
    {{"desc": "检查启动命令", "cmd": "..."}},  // ❌ 环境变量已经够了，不需要检查启动命令
    {{"desc": "检查配置文件", "cmd": "..."}},  // ❌ 密码在环境变量中，不需要检查配置文件
    {{"desc": "检查日志", "cmd": "..."}},  // ❌ 完全不需要
    {{"desc": "验证端口", "cmd": "..."}},  // ❌ 完全不需要
    {{"desc": "检查docker-compose", "cmd": "..."}}  // ❌ 完全不需要
  ]
}}
"""
        
        # 如果有对话上下文，添加上下文信息
        if conversation_context:
            prompt += "\n**对话上下文**：\n"
            for msg in conversation_context[-2:]:  # 只取最近2条
                if msg["role"] == "user":
                    prompt += f"- 用户之前说：{msg['content'][:100]}\n"
        
        return prompt

    def _build_user_prompt(
        self, 
        task_description: str,
        intent: Dict,
        conversation_context: List[Dict]
    ) -> str:
        """构建用户提示词"""
        # 判断是否是查询类问题
        query_keywords = ["是多少", "是什么", "密码", "配置", "状态", "查看", "查看", "显示", "列出"]
        is_query = any(kw in task_description for kw in query_keywords)
        
        prompt = f"""用户需求：{task_description}

⚠️ 重要提醒：
- 请严格按照用户需求生成命令计划
- **只生成最直接、最少的必要步骤，不要生成超过3步的查询计划**
- 如果用户只要求做一件事，就只生成做这一件事的命令（1步）
- 如果是查询类问题（如"密码是多少"），最多生成2步：找到目标 + 查询信息
- 禁止因为"可能有用"而添加用户没有要求的内容
- 禁止生成大量检查、验证、排查步骤
- 用户意图：{intent.get('action', '未识别')} {intent.get('target', '未识别')}
- 问题类型：{"查询类（应生成1-2步）" if is_query else "操作类"}"""
        
        return prompt

    def _parse_steps(self, raw_text: str, task_description: str) -> list:
        """从AI返回的文本中解析steps数组，确保只提取有效的shell命令"""
        if not raw_text:
            return []
        
        # 清理文本
        text = raw_text.strip()
        text = re.sub(r'```(?:json|shell)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text)
        text = text.lstrip('$ ').strip()
        
        if text.lower().startswith("json"):
            text = text[4:].strip()
        
        # 尝试找到完整的JSON对象（从第一个{到最后一个}）
        json_start = text.find('{')
        json_end = text.rfind('}')
        
        if json_start != -1 and json_end != -1 and json_end > json_start:
            json_str = text[json_start:json_end + 1]
        else:
            json_str = text
        
        try:
            data = json.loads(json_str)
            
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
                    
                    cmd = str(s.get("cmd") or s.get("command") or s.get("shell") or "").strip()
                    desc = str(s.get("desc") or s.get("description") or s.get("step") or "").strip()
                    
                    # 清理命令
                    cmd = cmd.replace("```", "").replace("`", "").strip()
                    
                    # 验证命令是有效的shell命令（不能是JSON片段）
                    if cmd and self._is_valid_shell_command(cmd):
                        if not desc:
                            desc = f"执行: {task_description}"
                        cleaned.append({"cmd": cmd, "desc": desc})
                
                if cleaned:
                    logger.info(f"成功解析到 {len(cleaned)} 个有效步骤")
                    return cleaned
                else:
                    logger.warning("解析到的步骤中没有有效的shell命令")
        
        except json.JSONDecodeError as e:
            logger.debug(f"JSON解析失败: {e}, 原始文本: {text[:200]}")
        
        return []
    
    def _is_valid_shell_command(self, cmd: str) -> bool:
        """验证是否是有效的shell命令（不能是JSON片段）"""
        if not cmd or len(cmd) < 3:
            return False
        
        # 排除明显的JSON片段
        invalid_patterns = [
            r'^["\']?\s*steps\s*[:=]',  # "steps": 或 steps:
            r'^["\']?\s*\{',  # 以{开头
            r'^["\']?\s*\[',  # 以[开头
            r'^\s*"cmd"\s*:',  # "cmd":
            r'^\s*"desc"\s*:',  # "desc":
        ]
        
        for pattern in invalid_patterns:
            if re.match(pattern, cmd, re.IGNORECASE):
                logger.warning(f"检测到无效命令（JSON片段）: {cmd[:50]}")
                return False
        
        # 检查是否包含常见的shell命令关键字
        shell_keywords = [
            'docker', 'kubectl', 'systemctl', 'ps', 'grep', 'find', 'cat', 
            'curl', 'wget', 'ssh', 'scp', 'ls', 'cd', 'echo', 'if', 'for',
            'while', 'test', 'exec', 'run', 'start', 'stop', 'restart'
        ]
        
        cmd_lower = cmd.lower()
        has_shell_keyword = any(keyword in cmd_lower for keyword in shell_keywords)
        
        return has_shell_keyword

    def _fallback_parse(self, text: str, task_description: str) -> list:
        """回退解析"""
        if not text:
            return []
        
        text = text.replace("```", "").replace("`", "").strip()
        lines = text.split('\n')
        commands = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
            
            if re.search(r'\$|docker|kubectl|systemctl|ps|grep|find|cat|curl|wget|ssh|scp', line, re.IGNORECASE):
                cmd = re.sub(r'^\$?\s*', '', line)
                if cmd and len(cmd) > 3:
                    commands.append(cmd)
        
        if commands:
            return [{"cmd": cmd, "desc": f"执行: {task_description}"} for cmd in commands[:5]]
        
        if text and len(text) < 500:
            return [{"cmd": text, "desc": f"执行: {task_description}"}]
        
        return []

