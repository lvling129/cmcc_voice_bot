#!/bin/bash
# =============================================================================
# 精简启动脚本：仅启动 robot_avvtn + doubao_realtime_dialog
# 用法: ./launch.sh
# 停止: ./stop_all.sh 或手动 kill
# =============================================================================

set -euo pipefail

PROJECT_DIR="/home/jetson/cmcc_voice_bot"
PID_DIR="/tmp/cmcc_voice_bot_pids"
mkdir -p "${PID_DIR}"

# ---- 加载 ROS2 环境 ----
set +u
source /opt/ros/humble/setup.bash
set -u
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# ---- 设置库路径 ----
ARCH=$(uname -m)
if [[ "$ARCH" == "x86_64" ]]; then
    export LD_LIBRARY_PATH="${PROJECT_DIR}/lib/x86:${LD_LIBRARY_PATH:-}"
elif [[ "$ARCH" == "aarch64" ]]; then
    export LD_LIBRARY_PATH="${PROJECT_DIR}/lib/arm:${LD_LIBRARY_PATH:-}"
fi

# ---- 日志目录（放在项目下，避免 /var/log 权限问题） ----
LOG_DIR="${PROJECT_DIR}/log"
mkdir -p "${LOG_DIR}"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC}   $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; }

# ---- 1. 停止已有实例 ----
bash "${PROJECT_DIR}/bin/stop.sh" 2>/dev/null || true
pid_file="${PID_DIR}/doubao_dialog.pid"
if [ -f "${pid_file}" ]; then
    kill "$(cat "${pid_file}")" 2>/dev/null || true
    rm -f "${pid_file}"
fi
sleep 1

# ---- 2. 启动 robot_avvtn ----
echo ""
echo ">>> 启动 robot_avvtn ..."
bash "${PROJECT_DIR}/bin/start.sh"
sleep 2

# 检查 robot_avvtn 是否运行
if pgrep -x "robot_avvtn" > /dev/null 2>&1; then
    ok "robot_avvtn 已启动 (PID: $(pgrep -x robot_avvtn | head -1))"
    AVVTTN_OK=true
else
    fail "robot_avvtn 启动失败"
    AVVTTN_OK=false
fi

# ---- 3. 启动 doubao_realtime_dialog ----
echo ""
echo ">>> 启动 doubao_realtime_dialog ..."
cd "${PROJECT_DIR}/doubao_realtime_dialog"
/usr/bin/python3.10 main.py --mic-source=ros2 \
    >> "${LOG_DIR}/doubao_dialog.log" 2>&1 &
DOUBAO_PID=$!
echo "${DOUBAO_PID}" > "${PID_DIR}/doubao_dialog.pid"
sleep 2

# 检查 doubao 是否运行
if kill -0 "${DOUBAO_PID}" 2>/dev/null; then
    ok "doubao_realtime_dialog 已启动 (PID: ${DOUBAO_PID})"
    DOUBAO_OK=true
else
    fail "doubao_realtime_dialog 启动失败，查看日志: ${LOG_DIR}/doubao_dialog.log"
    DOUBAO_OK=false
fi

# ---- 4. 汇总结果 ----
echo ""
echo "========================================="
if [[ "${AVVTTN_OK}" == true && "${DOUBAO_OK}" == true ]]; then
    echo -e "  ${GREEN}所有服务启动成功！${NC}"
else
    echo -e "  ${RED}部分服务启动失败，请检查上方日志${NC}"
fi
echo "  日志目录: ${LOG_DIR}/"
echo "  停止服务: ./stop_all.sh"
echo "========================================="
