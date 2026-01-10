## 跃云 AIOps 私有化离线部署仓库（Ubuntu/CentOS 适配）

本仓库用于**纯离线环境**的私有化一键部署：
- 支持 **Ubuntu / CentOS(RHEL系)**
- 离线镜像 `docker load` + `docker compose up -d`
- 后台可配置内网大模型接口（保存后优先生效）
- 支持机器码试用期（默认 30 天）+ 到期导入 license

### 目录结构

- `offline/`：离线一键部署
  - `install.sh`：一键安装/启动/健康检查
  - `uninstall.sh`：卸载
  - `docker-compose.yml`：离线编排（使用预构建镜像，不走 build）
  - `images/`：离线镜像 tar（建议放 Release 或 Git LFS）
  - `packages/ubuntu/`：docker/compose 的 deb 离线包
  - `packages/centos/`：docker/compose 的 rpm 离线包
  - `config/aiops.env.example`：配置模板（不要提交真实 .env）

### 使用（离线机器上）

```bash
cd offline
sudo ./install.sh
```

### 关于 GitHub 大文件

离线镜像/离线包通常很大，不建议直接普通 git push：
- 推荐：使用 **GitHub Releases** 上传 `aiops-offline-bundle.tar.gz`
- 或启用 **Git LFS** 跟踪 `offline/images/*.tar` 与 `offline/packages/**`

### 安全

- 不要提交 `.env`、任何私钥/证书、数据库真实 dump。
