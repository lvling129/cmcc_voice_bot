# robot_avvtn

机器人多模态采集与语音交互节点：集成 **AVVTN 多模态降噪/唤醒引擎** 与 **讯飞 AIUI**，通过 ROS2 与系统其他模块通信。

## 功能概述

- **多模态采集**：视频（摄像头）（暂未实现）、音频（麦克风）采集，并送入 AVVTN 引擎进行降噪与处理
- **语音唤醒**：支持 IVW 语音唤醒，可输出带角度的唤醒详情供转向等动作使用
- **语音识别与合成**：通过 AIUI 进行 ASR、TTS、流式 NLP 及技能/知识库语义处理
- **技能控制** old：解析语义后通过 HTTP 向 webrtc 服务发送移动/转向/动作/停止等控制请求（libcurl）
- **技能控制**：
- **ROS2 集成**：以单例 `ROSManager` 发布日志、聊天记录、状态、唤醒详情，并订阅如 `wake_up_turn_result` 等话题

## 依赖

- **CMake** 3.10–3.20，**C++17**
- **ROS2**（ament_cmake, rclcpp, std_msgs）
- **OpenCV**
- **libcurl**
- **PortAudio**、**udev**
- **AVVTN 引擎**：`lib/arm` 下 `avvtn_mic${MIC_NUM}`（如 `avvtn_mic6`）
- **讯飞 AIUI SDK**：`aiui`
- 配置文件与资源：`avvtn.cfg`、`resource/`

## 目录结构（简要）

```
robot_avvtn/
├── CMakeLists.txt          # 顶层 CMake，ROS2/curl 依赖
├── build.sh                # 编译脚本（build 目录 + 按架构设置 LD_LIBRARY_PATH）
├── avvtn.cfg               # AVVTN/登录/MMSP/VAD/录屏/日志等配置
├── bin/
│   ├── start.sh            # 启动程序（先停旧进程，再后台运行，写 program.log）
│   ├── stop.sh             # 停止程序
│   └── robot_avvtn         # 编译生成的可执行文件
├── src/
│   ├── main.cpp            # 入口：日志、ROS、AvvtnCapture 初始化与信号等待
│   ├── avvtn_capture/      # 多模态采集与 AVVTN 回调（视频/音频/唤醒/CAE/录音等）
│   │   ├── avvtn_capture.h/cpp
│   │   ├── avvtn_handle.cpp # 人脸、CAE、录音、唤醒等 handle
│   │   └── skill_handle.cpp # 技能解析与 HTTP 请求（postRequest、send*Request）
│   ├── aiui_capture/       # AIUI 封装（识别、合成、流式 NLP 等）
│   ├── audio_capture/      # 音频采集
│   ├── video_capture/      # 视频采集
│   ├── ros2/               # ROS2 单例（发布/订阅）
│   └── utils/              # 日志、JSON 等
├── include/                # 头文件（如 avvtn_api）
├── resource/               # 引擎与 AIUI 资源
├── license/                # AVVTN 许可证
├── log/                    # 引擎等日志输出目录（由 avvtn.cfg 等配置）
└── doc/                    # 版本与接口说明（如唤醒字段、参数变更）
```

## 注意（重要）
- 配置文件与资源：`avvtn.cfg`、`resource/`
里面的路径需要修改为当前项目的绝对路径，否则程序启动失败。
同时main函数中的avvtn.cfg和aiui.cfg也需使用绝对路径。

## 编译

```bash
# 在项目根目录执行
./build.sh
```

- 会清空 `build/` 后以 `Release` 配置执行 `cmake` 和 `make -j8`
- 根据架构设置 `LD_LIBRARY_PATH`：`lib/arm`（aarch64）或 `lib/x86`（x86_64）
- 可执行文件会复制到 `bin/robot_avvtn`

## 运行

**启动（建议在 `bin/` 下执行，以便使用脚本内日志路径）：**

```bash
cd bin
./start.sh
```

- 会先尝试停止已有进程，再后台启动 `./robot_avvtn`，日志写入 `bin/program.log`
- 程序内部 Logger 还会写 `app.log`（相对当前工作目录，若在 `bin/` 启动则为 `bin/app.log`）

**停止：**

```bash
cd bin
./stop.sh
```

**直接运行可执行文件（需自行设置库路径）：**

```bash
export LD_LIBRARY_PATH=$(pwd)/lib/arm:$LD_LIBRARY_PATH   # aarch64
# 或
export LD_LIBRARY_PATH=$(pwd)/lib/x86:$LD_LIBRARY_PATH   # x86_64
./bin/robot_avvtn
```

## 程序运行日志

- 脚本输出日志：`bin/program.log`
- 应用内部日志：`bin/app.log`（若从 `bin/` 启动）
- 其他引擎/组件日志可能输出到 `log/`（见 `avvtn.cfg` 等配置）

## ROS2 话题

| 类型     | 话题名称                       | 说明                     |
|----------|--------------------------------|--------------------------|
| 发布     | `robot_avvtn_log`              | 程序运行日志             |
| 发布     | `robot_avvtn_chat_history`    | 聊天记录（含流式等）     |
| 发布     | `robot_avvtn_chat_history_nostream` | 非流式聊天文本     |
| 发布     | `robot_avvtn_status`          | AIUI/状态切换（如等待连接、等待唤醒、对话中） |
| 发布     | `avvtn_wake`                  | 带角度的唤醒详情（供转向等使用） |
| 订阅     | `wake_up_turn_result`         | 唤醒转向结果回调         |

状态取值包括：`STATUS_WAITING_CONNECTION`、`STATUS_WAITING_WAKEUP`、`STATUS_IN_CONVERSATION`、`STATUS_WAITING_CONVERSATION`。

## 配置说明

- **avvtn.cfg**：登录信息（appid、sn、work_dir、license_path）、MMSP（视频延迟、人脸参数、CAE 模式等）、VAD、录屏、日志路径等。
- **resource/**：AVVTN、AIUI 等资源与配置文件（如 `resource/aiui/aiui.cfg`）。
- 唤醒词等：参见 `doc/README.md`（如 `resource/vtn/res/vtn/vtn.ini` 中 `res_identifier`、`wakeup` / `wakeup_detail` 字段说明）。

## 更多文档

- 唤醒词与唤醒字段、摄像头剪裁、自动降级等参数变更说明见 **doc/README.md**。
