#!/bin/bash
# =============================================================================
# 一键启动所有服务
# 用法: ./launch_all.sh
# 停止: ./stop_all.sh
# =============================================================================

set -euo pipefail

PROJECT_DIR="/home/jetson/cmcc_voice_bot"
PID_DIR="/tmp/cmcc_voice_bot_pids"
mkdir -p "${PID_DIR}"

# 加载 ROS2 环境（所有子进程共享）
set +u
source /opt/ros/humble/setup.bash
set -u
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# 设置库路径
ARCH=$(uname -m)
if [[ "$ARCH" == "x86_64" ]]; then
    export LD_LIBRARY_PATH="${PROJECT_DIR}/lib/x86:${LD_LIBRARY_PATH:-}"
elif [[ "$ARCH" == "aarch64" ]]; then
    export LD_LIBRARY_PATH="${PROJECT_DIR}/lib/arm:${LD_LIBRARY_PATH:-}"
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[launch_all]${NC} $1"; }
warn() { echo -e "${YELLOW}[launch_all]${NC} $1"; }

# ---------- 1. 先停止已有实例（幂等） ----------
warn "停止已有实例..."
bash "${PROJECT_DIR}/bin/stop.sh" 2>/dev/null || true
# 停止之前启动的 Python 服务
for name in business_flow doubao_dialog; do
    pid_file="${PID_DIR}/${name}.pid"
    if [ -f "${pid_file}" ]; then
        pid=$(cat "${pid_file}")
        kill "${pid}" 2>/dev/null || true
        rm -f "${pid_file}"
    fi
done
sleep 1

# ---------- 2. 启动 C++ AVVTN ----------
log "启动 robot_avvtn..."
bash "${PROJECT_DIR}/bin/start.sh"
sleep 2
log "robot_avvtn 已启动"

# ---------- 3. 启动业务流程节点 ----------
log "启动 business_flow_node..."
/usr/bin/python3.10 "${PROJECT_DIR}/control/business_flow_node.py" \
    >> ${PROJECT_DIR}/log/business_flow.log 2>&1 &
echo $! > "${PID_DIR}/business_flow.pid"
log "business_flow_node 已启动 (PID: $!)"

# ---------- 4. 启动豆包实时对话 ----------
log "启动 doubao_realtime_dialog..."
cd "${PROJECT_DIR}/doubao_realtime_dialog"
/usr/bin/python3.10 main.py --mic-source=ros2 \
    >> ${PROJECT_DIR}/log/doubao_dialog.log 2>&1 &
echo $! > "${PID_DIR}/doubao_dialog.pid"
log "doubao_realtime_dialog 已启动 (PID: $!)"

# ---------- 完成 ----------
echo ""
log "========================================="
log "  所有服务已启动！"
log "  AVVTN:          运行中 (见 bin/stop.sh)"
log "  business_flow:  PID $(cat ${PID_DIR}/business_flow.pid)"
log "  doubao_dialog:  PID $(cat ${PID_DIR}/doubao_dialog.pid)"
log "  日志目录:       ${PROJECT_DIR}/log/"
log "  停止所有服务:   ./stop_all.sh"
log "========================================="
