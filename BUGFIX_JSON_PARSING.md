# Bug修复 - JSON解析和命令验证

## 问题描述

用户反馈："查看这台机器上跑的容器列表"时，系统生成了错误的命令：
- 把JSON格式的`"steps": [`当作命令执行
- 导致`bash: line 1: steps:: command not found`错误
- 修复逻辑也在重复同样的错误

## 根本原因

1. **前端问题**：前端还在使用旧的复杂提示词（阶段A/B/C），这些提示词被包含在用户需求中发送给后端
2. **JSON解析问题**：当AI返回的JSON格式不完整时，解析失败，但系统把原始文本（包括`"steps": [`）当作命令执行
3. **缺少验证**：没有验证提取的命令是否是有效的shell命令

## 修复方案

### 1. 修复前端提示词 (`static/index.html`)

**修改前**：
```javascript
const opsPrompt = `
[阶段 A 发现] 确认目标存在并收集信息
- 容器名不确定：先用 \`docker ps --filter "name=graf"...
[阶段 B 执行] 单步操作，非交互...
[阶段 C 验证] 对执行步骤做验证...
用户需求：${q0}
`.trim();
```

**修改后**：
```javascript
// 直接使用用户需求，不要添加复杂的提示词（后端会处理）
const opsPrompt = q0;
```

### 2. 改进JSON解析逻辑 (`app/services/enhanced_ssh_service.py`)

**改进点**：
- 更准确地找到完整的JSON对象（从第一个{到最后一个}）
- 添加命令验证函数`_is_valid_shell_command()`
- 排除明显的JSON片段（如`"steps":`、`"cmd":`等）
- 验证命令包含shell关键字

**新增验证函数**：
```python
def _is_valid_shell_command(self, cmd: str) -> bool:
    """验证是否是有效的shell命令（不能是JSON片段）"""
    # 排除明显的JSON片段
    invalid_patterns = [
        r'^["\']?\s*steps\s*[:=]',  # "steps": 或 steps:
        r'^["\']?\s*\{',  # 以{开头
        r'^["\']?\s*\[',  # 以[开头
        r'^\s*"cmd"\s*:',  # "cmd":
        r'^\s*"desc"\s*:',  # "desc":
    ]
    
    # 检查是否包含shell关键字
    shell_keywords = ['docker', 'kubectl', 'systemctl', 'ps', 'grep', ...]
    
    return has_shell_keyword and not matches_invalid_pattern
```

### 3. 改进错误处理

- 如果解析失败，返回空列表，而不是把原始文本当作命令
- 记录详细的日志，便于调试
- 如果解析到的步骤中没有有效命令，返回空列表

## 修复效果

### 修复前
- ❌ 把`"steps": [`当作命令执行
- ❌ 导致`bash: line 1: steps:: command not found`错误
- ❌ 修复逻辑也在重复同样的错误

### 修复后
- ✅ 只提取有效的shell命令
- ✅ 排除JSON片段
- ✅ 对于"查看容器列表"，只生成1条命令：`docker ps`
- ✅ 如果解析失败，返回空列表，不会执行无效命令

## 测试建议

1. **简单查询**：
   - 问题："查看这台机器上跑的容器列表"
   - 预期：1条命令 `docker ps`

2. **复杂查询**：
   - 问题："mysql root密码是多少"
   - 预期：2条命令（找到容器 + 查看密码）

3. **操作类**：
   - 问题："重启所有容器"
   - 预期：根据复杂度生成必要步骤

## 文件变更

- `static/index.html` - 移除旧的复杂提示词
- `app/services/enhanced_ssh_service.py` - 改进JSON解析和命令验证

## 部署

代码已更新并重启服务，修复已生效。

