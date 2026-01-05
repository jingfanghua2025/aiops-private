# Cursor风格优化 - 流畅、丰富、精确的对话体验

## 优化目标

将AIOps+的问答和操作优化成像Cursor一样：
- ✅ **顺滑流畅**：多轮对话连贯，上下文理解准确
- ✅ **内容丰富**：支持多种交互模式，提供详细反馈
- ✅ **100%专注用户需求**：精准理解用户意图，不答非所问

## 新增功能

### 1. 对话上下文管理 (`app/services/conversation_service.py`)

**功能**：
- 支持多轮对话，保持上下文连贯性
- 自动管理对话历史（24小时过期）
- 支持对话摘要和上下文压缩

**特性**：
- 每个用户可以有多个对话会话
- 自动清理过期对话
- 支持对话历史查询和管理

### 2. 增强的RAG服务 (`app/services/enhanced_rag_service.py`)

**改进**：
- ✅ 支持多轮对话上下文
- ✅ 动态构建系统提示词（根据对话历史）
- ✅ 更精准的意图理解
- ✅ 100%专注用户需求

**使用方式**：
```python
result = enhanced_rag_service.query(
    question="如何重启Docker容器？",
    user_id=user.id,
    conversation_id="conv_123",  # 可选，用于多轮对话
    mode="qa"  # qa 或 code
)
```

### 3. 增强的SSH服务 (`app/services/enhanced_ssh_service.py`)

**改进**：
- ✅ 用户意图分析（自动识别动作、目标、关键词）
- ✅ 支持对话上下文（多轮对话中理解用户需求）
- ✅ 更精确的命令生成（100%专注用户需求）
- ✅ 智能命令解析和回退机制

**特性**：
- 自动分析用户意图（find/check/create/delete等）
- 识别目标对象（container/file/service等）
- 提取关键词（容器名、文件名等）
- 基于意图生成精确命令

### 4. 更新的API端点

**`POST /api/v1/ask`** - 增强的问答接口
- 新增参数：`conversation_id`（可选，用于多轮对话）
- 新增参数：`mode`（qa/code，默认qa）
- 返回：包含`conversation_id`，供前端使用

**`POST /api/v1/ssh/propose`** - 增强的排障计划接口
- `ProposeSchema`新增：`conversation_id`（可选）
- 使用增强的SSH服务生成更精确的命令
- 返回：包含`conversation_id`

## 核心优化点

### 1. 精准理解用户意图

**意图分析**：
```python
intent = {
    "action": "find",      # find/check/create/delete/restart等
    "target": "container", # container/file/service/process等
    "keywords": ["graf"],  # 提取的关键词
    "scope": "single"      # single/multiple/all
}
```

**基于意图生成命令**：
- 如果用户问"查找graf容器"，只生成查找命令
- 如果用户问"查看README.md"，只生成查看文件命令
- 禁止添加用户没有要求的内容

### 2. 多轮对话支持

**对话上下文管理**：
- 自动保存对话历史
- 在生成回答时考虑之前的对话
- 支持"继续"、"还有吗"等上下文相关的问题

**示例**：
```
用户："如何重启Docker容器？"
助手："可以使用 docker restart <容器名>..."

用户："如果容器没有运行呢？"
助手：（理解上下文，提供启动容器的方案）
```

### 3. 更精确的提示词

**系统提示词优化**：
- 明确禁止添加用户没有要求的内容
- 提供错误示例和正确示例对比
- 强调"100%专注用户需求"

**用户提示词增强**：
- 包含用户意图分析结果
- 包含对话上下文（如果有）
- 明确强调"只生成用户明确要求的内容"

## 使用示例

### 前端调用示例

**单轮对话**：
```javascript
// 问答
const res = await fetch('/api/v1/ask?question=' + encodeURIComponent(q), {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + token }
});

// 排障计划
const res = await api('/ssh/propose', 'POST', {
  host_id: hostId,
  task: opsPrompt
});
```

**多轮对话**：
```javascript
let conversationId = null;

// 第一轮
const res1 = await fetch('/api/v1/ask?question=' + encodeURIComponent(q1) + 
  '&conversation_id=' + (conversationId || ''), {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + token }
});
conversationId = res1.conversation_id;

// 第二轮（使用相同的conversation_id）
const res2 = await fetch('/api/v1/ask?question=' + encodeURIComponent(q2) + 
  '&conversation_id=' + conversationId, {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + token }
});
```

## 文件变更

### 新增文件
- `app/services/conversation_service.py` - 对话上下文管理
- `app/services/enhanced_rag_service.py` - 增强的RAG服务
- `app/services/enhanced_ssh_service.py` - 增强的SSH服务
- `CURSOR_STYLE_OPTIMIZATION.md` - 本文档

### 修改文件
- `app/api/endpoints.py` - 更新API端点支持对话上下文
- `app/services/ssh_service.py` - 原有服务（保留兼容）
- `app/services/rag_service.py` - 原有服务（保留兼容）

## 部署说明

### 1. 代码已更新
所有新代码已添加到项目中，原有代码保留以确保兼容性。

### 2. 重启服务
```bash
# 停止服务
pkill -f '/usr/bin/python3 -m uvicorn app.main:app'

# 启动服务
cd /data/aiops
nohup /usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 80 > /data/aiops/aiops-backend.log 2>&1 &
```

### 3. 前端适配（可选）
前端可以逐步适配新的API参数：
- 添加`conversation_id`参数支持
- 保存和管理对话ID
- 在多轮对话中传递`conversation_id`

## 效果对比

### 优化前
- ❌ 单轮对话，没有上下文
- ❌ 经常答非所问，添加用户没有要求的内容
- ❌ 命令生成过度扩展，包含不必要的步骤

### 优化后
- ✅ 支持多轮对话，上下文连贯
- ✅ 100%专注用户需求，不添加额外内容
- ✅ 精确理解用户意图，生成准确的命令
- ✅ 像Cursor一样流畅和精确

## 后续优化建议

1. **流式输出**：支持SSE/WebSocket实现流式响应
2. **前端优化**：改进UI，支持对话历史展示
3. **性能优化**：对话上下文缓存和压缩
4. **更多模式**：支持更多交互模式（如代码审查、文档生成等）

## 测试建议

1. **单轮对话测试**：
   - 测试简单问题："如何重启Docker容器？"
   - 验证回答是否精准，不添加额外内容

2. **多轮对话测试**：
   - 第一轮："如何查看容器日志？"
   - 第二轮："如果日志文件很大怎么办？"
   - 验证是否理解上下文

3. **命令生成测试**：
   - 测试："查找graf容器"
   - 验证只生成查找命令，不添加检查配置、日志等

4. **意图识别测试**：
   - 测试不同类型的需求
   - 验证意图分析是否准确

