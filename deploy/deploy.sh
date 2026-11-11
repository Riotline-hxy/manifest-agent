#!/usr/bin/env bash
# Deploy demo/ + config/ to the server. Run from the repo root:
#   bash deploy/deploy.sh
# - backs up the current app dir and data dir first (rollback: see bottom); the data backup is made with
#   demo/backup.py (SQLite online backup, consistent while the service is running; photos are skipped)
# - never ships .env, data/, tests, caches
# - keeps the server's demo/data symlink and /opt/manifest-agent/.env
# - does NOT reinstall deploy/manifest-agent.service; after changing it:
#     scp deploy/manifest-agent.service $HOST:/tmp/ && ssh $HOST 'sudo cp /tmp/manifest-agent.service \
#       /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart manifest-agent'
set -euo pipefail

HOST="${DEPLOY_HOST:-ops11768@154.21.200.133}"
APP=/opt/manifest-agent
TS=$(date +%Y%m%d-%H%M%S)

echo "==> packing"
tar --exclude='demo/data' --exclude='demo/.env' --exclude='demo/tests' \
    --exclude='__pycache__' --exclude='*.pyc' \
    -czf /tmp/xianban-$TS.tgz demo config

ROLLBACK="ssh $HOST 'cd $APP && rm -rf app && cp -a backup-$TS/app app && sudo systemctl restart manifest-agent'"

echo "==> upload + unpack"
scp -q /tmp/xianban-$TS.tgz "$HOST:/tmp/"
ssh "$HOST" "set -e
  cd $APP
  rm -rf app.new && mkdir app.new && tar -xzf /tmp/xianban-$TS.tgz -C app.new
  rm -f /tmp/xianban-$TS.tgz"
rm -f /tmp/xianban-$TS.tgz

echo "==> backup on server -> $APP/backup-$TS"
# 服务这时还在跑、库开着 WAL：直接拷 .db 文件可能拷到写了一半的状态，备份就恢复不出来。
# 用新版本带的 demo/backup.py（SQLite 的在线备份接口 + 完整性检查）；它退出码不是 0 就停在这里，不往下换版本。
# 照片（u/<uid>/photos）不在这份备份里：它们只增删、不会被改；要连照片一起备份，在服务器上加 --photos 单独跑。
ssh "$HOST" "set -e
  cd $APP
  mkdir -p backup-$TS
  cp -a app backup-$TS/app
  python3 app.new/demo/backup.py $APP/data $APP/backup-$TS/data"

echo "==> swap（下面任何一步出错，回滚：$ROLLBACK）"
ssh "$HOST" "set -e
  cd $APP
  ln -sfn ../../data app.new/demo/data
  rm -rf app.old && mv app app.old && mv app.new app
  sudo systemctl restart manifest-agent
  sleep 2
  systemctl is-active manifest-agent
  curl -fsS http://127.0.0.1:18765/api/health; echo"

echo "==> public check"
curl -fsS https://manifest.noryx.cn/api/health; echo
echo "done. rollback: $ROLLBACK"
echo "数据要恢复到这次部署前：先停服务，再把 $APP/backup-$TS/data 里的文件拷回 $APP/data（照片不在备份里，不用动）。"
