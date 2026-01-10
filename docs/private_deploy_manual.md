## 跃云 AIOps 私有化离线部署手册（要点版）

### 1. 部署前准备

- 一台有网的构建机（用于构建镜像、下载离线依赖包）
- 一台离线目标机（Ubuntu/CentOS，已满足内核与磁盘要求）

### 2. 离线包内容

离线包建议打包为 `aiops-offline-bundle.tar.gz`，包含：
- `offline/images/*.tar`：Docker 镜像（`aiops-backend:offline`、`mysql:8.0`、`nginx:latest`）
- `offline/packages/ubuntu/*.deb`：Ubuntu Docker/Compose 离线包（可选：若目标机已安装可不放）
- `offline/packages/centos/*.rpm`：CentOS/RHEL Docker/Compose 离线包（可选）
- `offline/config/aiops.env`：环境配置（不要把真实密钥提交 GitHub）

### 3. 离线一键部署（目标机执行）

```bash
tar -xzf aiops-offline-bundle.tar.gz
cd offline
sudo ./install.sh
```

部署完成后输出：
- 登录地址（80端口）
- 后端健康检查地址（8000端口）
- 默认管理员账号/密码

### 4. 私有化模式说明（重要）

当 `PRIVATE_DEPLOYMENT=true`：
- 仅支持 **用户名 + 密码** 登录
- 关闭 **注册/找回密码/微信登录/支付/运营看板**
- 仅管理员可在「用户管理」中：创建用户、重置密码、删除用户、编辑用户

### 5. License（机器码绑定 + 30天试用 + 续期）

- 首次启动自动进入试用期（默认 30 天，可用 `LICENSE_TRIAL_DAYS` 调整）
- 试用到期后系统会提示需要 license

#### 5.1 获取机器码/申请码

在私有化系统中访问：
- `GET /api/v1/system/license/machine-code`（管理员）
- `GET /api/v1/system/license/request`（管理员，返回 machine_code + request_code + 操作步骤）

#### 5.2 到官网申请续期

由于私有化环境通常不出网：
- 复制 `request_code` 到可联网环境
- 在跃云官网提交申请码
- 等待审批后获取 `license token`

#### 5.3 导入 license

管理员在系统中调用：
- `POST /api/v1/system/license/activate`（body: `{ "token": "..." }`）

> 注意：license token 需要使用跃云官方私钥签发（RS256）。

### 6. 内网大模型接口配置（优先级最高）

管理员可通过：
- `POST /api/v1/system/settings` 保存内网大模型信息（OpenAI兼容）

保存后系统会优先生效（覆盖 `.env`）。

