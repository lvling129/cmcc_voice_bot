# Doubao RealtimeDialog

豆包端到端实时语音对话客户端，支持麦克风输入、录音文件输入和文本输入三种模式。

## 环境要求

- 系统 Python 3.10（ROS2 Humble 的 rclpy 绑定系统 Python ABI）
- ROS2 Humble 运行时环境

## 安装依赖

```bash
# 安装系统依赖（一次性）
sudo apt install -y python3.10-dev portaudio19-dev libssl-dev

# 安装 Python 依赖（使用系统 Python 3.10）
/usr/bin/python3.10 -m pip install pyaudio 'websockets>=12.0,<13.0'
```

## 配置

### API 密钥

打开 `config.py` 文件，修改以下字段：
```python
"X-Api-App-ID": "火山控制台上端到端大模型对应的App ID",
"X-Api-Access-Key": "火山控制台上端到端大模型对应的Access Key",
```

### 发音人

修改 `config.py` 中的 `speaker` 字段，支持以下发音人：
- `zh_female_vv_jupiter_bigtts`：中文 vv 女声（默认）
- `zh_female_xiaohe_jupiter_bigtts`：中文 xiaohe 女声
- `zh_male_yunzhou_jupiter_bigtts`：中文云洲男声
- `zh_male_xiaotian_jupiter_bigtts`：中文小天男声

## 启动方式

### 方式一：使用 run.sh（推荐）

```bash
# 默认模式：从 ROS2 订阅 AVVTN 降噪后的麦克风数据
./run.sh

# 录音文件模式
./run.sh --audio=whoareyou.wav

# 纯文本对话模式
./run.sh --mod=text --recv_timeout=120
```

### 方式二：直接运行

```bash
# 先 source ROS2 环境
source /opt/ros/humble/setup.bash

# 然后启动
/usr/bin/python3.10 main.py --mic-source=ros2
```

### 方式三：systemd 服务

可将 `run.sh` 作为 systemd `ExecStart` 直接调用。

## 环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ROS_SETUP` | `/opt/ros/humble/setup.bash` | ROS2 setup 路径 |
| `ROS_DOMAIN_ID` | `0` | ROS2 域 ID |
| `PYTHON` | `/usr/bin/python3.10` | Python 解释器路径 |
| `SYSTEM_PROMPT_FILE` | `prompts/cmcc_lingxi.md` | 自定义 system prompt 文件 |

示例：
```bash
SYSTEM_PROMPT_FILE=/path/to/custom.md ./run.sh --mic-source=ros2
```

## 目录结构

```
doubao_realtime_dialog/
├── run.sh                   # 启动脚本
├── main.py                  # 入口文件
├── config.py                # 配置文件
├── audio_manager.py         # 音频管理（输入/输出/播放）
├── ros2_mic_source.py       # ROS2 麦克风数据订阅
├── realtime_dialog_client.py # WebSocket 对话客户端
├── protocol.py              # 协议定义
├── prompts/                 # system prompt 文件
│   └── cmcc_lingxi.md
└── requirements.txt         # Python 依赖
```