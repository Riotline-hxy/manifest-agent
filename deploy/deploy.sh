#!/usr/bin/env bash
# Deploy demo/ + config/ to the server. Run from the repo root:
#   bash deploy/deploy.sh
# - backs up the current app dir and data dir first (rollback: see bottom)
# - never ships .env, data/, tests, caches
# - keeps the server's demo/data symlink and /opt/manifest-agent/.env
set -euo pipefail

HOST="${DEPLOY_HOST:-ops11768@154.21.200.133}"
APP=/opt/manifest-agent
TS=$(date +%Y%m%d-%H%M%S)

echo "==> packing"
tar --exclude='demo/data' --exclude='demo/.env' --exclude='demo/tests' \
    --exclude='__pycache__' --exclude='*.pyc' \
    -czf /tmp/xianban-$TS.tgz demo config

echo "==> backup on server -> $APP/backup-$TS"
ssh "$HOST" "set -e; mkdir -p $APP/backup-$TS; cp -a $APP/app $APP/backup-$TS/app; cp -a $APP/data $APP/backup-$TS/data"

echo "==> upload + swap"
scp -q /tmp/xianban-$TS.tgz "$HOST:/tmp/"
ssh "$HOST" "set -e
  cd $APP
  rm -rf app.new && mkdir app.new && tar -xzf /tmp/xianban-$TS.tgz -C app.new
  ln -sfn ../../data app.new/demo/data
  rm -rf app.old && mv app app.old && mv app.new app
  sudo systemctl restart manifest-agent
  sleep 2
  systemctl is-active manifest-agent
  curl -fsS http://127.0.0.1:18765/api/health; echo
  rm -f /tmp/xianban-$TS.tgz"
rm -f /tmp/xianban-$TS.tgz

echo "==> public check"
curl -fsS https://manifest.noryx.cn/api/health; echo
echo "done. rollback: ssh $HOST 'cd $APP && rm -rf app && cp -a backup-$TS/app app && sudo systemctl restart manifest-agent'"
