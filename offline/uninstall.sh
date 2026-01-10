#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if docker compose version >/dev/null 2>&1; then
  (cd "$ROOT_DIR" && docker compose down -v)
else
  (cd "$ROOT_DIR" && docker-compose down -v)
fi
echo "已卸载（包含卷）"
