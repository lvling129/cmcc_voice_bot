#!/bin/bash
#
# 启动营业厅业务流程节点
# 用法: ./run_business.sh
#

set -e

# 脚本所在目录（支持从任意路径调用）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 加载 ROS2 环境
source /opt/ros/humble/setup.bash || {
    echo "错误: 未找到 ROS2 Humble，请先安装"
    exit 1
}

# Python 解释器（使用系统 Python 3.10 以兼容 rclpy）
PYTHON="${PYTHON:-/usr/bin/python3.10}"

# 检查 Python 是否存在
if ! command -v ${PYTHON} &> /dev/null; then
    echo "错误: 未找到 Python 解释器: ${PYTHON}"
    exit 1
fi

echo "========================================="
echo "  启动营业厅业务流程节点"
echo "  Python: ${PYTHON}"
echo "  节点: ${SCRIPT_DIR}/business_flow_node.py"
echo "========================================="

# 启动节点
exec ${PYTHON} "${SCRIPT_DIR}/business_flow_node.py" "$@"
