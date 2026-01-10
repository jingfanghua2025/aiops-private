#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="docker"

usage(){
  cat <<USAGE
用法：
  sudo ./install.sh --mode docker   # 全 docker-compose 离线部署（默认）
  sudo ./install.sh --mode native  # 原生部署（systemd + venv），不依赖 docker
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "未知参数：$1"; usage; exit 1;;
  esac
done

case "$MODE" in
  docker)
    exec "$ROOT_DIR/install_docker.sh";;
  native)
    exec "$ROOT_DIR/native/install_native.sh";;
  *)
    echo "不支持的 mode：$MODE"; usage; exit 1;;
 esac
