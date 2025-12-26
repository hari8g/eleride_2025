#!/usr/bin/env bash
set -euo pipefail

# Local dev runner:
# - Starts backend dependencies + API via docker compose
# - Starts all Vite apps with API base pointing to localhost
#
# URLs:
# - API docs: http://localhost:18080/docs
# - Rider app: http://localhost:5176
# - Fleet portal: http://localhost:5177
# - Financing portal: http://localhost:5178
# - Maintenance tech: http://localhost:5179
# - Matchmaking portal: http://localhost:5180

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:18080}"
export ELERIDE_ENV_FILE="${ELERIDE_ENV_FILE:-./env.localhost}"
export ELERIDE_COMPOSE_BUILD="${ELERIDE_COMPOSE_BUILD:-0}"

echo "Using VITE_API_BASE_URL=$VITE_API_BASE_URL"
echo "Using ELERIDE_ENV_FILE=$ELERIDE_ENV_FILE"
echo "Starting docker compose (postgres, redis, platform-api) ..."
if [ "$ELERIDE_COMPOSE_BUILD" = "1" ]; then
  docker compose up --build -d
else
  docker compose up -d
fi

ensure_deps () {
  local app_dir="$1"
  if [ ! -d "$ROOT_DIR/$app_dir/node_modules" ]; then
    echo "Installing deps for $app_dir ..."
    npm --prefix "$app_dir" ci
  fi
}

echo "Ensuring frontend deps are installed ..."
ensure_deps apps/rider-app
ensure_deps apps/fleet-portal
ensure_deps apps/financing-portal
ensure_deps apps/maintenance-tech
ensure_deps apps/matchmaking-portal

echo "Starting Vite dev servers ..."
trap 'echo; echo "Stopping..."; kill 0' INT TERM

npm --prefix apps/rider-app run dev &
npm --prefix apps/fleet-portal run dev &
npm --prefix apps/financing-portal run dev &
npm --prefix apps/maintenance-tech run dev &
npm --prefix apps/matchmaking-portal run dev &

wait


