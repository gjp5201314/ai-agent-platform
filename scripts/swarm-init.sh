#!/bin/bash
# ============================================================
# AI Agent Platform - Swarm 初始化脚本（仅需执行一次）
# 在 Linux 服务器上执行: bash scripts/swarm-init.sh
# ============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================
# 1. 检查配置
# ============================================================
# 自适应路径: 如果在 scripts/ 下则退一级，否则当前目录
_SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)"
if [ "$(basename "$_SCRIPT_PATH")" = "scripts" ]; then
    SCRIPT_DIR="$(dirname "$_SCRIPT_PATH")"
else
    SCRIPT_DIR="$_SCRIPT_PATH"
fi
cd "$SCRIPT_DIR"

echo_info "工作目录: $SCRIPT_DIR"

# 检查 backend/.env 是否存在
if [ ! -f "backend/.env" ]; then
    echo_error "backend/.env 不存在！"
    echo_warn "请先: cp .env.example backend/.env 然后编辑填入 API Key"
    exit 1
fi

# 加载环境变量（用于 docker compose config 解析）
set -a
source backend/.env 2>/dev/null || true
# 生产覆盖
export POSTGRES_HOST="postgres"
export REDIS_HOST="redis"
export APP_DEBUG="false"
set +a

# 检查 ACR 配置
if [ -z "${ACR_REGISTRY}" ]; then
    echo_error "请在 backend/.env 中设置 ACR_REGISTRY"
    echo_warn "格式: ACR_REGISTRY=registry.cn-hangzhou.aliyuncs.com/YOUR_NAMESPACE"
    exit 1
fi

# ============================================================
# 2. 检查 Docker
# ============================================================
echo_info "检查 Docker..."
if ! command -v docker &> /dev/null; then
    echo_info "Docker 未安装，开始自动安装..."
    sudo rm -f /etc/apt/sources.list.d/kubernetes.list 2>/dev/null || true
    sudo sed -i '/kubernetes/s/^/#/' /etc/apt/sources.list 2>/dev/null || true
    sudo apt-get update -qq
    curl -fsSL https://get.docker.com | sh
    sudo systemctl start docker
    sudo systemctl enable docker
    echo_info "Docker 安装完成"
else
    echo_info "Docker 已安装: $(docker --version)"
fi

# ============================================================
# 3. 初始化 Swarm（如果还未初始化）
# ============================================================
if docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -q "active"; then
    echo_info "Swarm 已处于活跃状态"
else
    echo_info "初始化 Docker Swarm..."
    docker swarm init
    echo_info "Swarm 初始化完成"
fi

# ============================================================
# 4. 登录阿里云 ACR
# ============================================================
echo_info "登录阿里云容器镜像服务..."
if [ -n "${ACR_USERNAME}" ] && [ -n "${ACR_PASSWORD}" ]; then
    echo "${ACR_PASSWORD}" | docker login --username="${ACR_USERNAME}" --password-stdin "${ACR_REGISTRY%%/*}"
elif [ -n "${ACR_PASSWORD}" ]; then
    # 阿里云默认用户名: 阿里云账号的 RAM 子账号名称
    echo "${ACR_PASSWORD}" | docker login --password-stdin "${ACR_REGISTRY%%/*}"
else
    echo_warn "未设置 ACR_PASSWORD，跳过登录（如果本地已有登录状态则不影响）"
fi

# ============================================================
# 5. 拉取镜像（仅拉取，不构建）
# ============================================================
echo_info "拉取镜像..."
IMAGE_TAG="${IMAGE_TAG:-latest}"

docker pull "${ACR_REGISTRY}/backend:${IMAGE_TAG}" || {
    echo_error "backend 镜像不存在！"
    echo_warn "请在本地构建并推送: docker compose build && docker push ${ACR_REGISTRY}/backend:${IMAGE_TAG}"
    exit 1
}
echo_info "backend 镜像已拉取"

docker pull "${ACR_REGISTRY}/frontend:${IMAGE_TAG}" || {
    echo_error "frontend 镜像不存在！"
    echo_warn "请在本地构建并推送: docker compose build && docker push ${ACR_REGISTRY}/frontend:${IMAGE_TAG}"
    exit 1
}
echo_info "frontend 镜像已拉取"

# ============================================================
# 6. 部署 Stack
# ============================================================
echo_info "部署 Stack..."
STACK_NAME="${STACK_NAME:-ai-agent}"

# 确保根目录有 .env 软链接（Docker Stack Deploy 读变量需要）
if [ ! -f ".env" ] && [ -f "backend/.env" ]; then
    echo_info "创建 .env 软链接..."
    ln -sf backend/.env .env
fi

# 导出变量后直接部署（不要用 docker compose config 管道，会把端口转成字符串）
set -a; source .env 2>/dev/null || source backend/.env 2>/dev/null; set +a
docker stack deploy -c docker-compose.prod.yml "${STACK_NAME}"

echo_info "等待服务就绪..."
sleep 5

# 强制更新确保镜像被拉取
docker service update --force --image "${ACR_REGISTRY}/backend:${IMAGE_TAG}" "${STACK_NAME}_backend" 2>/dev/null || true
docker service update --force --image "${ACR_REGISTRY}/frontend:${IMAGE_TAG}" "${STACK_NAME}_frontend" 2>/dev/null || true

echo_info "等待服务就绪..."
sleep 5

# 等待 backend 就绪
for i in $(seq 1 15); do
    if curl -sf -X POST http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo_info "后端服务已就绪! (${i}/15)"
        break
    fi
    echo_info "等待中... (${i}/15)"
    sleep 5
done

# ============================================================
# 7. 输出信息
# ============================================================
echo ""
echo "=========================================="
echo -e "${GREEN}  Swarm 部署完成!${NC}"
echo "=========================================="
echo ""

docker service ls --filter "name=${STACK_NAME}"

PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ipinfo.io/ip 2>/dev/null || echo "YOUR_SERVER_IP")

echo ""
echo "访问地址:"
echo "  前端界面:  http://${PUBLIC_IP}"
echo "  API 文档:  http://${PUBLIC_IP}:8000/docs"
echo "  健康检查:  http://${PUBLIC_IP}:8000/api/v1/health (POST)"
echo ""
echo "常用命令:"
echo "  查看服务:  docker service ls"
echo "  查看日志:  docker service logs -f ${STACK_NAME}_backend"
echo "  滚动更新:  bash scripts/swarm-update.sh"
echo "  停止服务:  docker stack rm ${STACK_NAME}"
echo ""
