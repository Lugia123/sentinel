#!/usr/bin/env bash
# Sentinel 本地开发一键启动
#   前置:Python(装 pandas/numpy/pyarrow/baostock 的解释器)、Go、Node、Docker(PostgreSQL 容器)
#   流程:检查依赖 → 确保 PG 容器+sentinel库 → 清端口 → 起后端(自动迁移)
#         → 首次自动生成快照 → 起前端;Ctrl+C 干净退出
#   可用环境变量覆盖:SENTINEL_PYTHON / SENTINEL_PORT / SENTINEL_PG_CONTAINER / SENTINEL_DB_USER
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${SENTINEL_PYTHON:-python3}"
BACKEND_PORT="${SENTINEL_PORT:-8787}"
FRONTEND_PORT=5173
PG_CONTAINER="${SENTINEL_PG_CONTAINER:-sentinel-postgres}"
PG_HOST_PORT="${SENTINEL_PG_PORT:-5432}"
DB_NAME=sentinel
DB_USER="${SENTINEL_DB_USER:-sentinel}"

say() { printf "\033[1;34m▸ %s\033[0m\n" "$*"; }
die() { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

# ── 0. 依赖检查 ──
command -v go   >/dev/null || die "未装 Go"
command -v node >/dev/null || die "未装 Node"
command -v docker >/dev/null || die "未装 Docker"
command -v "$PYTHON" >/dev/null || [ -x "$PYTHON" ] || die "Python 解释器不存在: $PYTHON(设 SENTINEL_PYTHON 覆盖)"
[ -f "$ROOT/server/.env" ] || {
  say "未找到 server/.env,从 .env.example 复制(请填 DB 密码后重跑)"
  cp "$ROOT/server/.env.example" "$ROOT/server/.env"
  die "已生成 server/.env —— 填入数据库密码等后再启动"
}

# ── 1. 确保 PG 容器运行 + sentinel 库存在 ──
if ! docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
  say "启动 PG 容器 ${PG_CONTAINER}"
  docker start "$PG_CONTAINER" >/dev/null || die "无法启动容器 ${PG_CONTAINER}"
  sleep 2
fi
if ! docker exec "$PG_CONTAINER" psql -U "$DB_USER" -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "$DB_NAME"; then
  say "建 ${DB_NAME} 库"
  docker exec "$PG_CONTAINER" createdb -U "$DB_USER" "$DB_NAME" || die "建库失败"
fi
say "PG 就绪(容器 ${PG_CONTAINER}:${PG_HOST_PORT} 库 ${DB_NAME})"

# ── 2. 清理端口 ──
for p in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  lsof -ti ":$p" 2>/dev/null | xargs kill -9 2>/dev/null || true
done

# ── 3. 起后端(自动连库+迁移)──
say "启动 Go 后端 :${BACKEND_PORT}"
( cd "$ROOT/server" && go run ./cmd/server ) &
BACKEND_PID=$!
cleanup() {
  say "关闭…"
  kill "$BACKEND_PID" 2>/dev/null || true
  lsof -ti ":$BACKEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 等后端就绪
for i in $(seq 1 30); do
  curl -sf "http://localhost:${BACKEND_PORT}/api/health" >/dev/null 2>&1 && break
  [ "$i" = 30 ] && die "后端启动超时(看上方日志,多半是 DB 连接失败)"
  sleep 1
done
say "后端就绪:$(curl -s http://localhost:${BACKEND_PORT}/api/version)"

# ── 4. 首次无快照则生成一份 ──
if ! curl -sf "http://localhost:${BACKEND_PORT}/api/snapshot" >/dev/null 2>&1; then
  say "库中无快照,首次生成(含 SY,约 30s)…"
  curl -s -X POST "http://localhost:${BACKEND_PORT}/api/run" >/dev/null || say "生成失败,可到页面点“刷新快照”重试"
fi

# ── 5. 起前端 ──
say "启动 React 前端 :${FRONTEND_PORT}"
cd "$ROOT/client"
[ -d node_modules ] || { say "首次安装前端依赖…"; npm install; }
say "打开 http://localhost:${FRONTEND_PORT}"
npm run dev
