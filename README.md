# AIOps+（OpsGPT）系统说明文档（47.243.217.174）

> 本文档用于说明当前已部署在 `47.243.217.174` 的 AIOps+（OpsGPT）系统：设计、部署、代码结构、关键路径、启动方式与功能清单。
>
> **安全提示**：本文档不会记录任何密钥/密码明文。请勿把 `.env`、邮箱密码、大模型 Key 等敏感信息提交到公开仓库或对外泄露。

---

## 1. 系统目标与总体设计

AIOps+ 是一个面向运维场景的 **Web 管理控制台 + 后端 API 服务**，核心能力包括：

- **智能问答**：方案咨询 / 代码编写 / 排障&部署 三种模式
- **排障&部署（Cursor 风格授权执行）**：先生成执行计划 → 用户点击授权执行（一键执行计划内命令）→ 结果回显；若失败可基于错误自检生成修正命令继续授权
- **主机资产管理（SSH）**：保存主机信息、测试连接、执行命令
- **私有知识库**：从对话保存方案，支持列表/搜索/分页/详情查看（Markdown 渲染）/删除
- **个人中心**：账号信息、绑定信息、实名认证入口等
- **用量与余额（演示计费）**：余额/用量明细/充值（演示）
- **邮箱注册**：邮件验证码（SMTP 真实发送）

### 1.1 架构

- **前端**：单页静态页面 `static/index.html`（HTML + Tailwind CDN + 纯 JS）
- **后端**：FastAPI（Uvicorn）
- **数据库**：SQLAlchemy（当前代码里可见 MySQL 连接串；历史上也曾使用 SQLite 文件）
- **SSH 执行**：Paramiko
- **大模型**：通过 `OPENAI_API_BASE/OPENAI_API_KEY/MODEL_NAME` 适配 DeepSeek 等 OpenAI 兼容 API
- **邮件验证码**：SMTP（支持 126 邮箱等）

### 1.2 访问入口

- **Web 控制台**：`http://47.243.217.174/`
- **健康检查**：`GET /health`
- **静态资源**：`/static/*`
- **后端 API 前缀**：
  - 认证：`/api/v1/auth/*`
  - 业务：`/api/v1/*`

---

## 2. 部署目录与关键路径（本机）

本机实际部署根目录：

- **程序根目录**：`/data/aiops`

目录结构（关键项）：

- `app/`：后端代码（FastAPI）
  - `app/main.py`：后端入口（加载 `.env`、初始化 DB、挂载静态文件、注册路由）
  - `app/api/auth_endpoints.py`：登录/注册/邮箱验证码/微信登录
  - `app/api/endpoints.py`：业务 API（SSH、KB、用量、个人信息等）
  - `app/models/user.py`：SQLAlchemy 模型 + `init_db()`
  - `app/services/`：RAG/脚本/诊断/SSH 等服务
- `static/`：前端与静态资源
  - `static/index.html`：Web 控制台页面
  - `static/logo.svg`：侧边栏 logo（脑图/大脑风格）
  - `static/uploads/`：企业实名认证营业执照上传目录
- `.env`：运行配置（**敏感**）
- `aiops-backend.log`：后端运行日志（nohup 输出）
- `requirements.txt`：Python 依赖

> 说明：根目录下可能存在历史同步残留文件（例如 `/data/aiops/index.html`、`/data/aiops/auth_endpoints.py`）。**实际生效路径以 `/data/aiops/app/**` 与 `/data/aiops/static/**` 为准。**

---

## 3. 关键配置（.env）

后端在启动时会加载：

- `app/main.py` 中：`load_dotenv(dotenv_path="/data/aiops/.env")`

常用环境变量（仅列出键名，不写值）：

### 3.1 大模型（OpenAI 兼容）

- `OPENAI_API_KEY`
- `OPENAI_API_BASE`（例如 DeepSeek）
- `MODEL_NAME`

### 3.2 邮箱验证码（SMTP）

- `SMTP_HOST`（例如 `smtp.126.com`）
- `SMTP_PORT`（例如 `465`）
- `SMTP_SSL`（`true/false`）
- `SMTP_USER`（邮箱账号）
- `SMTP_PASS`（SMTP 客户端授权密码/应用密码）
- `SMTP_FROM`（发件人地址）

> 提示：126 邮箱通常需要开启 SMTP 并使用“客户端授权密码”，不一定等同于网页登录密码。

### 3.3 支付配置（微信/支付宝）

- 微信：`WECHAT_APP_ID`、`WECHAT_MCH_ID`、`WECHAT_MCH_CERT_SERIAL`、`WECHAT_MCH_PRIVATE_KEY_PATH`、`WECHAT_API_V3_KEY`、`WECHAT_PAY_NOTIFY_URL`（可选 `WECHAT_CERT_DIR`）
- 支付宝：`ALIPAY_APP_ID`、`ALIPAY_PRIVATE_KEY_PATH`、`ALIPAY_PUBLIC_KEY_PATH`、`ALIPAY_NOTIFY_URL`、`ALIPAY_RETURN_URL`（可选 `ALIPAY_GATEWAY`，默认 `https://openapi.alipay.com/gateway.do`）
- 回调路径：`/api/v1/payment/notify/wechat`、`/api/v1/payment/notify/alipay`
- 开关：`ALLOW_DEMO_RECHARGE=true` 时才允许旧版“演示充值”接口，默认关闭，前端已切换为真实支付下单。

