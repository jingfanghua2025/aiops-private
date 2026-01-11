# 跃云 AIOps+ 私有化一键部署（offline/）

本目录用于**私有化离线/内网**交付，目标是：在目标机解压到 `/opt/aiops/offline` 后，执行一条命令完成部署与自检。

## 目录说明

- `install.sh`：一键部署入口（Docker）
- `verify.sh`：验收脚本（健康检查/私有化标志/License 状态）
- `uninstall.sh`：卸载（容器 + 数据卷）
- `docker-compose.yml`：编排（backend/mysql/nginx）
- `nginx/conf.d/default.conf`：Nginx 反代配置
- `config/aiops.env.example`：业务环境变量模板（**不要提交真实密钥**）
- `.env.example`：Docker compose 侧环境变量模板（MySQL root 密码等）
- `patches/`：交付补丁（用于覆盖容器内代码）
- `static/`：控制台静态文件（含 `private_deploy_patch.js`）
- `images/`：**可选**离线镜像包（建议放 Release 或 Git LFS，不要直接进 Git）

## 一键部署（Docker）

在目标机（已安装 Docker + docker compose）：

### 方式A（推荐）：从 GitHub Release 下载“全量离线包”并一键部署

> 这是真正的“一条命令搞定”：离线包里**自带所有镜像**（backend/mysql/nginx）+ `offline/` 一键脚本。

```bash
cd /tmp
git clone git@github.com:jingfanghua2025/aiops-private.git
cd aiops-private
git checkout private-deploy

chmod +x ./offline/install_from_release.sh
GH_TOKEN=xxxx sudo -E ./offline/install_from_release.sh --tag latest
```

## 交付方：制作并上传 latest Release（包含所有镜像）

在交付机（能访问镜像仓库、能 docker pull/构建）：

```bash
# 1) 确保镜像存在（backend/mysql/nginx）
docker image ls | grep -E 'aiops-backend|mysql|nginx'

# 2) 生成全量离线包（会 docker save 镜像到 bundle 内）
chmod +x ./offline/release/make_offline_bundle.sh
./offline/release/make_offline_bundle.sh

# 3) 生成 sha256（可选但推荐）
sha256sum ./aiops-offline-bundle.tar.gz > ./aiops-offline-bundle.tar.gz.sha256

# 4) 上传到 GitHub Release（tag=latest）
chmod +x ./offline/release/upload_latest.sh
export GH_TOKEN=xxxx
./offline/release/upload_latest.sh ./aiops-offline-bundle.tar.gz
```

### 方式B：已拿到 offline/ 目录（不含镜像包），在目标机本地一键部署

```bash
cd /opt/aiops/offline
cp .env.example .env
cp config/aiops.env.example config/aiops.env

# 1) 修改密码/密钥（必做）
vi .env
vi config/aiops.env

# 2) 离线镜像（GitHub Release 获取，推荐）
# 私有仓库请带 GH_TOKEN；资产文件名默认：aiops-offline-images.tar.gz
chmod +x ./download_release.sh
GH_TOKEN=xxxx ./download_release.sh --tag latest

# 3) 一键部署
sudo ./install.sh
```

访问：`http://<server_ip>/`

## 大文件交付（镜像/离线依赖）

为避免 GitHub 仓库膨胀：

- **镜像离线包**：放在 GitHub Release 或 Git LFS（`offline/images/*.tar*`）
- **原生部署 wheelhouse/app.tar.gz**：同上（`offline/native/`）
- **密钥文件**：不要进仓库（`keys/*.pem`），现场导入或通过管理员控制台上传公钥

