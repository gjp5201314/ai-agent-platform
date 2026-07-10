#!/bin/bash
# ============================================================
# AI Agent Platform - 一键部署脚本
# 在 Linux 服务器上执行: bash deploy.sh
# ============================================================
set -e

PROJECT_DIR="ai-agent-platform"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---- 1. 检查 Docker ----
echo_info "检查 Docker..."
if ! command -v docker &> /dev/null; then
    echo_info "Docker 未安装，开始自动安装..."

    # 清理可能导致 apt-get update 失败的第三方源
    echo_info "清理可能冲突的第三方 apt 源..."
    sudo rm -f /etc/apt/sources.list.d/kubernetes.list 2>/dev/null || true
    sudo rm -f /etc/apt/sources.list.d/apt.kubernetes.io.list 2>/dev/null || true
    # 注释掉 sources.list 中的 kubernetes 行
    sudo sed -i '/kubernetes/s/^/#/' /etc/apt/sources.list 2>/dev/null || true
    sudo apt-get update -qq

    curl -fsSL https://get.docker.com | sh
    systemctl start docker
    systemctl enable docker
    echo_info "Docker 安装完成"
else
    echo_info "Docker 已安装: $(docker --version)"
fi

# ---- 2. 检查 Docker Compose ----
echo_info "检查 Docker Compose..."
if docker compose version &> /dev/null; then
    echo_info "Docker Compose 已就绪"
else
    echo_error "Docker Compose 不可用，请检查 Docker 版本 (需要 20.10+)"
    exit 1
fi

# ---- 3. 进入项目目录 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
echo_info "工作目录: $SCRIPT_DIR"

# ---- 4. 检查 .env ----
if [ ! -f "backend/.env" ]; then
    echo_warn "backend/.env 不存在，从模板创建..."
    cp .env.example backend/.env
    echo_error "请先编辑 backend/.env 填入 API Key，然后重新运行此脚本"
    echo_warn "命令: nano backend/.env"
    exit 1
fi

# 检查 API Key 是否还是占位符
if grep -q "sk-your-qwen-api-key" backend/.env; then
    echo_error "请先在 backend/.env 中填入你的 Qwen API Key"
    echo_warn "命令: nano backend/.env"
    exit 1
fi

echo_info ".env 配置检查通过"

# ---- 5. 构建并启动 ----
echo_info "开始构建镜像（首次约 3-5 分钟）..."
docker compose build

echo_info "启动服务..."
docker compose up -d

# ---- 6. 等待健康检查 ----
echo_info "等待服务启动..."
sleep 10

for i in $(seq 1 12); do
    if curl -s http://localhost:8000/health | grep -q "ok"; then
        echo_info "后端服务已就绪!"
        break
    fi
    echo_info "等待中... ($i/12)"
    sleep 5
done

# ---- 7. 最终检查 ----
echo ""
echo "=========================================="
echo -e "${GREEN}  部署完成!${NC}"
echo "=========================================="
echo ""

docker compose ps

# 获取公网 IP
PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ipinfo.io/ip 2>/dev/null || echo "YOUR_SERVER_IP")

echo ""
echo "访问地址:"
echo "  前端界面:  http://$PUBLIC_IP"
echo "  API 文档:  http://$PUBLIC_IP:8000/docs"
echo "  健康检查:  http://$PUBLIC_IP:8000/health"
echo ""
echo "常用命令:"
echo "  查看日志:  docker compose logs -f"
echo "  重启服务:  docker compose restart"
echo "  停止服务:  docker compose down"
echo "  更新代码:  docker compose build && docker compose up -d"
echo ""
echo_warn "记得在云服务器安全组开放端口: 80, 8000"
echo ""