---

## 4. 启动/重启方式（当前）

当前后端使用 uvicorn 直接启动（端口 80）：

- **查看进程**

```bash
pgrep -af '/usr/bin/python3 -m uvicorn app.main:app'
```

- **停止服务**

```bash
pkill -f '/usr/bin/python3 -m uvicorn app.main:app'
```

- **启动服务**

```bash
cd /data/aiops
nohup /usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 80 > /data/aiops/aiops-backend.log 2>&1 &
```

- **查看日志**

```bash
tail -n 200 /data/aiops/aiops-backend.log
```

> 建议：后续可切换为 `systemd` 管理 uvicorn，避免重复启动导致端口占用（`Errno 98 address already in use`）。

---

## 5. 默认账号

数据库初始化（`app/models/user.py:init_db()`）会在无 `admin` 用户时创建默认管理员：

- 用户名：`admin`
- 密码：`admin@123A`

---

## 6. 功能与 API 对照

### 6.1 认证/注册

- `POST /api/v1/auth/login`：登录（OAuth2 form：`username/password`）
- `POST /api/v1/auth/send-email-code?email=...`：发送邮箱验证码（真实 SMTP）
- `POST /api/v1/auth/register`：注册（JSON：`username/email/password/code`）
- `POST /api/v1/auth/wechat-login?wechat_id=...`：微信登录（前提：已绑定）

### 6.2 个人信息

- `GET /api/v1/user/profile`：个人信息
- `POST /api/v1/user/change-password`：修改密码
- `POST /api/v1/user/bind-wechat?wechat_id=...`：绑定微信（当前为“绑定标识”版本；完整扫码 OAuth 需对接微信开放平台 AppID/Secret）
- `POST /api/v1/user/send-sms`：短信验证码（目前为演示）
- `POST /api/v1/user/verify-personal`：个人实名认证
- `POST /api/v1/user/verify-enterprise`：企业实名认证（上传营业执照）

### 6.3 主机资产与 SSH

- `POST /api/v1/ssh/hosts`：新增主机
- `GET /api/v1/ssh/hosts`：主机列表
- `DELETE /api/v1/ssh/hosts/{id}`：删除主机
- `POST /api/v1/ssh/test`：测试连接
- `POST /api/v1/ssh/propose`：AI 生成命令计划（授权前置）
- `POST /api/v1/ssh/execute`：执行命令（返回 `success/output/error/exit_status`）

### 6.4 私有知识库

- `POST /api/v1/kb/private`：新增知识
- `GET /api/v1/kb/private`：列表
- `DELETE /api/v1/kb/private/{id}`：删除

前端表现：
- 列表：摘要展示
- 详情：**Markdown 渲染 + 代码高亮**

### 6.5 仪表盘/用量

- `GET /api/v1/dashboard/stats`：主机数/任务数/知识库数/余额
- `GET /api/v1/usage/history`：用量明细
- `POST /api/v1/usage/recharge/order`：创建充值订单（body：`amount/method`）
- `GET /api/v1/usage/recharge/order/{order_no}`：查询订单状态（前端轮询用）
- `POST /api/v1/payment/notify/wechat`：微信支付回调
- `POST /api/v1/payment/notify/alipay`：支付宝回调
- `POST /api/v1/usage/recharge?amount=...&method=...`：演示充值（需 `ALLOW_DEMO_RECHARGE=true` 才开启）

---

## 7. 前端交互说明（Cursor 风格）

### 7.1 三种模式

- **方案咨询（qa）**：调用 `/api/v1/ask` 生成方案
- **代码编写（code）**：调用 `/api/v1/ask`，前端注入“输出可运行代码”的提示词
- **排障&部署（ops）**：
  1. 用户选择目标主机（可多选）
  2. 发送指令 → 后端 `/ssh/propose` 生成计划
  3. 前端渲染“授权卡片”（一键执行）
  4. 点击“授权执行” → `/ssh/execute` 顺序执行计划内命令
  5. 若失败（`success=false` 或 `exit_status!=0`）→ 前端基于错误信息再次 `/ssh/propose` 生成修正卡片继续授权

### 7.2 立即反馈

发送后立即出现“生成中/规划中…”占位，避免空白等待。

---

## 8. 运维排障清单

- **页面按钮无响应/控制台报错**：通常是 `static/index.html` JS 语法错误或残留函数引用；可通过浏览器 Console 定位。
- **后端端口占用**：重复启动 uvicorn 会导致 `Errno 98 address already in use`；先 `pkill -f uvicorn` 再启动。
- **邮件收不到验证码**：
  - 检查 `.env` 的 `SMTP_*` 是否正确
  - 126 邮箱需开启 SMTP 并使用“客户端授权密码”
  - 查看 `/data/aiops/aiops-backend.log` 是否有 `邮件发送失败` 报错
- **大模型无返回/余额不足**：检查 `OPENAI_*` 配置与账号余额。

---

## 9. 后续建议（可选）

- 用 `systemd` 管理 uvicorn，避免多进程与端口占用
- 将数据库连接串从代码中迁移到 `.env`，并统一配置管理（避免在代码里出现敏感 DSN）
- 对“排障&部署”增加更强的安全策略（命令白名单/危险命令拦截/审计）
- 微信绑定升级为“扫码 OAuth”完整链路（需要微信开放平台 AppID/Secret）


