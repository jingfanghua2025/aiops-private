#!/usr/bin/env bash
set -euo pipefail
# 在有网 Ubuntu/Debian 构建机执行：下载 docker + compose 插件及其依赖到 offline/packages/ubuntu

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT_DIR/packages/ubuntu"
mkdir -p "$OUT"

# 需要 apt-utils / apt-rdepends
sudo apt-get update
sudo apt-get install -y apt-rdepends ca-certificates curl gnupg

# docker 官方仓库
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

. /etc/os-release
ARCH=$(dpkg --print-architecture)
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update

# 目标包（可按需调整版本）
PKGS=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin)

# 下载包本体
apt-get download "${PKGS[@]}" -o=dir::cache="$OUT" || true

# 下载依赖（尽量全）
for p in "${PKGS[@]}"; do
  apt-rdepends "$p" | awk '/^\w/{print $1}' | sort -u | while read -r dep; do
    apt-get download "$dep" -o=dir::cache="$OUT" || true
  done
done

# 把当前目录下的 .deb 都归集
find . -maxdepth 1 -type f -name '*.deb' -exec mv -f {} "$OUT" \; 2>/dev/null || true

# 生成校验
(cd "$OUT" && sha256sum *.deb > SHA256SUMS.txt)

echo "OK: packages saved to $OUT"
