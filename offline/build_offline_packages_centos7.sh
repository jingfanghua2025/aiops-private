#!/usr/bin/env bash
set -euo pipefail
# 在有网 CentOS 7 构建机执行：下载 docker-ce & docker-compose 相关 rpm 及依赖到 offline/packages/centos7

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT_DIR/packages/centos7"
mkdir -p "$OUT"

sudo yum install -y yum-utils yum-plugin-downloadonly || true
sudo yum install -y yum-utils

sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum makecache fast

# CentOS7 上通常使用 docker-ce + docker-ce-cli + containerd.io
# compose-plugin 在 7 上可能不可用/依赖多，建议用 docker-compose v2 二进制或 python 版；这里先下载 docker-compose(1.x) rpm (如果仓库无则改用二进制)
PKGS=(docker-ce docker-ce-cli containerd.io)

# 下载包及依赖
sudo yum install -y --downloadonly --downloaddir="$OUT" "${PKGS[@]}" || true

# 尝试下载 docker-compose（若仓库无就跳过）
sudo yum install -y --downloadonly --downloaddir="$OUT" docker-compose || true

(cd "$OUT" && sha256sum *.rpm > SHA256SUMS.txt)

echo "OK: packages saved to $OUT"
