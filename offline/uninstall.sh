#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found"
  exit 0
fi

if docker compose version >/dev/null 2>&1; then
  docker compose down -v --remove-orphans || true
else
  docker-compose down -v --remove-orphans || true
fi

echo "OK: uninstalled (containers + volumes removed)"

