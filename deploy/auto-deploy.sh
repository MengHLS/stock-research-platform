#!/usr/bin/env bash
# 服务器端拉取式部署。
#
# 该 ECS 的安全组只放行少量来源 IP，GitHub Actions 的运行器无法入站 SSH，
# 因此改由服务器主动轮询 origin/dev：远端前进就部署对应的不可变镜像。
# 由 systemd timer 定时触发（见 deploy/systemd/），也可手工执行。
#
# 退出码：0 = 无需部署或部署成功；非 0 = 部署失败（deploy.sh 已尝试回滚）。

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

STATE_FILE="deploy/.state/current"
BRANCH="dev"

log() { echo "[auto-deploy] $*"; }

git fetch --prune origin "$BRANCH" --quiet

remote_sha="$(git rev-parse "origin/$BRANCH")"
deployed_sha="$(cat "$STATE_FILE" 2>/dev/null || true)"

if [[ "$remote_sha" == "$deployed_sha" ]]; then
  log "无变化：origin/$BRANCH 仍为 ${remote_sha:0:7}"
  exit 0
fi

log "检测到新提交：${deployed_sha:0:7} -> ${remote_sha:0:7}"

# 只更新部署脚本与编排；deploy/.env 与 .state 被 Git 忽略，不受影响。
git reset --hard "$remote_sha" --quiet

# 镜像由 GitHub Actions 构建推送，可能存在构建尚未完成的短暂窗口；
# deploy.sh 的 pull 失败会直接返回非 0，下一轮定时任务会重试。
bash deploy/deploy.sh --tag "$remote_sha"
