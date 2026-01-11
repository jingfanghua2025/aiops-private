#!/usr/bin/env bash
set -euo pipefail

# 真正“一键部署”：
# 1) 从 GitHub Release 下载全量离线包（包含 offline/ + images/）
# 2) 解压到 /opt/aiops/offline
# 3) 自动执行 /opt/aiops/offline/install.sh
#
# 用法：
#   GH_TOKEN=xxx ./install_from_release.sh --tag latest
#   GH_TOKEN=xxx ./install_from_release.sh --tag v1.2.3
#
# 可选：
#   --repo org/repo
#   --bundle aiops-offline-bundle.tar.gz
#   --dest /opt/aiops

REPO="jingfanghua2025/aiops-private"
TAG="latest"
BUNDLE="aiops-offline-bundle.tar.gz"
DEST="/opt/aiops"

usage() {
  cat <<'USAGE'
Usage:
  ./install_from_release.sh [--repo org/repo] [--tag <tag|latest>] [--bundle <name>] [--dest <dir>]

Env:
  GH_TOKEN: GitHub token（私有仓库必需）

Example:
  GH_TOKEN=xxx sudo -E ./install_from_release.sh --tag latest
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2;;
    --tag) TAG="${2:-}"; shift 2;;
    --bundle) BUNDLE="${2:-}"; shift 2;;
    --dest) DEST="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2;;
  esac
done

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl 未安装" >&2
  exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
  echo "ERROR: tar 未安装" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker 未安装（请先安装 Docker + docker compose）" >&2
  exit 1
fi

API_BASE="https://api.github.com"
REL_URL=""
if [[ "$TAG" == "latest" ]]; then
  REL_URL="$API_BASE/repos/$REPO/releases/latest"
else
  REL_URL="$API_BASE/repos/$REPO/releases/tags/$TAG"
fi

AUTH_HEADER=()
if [[ -n "${GH_TOKEN:-}" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${GH_TOKEN}")
fi

echo "[+] query release: repo=$REPO tag=$TAG"
REL_JSON="$(curl -fsSL "${AUTH_HEADER[@]}" -H "Accept: application/vnd.github+json" "$REL_URL")"

DOWNLOAD_URL="$(printf '%s' "$REL_JSON" | grep -Eo '\"browser_download_url\"\\s*:\\s*\"[^\"]+\"' | sed -E 's/.*\"([^\"]+)\"/\\1/' | grep -F "/$BUNDLE" | head -n1 || true)"
if [[ -z "$DOWNLOAD_URL" ]]; then
  echo "ERROR: 未找到 Release 资产：$BUNDLE" >&2
  echo "请先在 GitHub Release 上传该文件，或用 --bundle 指定正确文件名。" >&2
  exit 1
fi

sudo mkdir -p "$DEST"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

OUT="$TMP/$BUNDLE"
echo "[+] download bundle: $BUNDLE"
curl -fL "${AUTH_HEADER[@]}" -o "$OUT" "$DOWNLOAD_URL"

echo "[+] extract -> $DEST/"
sudo tar -xzf "$OUT" -C "$DEST"

if [[ ! -d "$DEST/offline" ]]; then
  echo "ERROR: 解压后未发现 $DEST/offline （bundle 内容不符合约定）" >&2
  exit 1
fi

echo "[+] run one-click installer"
sudo bash -lc "cd '$DEST/offline' && chmod +x ./install.sh ./verify.sh ./uninstall.sh && ./install.sh && ./verify.sh"

echo
echo "OK: 已完成下载 + 部署。访问 http://<server_ip>/"

