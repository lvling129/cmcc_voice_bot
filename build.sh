#!/bin/bash

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. 创建并进入 build 目录
if [ ! -d "build" ]; then
    mkdir build
fi
cd build

# 2. 清理
# 完全重新编译
rm -rf *

# 3. CMake 配置
cmake .. -DCMAKE_BUILD_TYPE=Release

# 4. 编译
make -j4

# 5. 返回项目根目录
cd "$SCRIPT_DIR"

# 6. 设置库路径
ARCH=$(uname -m)
if [[ "$ARCH" == "x86_64" ]]; then
    export LD_LIBRARY_PATH=$(pwd)/lib/x86:$LD_LIBRARY_PATH
    echo "Set LD_LIBRARY_PATH for x86_64"
elif [[ "$ARCH" == "aarch64"* ]]; then
    export LD_LIBRARY_PATH=$(pwd)/lib/arm:$LD_LIBRARY_PATH
    echo "Set LD_LIBRARY_PATH for ARM64"
else
    echo "Unsupported architecture: $ARCH"
    exit 1
fi
