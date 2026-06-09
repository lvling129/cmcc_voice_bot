#!/bin/bash
# =============================================================================
# 一键停止所有服务（launch_all.sh 启动的）
# 用法: ./stop_all.sh
# =============================================================================

set -u

PROJECT_DIR="/home/nvidia/cmcc_voice_bot"
PID_DIR="/tmp/cmcc_voice_bot_pids"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[stop_all]${NC} $1"; }
warn() { echo -e "${YELLOW}[stop_all]${NC} $1"; }

# ---------- 1. 停止豆包对话 ----------
pid_file="${PID_DIR}/doubao_dialog.pid"
if [ -f "${pid_file}" ]; then
    pid=$(cat "${pid_file}")
    if kill -0 "${pid}" 2>/dev/null; then
        log "停止 doubao_dialog (PID: ${pid})..."
        kill "${pid}" 2>/dev/null || true
        sleep 1
        kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
else
    warn "doubao_dialog 未运行"
fi

# ---------- 2. 停止业务流程节点 ----------
pid_file="${PID_DIR}/business_flow.pid"
if [ -f "${pid_file}" ]; then
    pid=$(cat "${pid_file}")
    if kill -0 "${pid}" 2>/dev/null; then
        log "停止 business_flow (PID: ${pid})..."
        kill "${pid}" 2>/dev/null || true
        sleep 1
        kill -9 "${pid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
else
    warn "business_flow 未运行"
fi

# ---------- 3. 停止 C++ AVVTN ----------
log "停止 robot_avvtn..."
bash "${PROJECT_DIR}/bin/stop.sh" 2>/dev/null || true

# ---------- 完成 ----------
log "========================================="
log "  所有服务已停止"
log "========================================="
