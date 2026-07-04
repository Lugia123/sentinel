#!/usr/bin/env bash
# Sentinel 本地开发一键启动:引擎生成快照 → Go 后端 → React 前端
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${SENTINEL_PYTHON:-/Users/lugia/lugia_fc/TradingAgents/.venv/bin/python}"

echo "① 引擎生成今日快照(含 SY,首次较慢)…"
(cd "$ROOT/engine" && "$PYTHON" run_daily.py --asof latest)

echo "② 启动 Go 后端 :8787 …"
(cd "$ROOT/server" && go run ./cmd/server) &
SRV=$!
trap "kill $SRV 2>/dev/null" EXIT
sleep 2

echo "③ 启动 React 前端 :5173 …"
cd "$ROOT/client"
[ -d node_modules ] || npm install
npm run dev
