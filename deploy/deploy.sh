#!/usr/bin/env bash
# 服务器端部署入口（阿里云 ECS）。
#
# 只做三件事：拉取已构建好的不可变镜像、迁移数据库、滚动启动并验证健康；
# 失败自动回滚到上一版。不在服务器上构建，也不依赖本地开发模板。
#
# 用法：
#   ./deploy.sh --tag <commit-sha>     部署指定镜像标签
#   ./deploy.sh --rollback             回到上一版（deploy/.state/previous）
#   ./deploy.sh --help
#
# 前提：同目录存在 deploy/.env（由 env.server.example 复制并填写），
# 且 docker、curl 可用；镜像仓库为 GHCR，CI 会通过 stdin 预先登录，
# 手工部署则在 .env 里提供 GHCR_USERNAME / GHCR_PASSWORD 或事先 docker login。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE=".env"
COMPOSE_FILE="compose.server.yaml"
STATE_DIR=".state"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-150}"

TAG=""
ROLLBACK_ONLY=0

usage() {
  cat <<'EOF'
用法: deploy.sh --tag <commit-sha> [--health-timeout 150]
      deploy.sh --rollback [--health-timeout 150]

  --tag              要部署的镜像标签（GitHub Actions 使用提交 SHA）
  --rollback         回滚到上一版，不做新部署
  --health-timeout   等待 /health/ready 的秒数（默认 150）
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      [[ $# -ge 2 ]] || { echo "--tag 需要一个值" >&2; exit 2; }
      TAG="$2"
      shift 2
      ;;
    --rollback)
      ROLLBACK_ONLY=1
      shift
      ;;
    --health-timeout)
      [[ $# -ge 2 ]] || { echo "--health-timeout 需要一个值" >&2; exit 2; }
      HEALTH_TIMEOUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

die() { echo "错误: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "未找到 docker"
docker compose version >/dev/null 2>&1 || die "未找到 docker compose 插件"
command -v curl >/dev/null 2>&1 || die "未找到 curl（健康检查需要）"

[[ -f "$ENV_FILE" ]] || die "缺少 deploy/.env，请从 deploy/env.server.example 复制并填写"

# 加载部署变量。文件内含密钥，权限必须收紧。
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

require_var() {
  local name="$1"
  [[ -n "${!name:-}" ]] || die "deploy/.env 缺少 $name"
}

for var in IMAGE_PREFIX MYSQL_PASSWORD RP_AUTH__SECRET; do
  require_var "$var"
done

env_perms="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo 600)"
# 组权限与其他用户权限都必须为 0（600/400 才算安全）。
if [[ "${env_perms: -2}" != "00" ]]; then
  echo "警告: deploy/.env 对组或其他用户可读（当前 $env_perms），建议 chmod 600 deploy/.env" >&2
fi

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

compose() { docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"; }

web_port="${RP_WEB_PORT:-8080}"
ready_url="http://127.0.0.1:${web_port}/health/ready"

image_for() {
  local name="$1" tag="$2"
  echo "${IMAGE_PREFIX}/${name}:${tag}"
}

wait_for_ready() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 5 "$ready_url" >/dev/null 2>&1; then
      echo "健康检查通过: $ready_url"
      return 0
    fi
    sleep 3
  done
  echo "健康检查超时: $ready_url" >&2
  return 1
}

deploy_tag() {
  local tag="$1"
  export RP_IMAGE_API RP_IMAGE_WEB
  RP_IMAGE_API="$(image_for research-platform-api "$tag")"
  RP_IMAGE_WEB="$(image_for research-platform-web "$tag")"

  echo "==> 部署镜像标签: ${tag}"
  compose pull || return 1

  # 迁移在应用启动前单独执行：容器启动/退出不跑迁移，避免并发与不可预期 DDL。
  echo "==> 执行数据库迁移"
  compose run --rm --no-deps api alembic -c backend/alembic.ini upgrade head || return 1

  echo "==> 启动 api / worker / web"
  compose up -d || return 1

  echo "==> 等待健康检查（最长 ${HEALTH_TIMEOUT}s）"
  wait_for_ready || return 1
  return 0
}

login_registry() {
  if [[ -n "${GHCR_USERNAME:-}" && -n "${GHCR_PASSWORD:-}" ]]; then
    local registry="${IMAGE_PREFIX%%/*}"
    echo "==> 登录镜像仓库 ${registry}"
    printf '%s' "$GHCR_PASSWORD" | docker login "$registry" \
      --username "$GHCR_USERNAME" --password-stdin >/dev/null \
      || die "镜像仓库登录失败，检查 GHCR_USERNAME / GHCR_PASSWORD"
  else
    echo "==> 跳过镜像仓库登录（CI 已通过 stdin 登录，或镜像为公开包）"
  fi
}

read_state() {
  local file="$1"
  [[ -f "$file" ]] && cat "$file" || true
}

write_state() {
  local file="$1" tag="$2"
  printf '%s\n' "$tag" > "$file"
}

login_registry

if (( ROLLBACK_ONLY )); then
  previous="$(read_state "$STATE_DIR/previous")"
  [[ -n "$previous" ]] || die "没有可回滚的版本（$STATE_DIR/previous 为空）"
  echo "==> 回滚到 $previous"
  deploy_tag "$previous" || die "回滚失败，需人工介入"
  write_state "$STATE_DIR/current" "$previous"
  echo "回滚完成: $previous"
  exit 0
fi

[[ -n "$TAG" ]] || { usage >&2; exit 2; }

current="$(read_state "$STATE_DIR/current")"

if deploy_tag "$TAG"; then
  if [[ -n "$current" && "$current" != "$TAG" ]]; then
    write_state "$STATE_DIR/previous" "$current"
  fi
  write_state "$STATE_DIR/current" "$TAG"
  echo "部署完成: $TAG"
  exit 0
fi

echo "==> 部署失败，收集现场" >&2
compose ps >&2 || true
compose logs --tail=80 api >&2 || true

if [[ -z "$current" || "$current" == "$TAG" ]]; then
  die "部署失败且没有可回滚的上一版"
fi

echo "==> 自动回滚到 $current" >&2
if deploy_tag "$current"; then
  write_state "$STATE_DIR/current" "$current"
  die "新版本 $TAG 部署失败，已回滚到 $current"
fi

die "新版本失败且回滚失败，需人工介入"
