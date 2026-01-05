# AI模型优化更新日志

## 更新日期
2025-12-23

## 问题修复

### 1. 修复"答非所问"问题

**问题描述**：
- 智能问答功能经常答非所问
- 排障&部署模式生成的命令计划与用户需求不匹配

**修复内容**：
1. **改进SSH服务的提示词** (`app/services/ssh_service.py`)
   - 移除了硬编码的特殊处理逻辑（如EMQX/MQTT的特殊分支）
   - 添加了更清晰的系统提示词，强调"准确理解用户意图"、"只生成用户明确要求的内容"
   - 改进了JSON解析逻辑，更好地处理AI返回的各种格式
   - 添加了回退解析机制，提高容错性

2. **优化RAG服务的提示词** (`app/services/rag_service.py`)
   - 改进了系统提示词，强调"准确理解问题"、"直接回答问题"、"不要添加无关内容"
   - 优化了上下文检索和回答生成逻辑
   - 添加了更好的错误处理和回退机制

### 2. 支持多个AI模型提供商

**新增功能**：
- 创建了统一的AI服务 (`app/services/ai_service.py`)
- 支持以下模型提供商：
  - **DeepSeek**（默认）：通过OpenAI兼容接口
  - **豆包（DashScope）**：阿里云通义千问
  - **OpenAI**：原生OpenAI API

**配置方式**：
在 `.env` 文件中配置：

```bash
# DeepSeek配置（默认）
OPENAI_API_KEY=sk-your-deepseek-api-key
OPENAI_API_BASE=https://api.deepseek.com
MODEL_NAME=deepseek-chat

# 豆包配置（可选）
DASHSCOPE_API_KEY=sk-your-dashscope-api-key
DASHSCOPE_MODEL_NAME=qwen-turbo
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

# 模型提供商选择（auto/deepseek/dashscope/openai）
AI_MODEL_PROVIDER=auto  # auto会自动选择：优先DeepSeek，如果配置了DASHSCOPE_API_KEY则使用豆包
```

## 文件变更

### 新增文件
- `app/services/ai_service.py` - 统一的AI服务，支持多模型
- `.env.example` - 配置示例文件
- `CHANGELOG_AI_FIX.md` - 本更新日志

### 修改文件
- `app/services/ssh_service.py` - 改进提示词，移除硬编码逻辑
- `app/services/rag_service.py` - 优化提示词，使用统一AI服务
- `requirements.txt` - 添加 `dashscope` 依赖

## 使用说明

### 1. 安装新依赖

```bash
cd /data/aiops
pip install dashscope
```

### 2. 配置模型（可选）

如果要使用豆包模型，在 `.env` 文件中添加：

```bash
DASHSCOPE_API_KEY=your-dashscope-api-key
DASHSCOPE_MODEL_NAME=qwen-turbo
AI_MODEL_PROVIDER=dashscope  # 或使用 auto 自动选择
```

### 3. 重启服务

```bash
# 停止服务
pkill -f '/usr/bin/python3 -m uvicorn app.main:app'

# 启动服务
cd /data/aiops
nohup /usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 80 > /data/aiops/aiops-backend.log 2>&1 &
```

## 测试建议

1. **测试智能问答**：
   - 在"方案咨询"模式下提问，验证回答是否准确
   - 测试不同复杂度的问题

2. **测试排障&部署**：
   - 选择目标主机
   - 输入具体的运维需求（如"查找graf容器"）
   - 验证生成的命令计划是否与需求匹配

3. **测试多模型切换**：
   - 配置不同的模型提供商
   - 验证系统能正确使用配置的模型

## 注意事项

1. **豆包模型**：需要安装 `dashscope` 包，并配置有效的API密钥
2. **模型切换**：修改 `.env` 后需要重启服务才能生效
3. **API密钥安全**：请妥善保管API密钥，不要提交到公开仓库

## 后续优化建议

1. 添加模型性能监控和对比
2. 支持模型自动切换（当一个模型失败时自动切换到备用模型）
3. 添加用户级别的模型选择功能
4. 优化提示词模板，支持更多场景

