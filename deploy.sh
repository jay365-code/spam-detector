#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== [1/4] git pull ==="
git -C "$ROOT" pull

echo "=== [2/4] 프론트엔드 빌드 ==="
cd "$ROOT/frontend"
npm install --silent
npm run build

echo "=== [3/4] 서버 재시작 ==="
pkill -f "python run.py" 2>/dev/null || true
sleep 1

mkdir -p "$ROOT/logs"
cd "$ROOT/backend"
nohup python run.py > "$ROOT/logs/server.log" 2>&1 &
echo "PID: $!"

echo "=== [4/4] 기동 확인 (10초 대기) ==="
sleep 10
tail -5 "$ROOT/logs/server.log"

echo ""
echo "=== 배포 완료 ==="
