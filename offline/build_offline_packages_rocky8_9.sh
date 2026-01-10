#!/usr/bin/env bash
set -euo pipefail
# 在有网 Rocky/Alma/RHEL 8/9 构建机执行：下载 docker-ce + compose-plugin rpm 及依赖到 offline/packages/rocky

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT_DIR/packages/rocky"
mkdir -p "$OUT"

sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf makecache

PKGS=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin)

# 使用 dnf download --resolve 拉全依赖
sudo dnf download --resolve --alldeps --downloaddir="$OUT" "${PKGS[@]}" || true

(cd "$OUT" && sha256sum *.rpm > SHA256SUMS.txt)

echo "OK: packages saved to $OUT"
