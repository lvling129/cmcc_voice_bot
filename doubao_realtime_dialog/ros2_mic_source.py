"""ROS2 麦克风输入源

订阅 C++ AVVTN 主程序通过 /avvtn/mic_pcm 发布的 AEC 后 PCM（16k mono S16LE），
作为豆包对话的麦克风输入源，**绕开本地 pyaudio 直采**，从而：
1. 让豆包听到的是 AVVTN 已经回声消除/波束成形/降噪后的干净人声
2. 避免双程序竞争麦克风设备导致 device busy

使用方式：
    main.py --mic-source=ros2

设计要点：
- 节点 spin 跑在独立守护线程，不阻塞 asyncio 事件循环
- ROS2 回调把 PCM 字节追加到 bytearray 缓冲；async read(chunk_size) 端做切片
- 缓冲使用 threading.Lock 保护，跨线程安全
- 缓冲超过 max_buffer_bytes（默认 5 秒）会丢弃最旧数据，避免内存膨胀
- QoS: BEST_EFFORT + KeepLast(20)，与 C++ publisher 对齐
"""

import asyncio
import threading
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from std_msgs.msg import UInt8MultiArray


class Ros2MicSource:
    """ROS2 PCM 订阅器，提供与 pyaudio Stream 类似的 read 接口"""

    DEFAULT_TOPIC = "/avvtn/mic_pcm"
    # 5 秒 16k S16LE 缓冲上限：16000 * 2 * 5 = 160000B
    DEFAULT_MAX_BUFFER_BYTES = 16000 * 2 * 5

    def __init__(self, topic: str = DEFAULT_TOPIC,
                 node_name: str = "doubao_mic_source",
                 max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES) -> None:
        self.topic = topic
        self.node_name = node_name
        self.max_buffer_bytes = max_buffer_bytes

        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._first_packet_seen = False

        self._node: Optional[Node] = None
        self._executor = None
        self._spin_thread: Optional[threading.Thread] = None
        self._running = False

    # -- 启动 / 停止 ---------------------------------------------------------

    def start(self) -> None:
        """初始化 rclpy（若尚未初始化）+ 创建 Node + 后台线程 spin"""
        if not rclpy.ok():
            rclpy.init()

        self._node = rclpy.create_node(self.node_name)

        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=20,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._node.create_subscription(
            UInt8MultiArray, self.topic, self._on_pcm, qos)

        self._running = True
        self._spin_thread = threading.Thread(
            target=self._spin_loop, name="ros2_mic_spin", daemon=True)
        self._spin_thread.start()

        self._node.get_logger().info(
            f"ROS2 mic source 已启动，订阅 topic={self.topic}")

    def stop(self) -> None:
        """停止节点和 spin 线程，唤醒任何阻塞的 read"""
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._node is not None:
            try:
                self._node.destroy_node()
            except Exception:
                pass
            self._node = None
        # 不在这里 rclpy.shutdown()——让进程级负责，避免重复 shutdown

    def _spin_loop(self) -> None:
        try:
            while self._running and rclpy.ok() and self._node is not None:
                rclpy.spin_once(self._node, timeout_sec=0.1)
        except Exception as e:
            print(f"[ros2_mic_source] spin 线程异常: {e}")

    # -- 数据回调 ------------------------------------------------------------

    def _on_pcm(self, msg: UInt8MultiArray) -> None:
        # msg.data 在 rclpy 里通常是 array.array('B', ...)
        # 转 bytes 一次 copy；对 100ms 3200B 来说成本可忽。
        chunk = bytes(msg.data)
        if not chunk:
            return
        with self._cond:
            self._buffer.extend(chunk)
            # 超出上限时丢弃最旧数据，避免长时间无人消费导致内存爆涨
            if len(self._buffer) > self.max_buffer_bytes:
                drop = len(self._buffer) - self.max_buffer_bytes
                del self._buffer[:drop]
            if not self._first_packet_seen:
                self._first_packet_seen = True
                print(f"[ros2_mic_source] 首包到达: {len(chunk)}B，缓冲区累计 {len(self._buffer)}B")
            self._cond.notify_all()

    # -- 同步阻塞读（提供给非 asyncio 调用者） -----------------------------

    def read_blocking(self, chunk_size: int, timeout: Optional[float] = None) -> bytes:
        """阻塞读取 chunk_size 字节；timeout 为 None 时永久等待。
        若停止/超时仍不足，会返回当前累积（可能为空）。"""
        deadline = None if timeout is None else (time.monotonic() + timeout)
        with self._cond:
            while self._running and len(self._buffer) < chunk_size:
                remain = None
                if deadline is not None:
                    remain = deadline - time.monotonic()
                    if remain <= 0:
                        break
                self._cond.wait(timeout=remain)
            n = min(chunk_size, len(self._buffer))
            data = bytes(self._buffer[:n])
            del self._buffer[:n]
            return data

    # -- 异步读（asyncio 友好） ---------------------------------------------

    async def read(self, chunk_size: int, poll_interval: float = 0.01) -> bytes:
        """异步等待 chunk_size 字节就绪；若一帧时长内仍不足，用静音填充返回。

        豆包云端 ASR 有 AudioASRIdleTimeoutError(52000009)：客户端长时间不送
        任何字节就会主动断开。pyaudio 直采本来就持续给云端送麦克风采样
        （静音段也是有效字节），但 ROS2 模式下 AVVTN VAD 过滤了静音，
        间隙完全断流会触发云端 idle 超时。

        这里的策略：每帧最多等 chunk_duration（chunk_size 对应的真实时长），
        超时就立即返回 chunk_size 字节的静音；有真实数据时优先返回真实数据。
        既保证云端持续有数据消费，又不污染语音段。
        """
        # 16k mono S16LE：每字节 1/(16000*2) 秒
        chunk_duration = chunk_size / (16000 * 2)
        deadline = time.monotonic() + chunk_duration

        while self._running:
            with self._lock:
                if len(self._buffer) >= chunk_size:
                    data = bytes(self._buffer[:chunk_size])
                    del self._buffer[:chunk_size]
                    return data

            # 超过一帧时长仍不足 → 用静音填充返回，避免云端 idle 超时
            if time.monotonic() >= deadline:
                return b"\x00" * chunk_size

            await asyncio.sleep(poll_interval)

        # 已停止：返回一帧静音，让上层循环自然退出
        return b"\x00" * chunk_size

    # -- 上下文管理 ---------------------------------------------------------

    def __enter__(self) -> "Ros2MicSource":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
