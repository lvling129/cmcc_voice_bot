#!/bin/bash
# =============================================================================
# 豆包端到端实时语音对话 - 启动脚本
# 用法:
#   ./run.sh                       # 默认启动: --format=pcm 麦克风模式
#   ./run.sh --format=pcm          # 同上，显式指定
#   ./run.sh --audio=whoareyou.wav # 用录音文件做一次对话
#   ./run.sh --mod=text --recv_timeout=120  # 纯文本对话
#   ./run.sh --help                # 透传给 main.py 看其全部参数
#
# 环境变量（可覆盖默认值）:
#   ROS_SETUP        - ROS2 setup.bash 路径，默认 /opt/ros/humble/setup.bash
#   VENV_DIR         - venv 目录，默认 ../.venv310（相对脚本目录）
#   ROS_DOMAIN_ID    - ROS2 域 ID，默认 0（与 bin/start.sh 保持一致）
#   SYSTEM_PROMPT_FILE - system_role 加载路径，默认 prompts/cmcc_lingxi.md
#
# 可被 bin/start.sh 或 systemd ExecStart 直接调用
# =============================================================================

set -euo pipefail

# ---- 1. 定位脚本所在目录（不依赖调用者 cwd） -------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 2. 配置（可被环境变量覆盖） -------------------------------------------
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
VENV_DIR="${VENV_DIR:-${SCRIPT_DIR}/../.venv310}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

# ---- 3. 前置检查 ------------------------------------------------------------
if [ ! -f "${ROS_SETUP}" ]; then
    echo "[run.sh] 错误: 未找到 ROS2 setup.bash: ${ROS_SETUP}" >&2
    echo "         可通过环境变量覆盖，例如: ROS_SETUP=/opt/ros/foxy/setup.bash ./run.sh" >&2
    exit 1
fi

if [ ! -f "${VENV_DIR}/bin/activate" ]; then
    echo "[run.sh] 错误: 未找到 venv 环境: ${VENV_DIR}" >&2
    echo "         请先按下面步骤创建（一次性）:" >&2
    echo "           sudo apt install -y python3.10-venv python3.10-dev portaudio19-dev libssl-dev" >&2
    echo "           python3.10 -m venv --system-site-packages ${VENV_DIR}" >&2
    echo "           source ${VENV_DIR}/bin/activate" >&2
    echo "           pip install pyaudio 'websockets>=12.0,<13.0'" >&2
    exit 2
fi

# ---- 4. 激活环境（顺序: 先 ROS, 再 venv） ----------------------------------
# ROS2 setup.bash 带未定义变量访问，与 set -u 不兼容，需临时关闭
set +u
# shellcheck disable=SC1090
source "${ROS_SETUP}"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
set -u

# ---- 5. 默认参数处理 --------------------------------------------------------
# 若调用方未传任何参数，使用麦克风 PCM 模式
if [ "$#" -eq 0 ]; then
    set -- --format=pcm
fi

# ---- 6. 启动信息（systemd journal 也能看到） -------------------------------
echo "[run.sh] python:        $(python --version 2>&1)"
echo "[run.sh] venv:          ${VIRTUAL_ENV:-N/A}"
echo "[run.sh] ROS_DISTRO:    ${ROS_DISTRO:-N/A}"
echo "[run.sh] ROS_DOMAIN_ID: ${ROS_DOMAIN_ID}"
echo "[run.sh] cwd:           ${SCRIPT_DIR}"
echo "[run.sh] prompt:        ${SYSTEM_PROMPT_FILE:-prompts/cmcc_lingxi.md}"
echo "[run.sh] launch:        python main.py $*"
echo "----------------------------------------------------------------------"

# ---- 7. 用 exec 启动，让信号(SIGTERM/SIGINT)能直接传给 python --------------
exec python main.py "$@"
