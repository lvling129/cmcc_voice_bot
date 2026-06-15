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
import json
import threading
import time
from typing import Optional
from queue import Queue, Empty

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from std_msgs.msg import UInt8MultiArray, String


class Ros2MicSource:
    """ROS2 PCM 订阅器，提供与 pyaudio Stream 类似的 read 接口"""

    DEFAULT_TOPIC = "/avvtn/mic_pcm"
    DEFAULT_TTS_TOPIC = "/doubao_tts"
    DEFAULT_CHAT_HISTORY_TOPIC = "/chat_history"
    DEFAULT_VOICE_TOPIC = "/voice_topic"
    DEFAULT_SUBTITLE_TOPIC = "/voiceprint/subtitle"
    # 5 秒 16k S16LE 缓冲上限：16000 * 2 * 5 = 160000B
    DEFAULT_MAX_BUFFER_BYTES = 16000 * 2 * 5

    def __init__(self, topic: str = DEFAULT_TOPIC,
                 tts_topic: str = DEFAULT_TTS_TOPIC,
                 chat_history_topic: str = DEFAULT_CHAT_HISTORY_TOPIC,
                 node_name: str = "doubao_mic_source",
                 max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES) -> None:
        self.topic = topic
        self.tts_topic = tts_topic
        self.chat_history_topic = chat_history_topic
        self.node_name = node_name
        self.max_buffer_bytes = max_buffer_bytes

        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._first_packet_seen = False

        # TTS 文本队列（线程安全）
        self._tts_queue: Queue = Queue()

        # 字幕文本队列（VAD 结束后的完整句子，线程安全）
        self._subtitle_queue: Queue = Queue()

        # 对话查询队列（收到 /doubao_chat_text_query 后发给大模型）
        self._chat_query_queue: Queue = Queue()

        self._node: Optional[Node] = None
        self._executor = None
        self._spin_thread: Optional[threading.Thread] = None
        self._running = False
        
        # 聊天历史发布器
        self._pub_chat_history = None
        
        # 业务意图发布器（/voice_topic）
        self._pub_voice_topic = None

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

        # 订阅 /doubao_tts 话题（用于接收外部文本并转 TTS）
        self._node.create_subscription(
            String, self.tts_topic, self._on_tts_text, 10)

        # 订阅 /voiceprint/subtitle 话题（用于接收 VAD 字幕文本）
        self._node.create_subscription(
            String, self.DEFAULT_SUBTITLE_TOPIC, self._on_subtitle, 10)

        # 订阅 /doubao_chat_text_query 话题（收到文本后发给大模型对话）
        self._node.create_subscription(
            String, '/doubao_chat_text_query', self._on_chat_query, 10)

        # 发布 /chat_history 话题（用于发送 ASR 识别结果）
        chat_history_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._pub_chat_history = self._node.create_publisher(
            String, self.chat_history_topic, chat_history_qos)
        
        # 发布 /voice_topic 话题（用于发送业务意图）
        self._pub_voice_topic = self._node.create_publisher(
            String, "/voice_topic", 10)

        self._running = True
        self._spin_thread = threading.Thread(
            target=self._spin_loop, name="ros2_mic_spin", daemon=True)
        self._spin_thread.start()

        self._node.get_logger().info(
            f"ROS2 mic source 已启动，订阅 topic={self.topic}, tts_topic={self.tts_topic}, subtitle_topic={self.DEFAULT_SUBTITLE_TOPIC}")

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

    # -- TTS 回调 -------------------------------------------------------------

    def _on_tts_text(self, msg: String) -> None:
        """收到 /doubao_tts 话题消息，放入 TTS 队列"""
        text = msg.data.strip()
        if text:
            print(f"[ros2_mic_source] 收到 TTS 文本: {text}")
            self._tts_queue.put(text)

    def get_tts_text(self) -> Optional[str]:
        """非阻塞获取一条 TTS 文本，无数据时返回 None"""
        try:
            return self._tts_queue.get_nowait()
        except Empty:
            return None

    # -- 字幕回调 -------------------------------------------------------------

    def _on_subtitle(self, msg: String) -> None:
        print(f"[ros2_mic_source] 收到 /voiceprint/subtitle 话题消息")
        """收到 /voiceprint/subtitle 话题消息，VAD 结束时将完整句子放入队列"""
        try:
            data = json.loads(msg.data)
            text = data.get("text", "").strip()
            end = data.get("end", False)
            if end and text:
                print(f"[ros2_mic_source] 字幕 VAD 结束: {text}")
                self._subtitle_queue.put(text)
        except json.JSONDecodeError as e:
            print(f"[ros2_mic_source] 字幕 JSON 解析失败: {e}")

    def get_subtitle_text(self) -> Optional[str]:
        """非阻塞获取一条 VAD 结束的字幕文本，无数据时返回 None"""
        try:
            return self._subtitle_queue.get_nowait()
        except Empty:
            return None

    # -- 对话查询回调 ---------------------------------------------------------

    def _on_chat_query(self, msg: String) -> None:
        """收到 /doubao_chat_text_query 话题消息，将文本放入队列"""
        text = msg.data.strip()
        if text:
            print(f"[ros2_mic_source] 收到 /doubao_chat_text_query: {text}")
            self._chat_query_queue.put(text)

    def get_chat_query_text(self) -> Optional[str]:
        """非阻塞获取一条对话查询文本，无数据时返回 None"""
        try:
            return self._chat_query_queue.get_nowait()
        except Empty:
            return None
    
    def publish_chat_history(self, content: str, speaker: str) -> None:
        """发布聊天历史到 /chat_history 话题
        
        Args:
            content: 聊天内容（ASR 识别结果或 TTS 回复文本）
            speaker: 说话者，"PERSON"（用户）或 "ROBOT"（豆包）
        """
        if self._pub_chat_history is None or not self._node:
            return
        try:
            msg_data = json.dumps({
                "speaker": speaker,
                "content": content
            }, ensure_ascii=False)  # 直接输出中文，不进行 Unicode 转义
            self._pub_chat_history.publish(String(data=msg_data))
            self._node.get_logger().info(f"发布聊天历史 [{speaker}]: {content}")
        except Exception as e:
            self._node.get_logger().error(f"发布聊天历史失败: {e}")
    
    def publish_business_intent(self, intent_data: dict) -> None:
        """发布业务意图到 /voice_topic 话题
        
        Args:
            intent_data: 意图数据，例如 {"intent": "query_balance"}
        """
        if self._pub_voice_topic is None or not self._node:
            return
        try:
            # 转换为 business_flow_node 期望的格式
            intent = intent_data.get("intent", "")
            msg_data = json.dumps({
                "business_type": intent,
                "content": ""
            }, ensure_ascii=False)
            self._pub_voice_topic.publish(String(data=msg_data))
            self._node.get_logger().info(f"发布业务意图到 /voice_topic: {intent}")
        except Exception as e:
            self._node.get_logger().error(f"发布业务意图失败: {e}")

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
