## 离线镜像制作（在有网构建机执行）

目标：生成可在纯离线环境 `docker load` 的镜像包。

### 1) 构建后端镜像

在有网机器上（能访问 pypi/apt），进入后端 Dockerfile 所在目录：

```bash
cd /data/aiops_deploy_pkg/aiops

docker build -t aiops-backend:offline .
```

### 2) 拉取基础镜像

```bash
docker pull mysql:8.0
docker pull nginx:latest
```

### 3) 导出镜像 tar

```bash
mkdir -p offline/images

docker save -o offline/images/aiops-backend.offline.tar aiops-backend:offline
docker save -o offline/images/mysql.8.0.tar mysql:8.0
docker save -o offline/images/nginx.latest.tar nginx:latest
```

### 4) 将 offline/ 整体打包（建议放 GitHub Release）

```bash
tar -czf aiops-offline-bundle.tar.gz offline/
sha256sum aiops-offline-bundle.tar.gz > aiops-offline-bundle.tar.gz.sha256
```
