#!/bin/bash
# ============================================================
# AI Agent Platform - 滚动更新脚本
# 用法: bash scripts/swarm-update.sh [IMAGE_TAG]
# 示例: bash scripts/swarm-update.sh v1.2.0
#       bash scripts/swarm-update.sh（默认用 latest）
# ============================================================
# 该脚本实现零停机滚动更新：
#   1. 拉取新镜像
#   2. docker service update --image 触发 Swarm 滚动更新
#   3. Swarm 自动: 启新实例 → 健康检查通过 → 停旧实例（逐个）
# ============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

IMAGE_TAG="${1:-latest}"
STACK_NAME="${STACK_NAME:-ai-agent}"

# 加载环境变量
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ -f "backend/.env" ]; then
    set -a
    source backend/.env 2>/dev/null || true
    set +a
fi

if [ -z "${ACR_REGISTRY}" ]; then
    echo_error "ACR_REGISTRY 未设置，请在 backend/.env 中配置"
    echo_warn "格式: ACR_REGISTRY=registry.cn-hangzhou.aliyuncs.com/YOUR_NAMESPACE"
    exit 1
fi

echo_info "使用镜像 Tag: ${IMAGE_TAG}"
echo_info "仓库: ${ACR_REGISTRY}"

# ============================================================
# 1. 登录 ACR
# ============================================================
if [ -n "${ACR_PASSWORD}" ]; then
    echo_info "登录 ACR..."
    if [ -n "${ACR_USERNAME}" ]; then
        echo "${ACR_PASSWORD}" | docker login --username="${ACR_USERNAME}" --password-stdin "${ACR_REGISTRY%%/*}" > /dev/null 2>&1
    else
        echo "${ACR_PASSWORD}" | docker login --password-stdin "${ACR_REGISTRY%%/*}" > /dev/null 2>&1
    fi
fi

# ============================================================
# 2. 拉取新镜像
# ============================================================
echo_info "拉取 backend:${IMAGE_TAG}..."
docker pull "${ACR_REGISTRY}/backend:${IMAGE_TAG}"

echo_info "拉取 frontend:${IMAGE_TAG}..."
docker pull "${ACR_REGISTRY}/frontend:${IMAGE_TAG}"

# ============================================================
# 3. 滚动更新 backend（零停机）
# ============================================================
echo_info "========================================="
echo_info "开始滚动更新 backend（零停机）..."
echo_info "========================================="

docker service update \
    --image "${ACR_REGISTRY}/backend:${IMAGE_TAG}" \
    --update-parallelism 1 \
    --update-delay 10s \
    --update-order start-first \
    --update-failure-action rollback \
    --update-monitor 20s \
    "${STACK_NAME}_backend"

echo_info "等待 backend 滚动更新完成..."
# 监控更新进度
for i in $(seq 1 60); do
    UPDATE_STATE=$(docker service inspect "${STACK_NAME}_backend" --format '{{.UpdateStatus.State}}' 2>/dev/null || echo "unknown")

    case "${UPDATE_STATE}" in
        "completed")
            echo_info "backend 滚动更新完成!"
            break
            ;;
        "paused")
            echo_info "更新已暂停，可能是健康检查未通过"
            echo_info "运行: docker service inspect ${STACK_NAME}_backend"
            break
            ;;
        "rollback_completed")
            echo_error "backend 更新失败，已自动回滚！"
            break
            ;;
        *)
            echo_info "更新中... (${i}/60) 状态: ${UPDATE_STATE}"
            sleep 3
            ;;
    esac
done

# ============================================================
# 4. 更新 frontend
# ============================================================
echo_info "========================================="
echo_info "更新 frontend..."
echo_info "========================================="

docker service update \
    --image "${ACR_REGISTRY}/frontend:${IMAGE_TAG}" \
    --update-order start-first \
    --update-failure-action rollback \
    "${STACK_NAME}_frontend"

# ============================================================
# 5. 验证
# ============================================================
echo_info "验证服务..."

# 后端健康检查
sleep 5
if curl -sf -X POST http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo_info "后端健康检查: OK"
else
    echo_warn "后端健康检查: FAIL（可能还在启动中）"
fi

# 前端检查
if curl -sf http://localhost:80/ > /dev/null 2>&1; then
    echo_info "前端健康检查: OK"
else
    echo_warn "前端健康检查: FAIL"
fi

# ============================================================
# 6. 清理旧镜像
# ============================================================
echo_info "清理旧镜像..."
docker image prune -f

echo ""
echo "=========================================="
echo -e "${GREEN}  滚动更新完成!${NC}"
echo "=========================================="
echo ""
docker service ls --filter "name=${STACK_NAME}"
echo ""
echo "当前镜像标签: ${IMAGE_TAG}"
echo ""
