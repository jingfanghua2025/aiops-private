#!/usr/bin/env bash
set -euo pipefail

# 在有网构建机执行：
# - 打包 app 代码到 offline/native/app.tar.gz
# - 下载 requirements wheel 到 offline/native/wheelhouse

AIOPS_SRC="${1:-/data/aiops}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFLINE_DIR="$(cd "$ROOT_DIR/.." && pwd)"

mkdir -p "$ROOT_DIR/wheelhouse"

# 1) 打包 app
TMP="$ROOT_DIR/.tmp_app"
rm -rf "$TMP" && mkdir -p "$TMP"
rsync -a --delete "$AIOPS_SRC/" "$TMP/" \
  --exclude '.git' --exclude 'logs' --exclude '__pycache__' --exclude 'opsgpt.db' --exclude '*.log'

tar -czf "$ROOT_DIR/app.tar.gz" -C "$TMP" .
rm -rf "$TMP"

# 2) 下载 wheels
python3 -m pip download -r "$AIOPS_SRC/requirements.txt" -d "$ROOT_DIR/wheelhouse"

# 3) 校验
(cd "$ROOT_DIR" && sha256sum app.tar.gz > app.tar.gz.sha256)
(cd "$ROOT_DIR/wheelhouse" && sha256sum * > SHA256SUMS.txt)

echo "OK: generated $ROOT_DIR/app.tar.gz and wheelhouse/"
