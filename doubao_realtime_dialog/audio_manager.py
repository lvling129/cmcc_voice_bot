import asyncio
import queue
import signal
import sys
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from typing import Optional, Dict, Any

import pyaudio

import config
from realtime_dialog_client import RealtimeDialogClient


@dataclass
class AudioConfig:
    """音频配置数据类"""
    format: str
    bit_size: int
    channels: int
    sample_rate: int
    chunk: int


class AudioDeviceManager:
    """音频设备管理类，处理音频输入输出"""

    def __init__(self, input_config: AudioConfig, output_config: AudioConfig):
        self.input_config = input_config
        self.output_config = output_config
        self.pyaudio = pyaudio.PyAudio()
        self.input_stream: Optional[pyaudio.Stream] = None
        self.output_stream: Optional[pyaudio.Stream] = None

    def open_input_stream(self) -> pyaudio.Stream:
        """打开音频输入流"""
        # p = pyaudio.PyAudio()
        self.input_stream = self.pyaudio.open(
            format=self.input_config.bit_size,
            channels=self.input_config.channels,
            rate=self.input_config.sample_rate,
            input=True,
            frames_per_buffer=self.input_config.chunk
        )
        return self.input_stream

    def open_output_stream(self) -> pyaudio.Stream:
        """打开音频输出流"""
        self.output_stream = self.pyaudio.open(
            format=self.output_config.bit_size,
            channels=self.output_config.channels,
            rate=self.output_config.sample_rate,
            output=True,
            frames_per_buffer=self.output_config.chunk
        )
        return self.output_stream

    def cleanup(self) -> None:
        """清理音频设备资源"""
        for stream in [self.input_stream, self.output_stream]:
            if stream:
                stream.stop_stream()
                stream.close()
        self.pyaudio.terminate()


class DialogSession:
    """对话会话管理类"""
    is_audio_file_input: bool
    mod: str

    def __init__(self, ws_config: Dict[str, Any], output_audio_format: str = "pcm", audio_file_path: str = "",
                 mod: str = "audio", recv_timeout: int = 10, mic_source: str = "pyaudio"):
        self.audio_file_path = audio_file_path
        self.recv_timeout = recv_timeout
        self.is_audio_file_input = self.audio_file_path != ""
        self.mic_source = mic_source  # "pyaudio" 或 "ros2"
        self._ros2_mic = None  # 延迟创建，避免未使用 ros2 时 import 失败
        if self.is_audio_file_input:
            mod = 'audio_file'
        else:
            self.say_hello_over_event = asyncio.Event()
        self.mod = mod

        self.session_id = str(uuid.uuid4())
        self.client = RealtimeDialogClient(config=ws_config, session_id=self.session_id,
                                           output_audio_format=output_audio_format, mod=mod, recv_timeout=recv_timeout)
        if output_audio_format == "pcm_s16le":
            config.output_audio_config["format"] = "pcm_s16le"
            config.output_audio_config["bit_size"] = pyaudio.paInt16

        self.is_running = True
        self.is_session_finished = False
        self.is_user_querying = False
        self.is_sending_chat_tts_text = False
        self.is_muting_tts = False  # TTS 静音标志位（JSON 意图周期内禁止播放）
        self.audio_buffer = b''
        self.tts_text_buffer = ""  # 累积 TTS 文本

        self.audio_queue = queue.Queue()
        if not self.is_audio_file_input:
            self.audio_device = AudioDeviceManager(
                AudioConfig(**config.input_audio_config),
                AudioConfig(**config.output_audio_config)
            )
            # 初始化音频队列和输出流
            self.output_stream = self.audio_device.open_output_stream()
            # 启动播放线程
            self.is_recording = True
            self.is_playing = True
            self.player_thread = threading.Thread(target=self._audio_player_thread)
            self.player_thread.daemon = True
            self.player_thread.start()

    def _audio_player_thread(self):
        """音频播放线程"""
        while self.is_playing:
            try:
                # 从队列获取音频数据
                audio_data = self.audio_queue.get(timeout=1.0)
                if audio_data is not None:
                    self.output_stream.write(audio_data)
            except queue.Empty:
                # 队列为空时等待一小段时间
                time.sleep(0.1)
            except Exception as e:
                print(f"音频播放错误: {e}")
                time.sleep(0.1)

    def handle_server_response(self, response: Dict[str, Any]) -> None:
        if response == {}:
            return
        # 健壮性：偶发 server 会下发不带 message_type 的 dict（比如某些心跳/控制帧），
        # 之前会拋 KeyError 并在上层被捕获后关闭 WebSocket，导致一轮对话之后连接被断。
        # 这里跳过未知帧，避免引起全局中断。
        if 'message_type' not in response:
            return
        """处理服务器响应"""
        if response['message_type'] == 'SERVER_ACK' and isinstance(response.get('payload_msg'), bytes):
            # print(f"[audio] SERVER_ACK 音频帧: {len(response['payload_msg'])}B")
            if self.is_sending_chat_tts_text:
                return
            # 如果处于 TTS 静音期（JSON 意图），不将音频放入队列
            if self.is_muting_tts:
                return
            audio_data = response['payload_msg']
            if not self.is_audio_file_input:
                self.audio_queue.put(audio_data)
            self.audio_buffer += audio_data
        elif response['message_type'] == 'SERVER_FULL_RESPONSE':
            print(f"服务器响应: {response}")
            event = response.get('event')
            payload_msg = response.get('payload_msg', {})

            if event == 450:
                print(f"清空缓存音频: {response['session_id']}")
                while not self.audio_queue.empty():
                    try:
                        self.audio_queue.get_nowait()
                    except queue.Empty:
                        continue
                self.is_user_querying = True
                self.tts_text_buffer = ""  # 清空 TTS 文本缓存
                self.is_muting_tts = False  # 重置 TTS 静音标志位

            # ASR 识别结果（流式，event 451）
            if event == 451:
                payload_msg_data = payload_msg.get("results", [])
                if payload_msg_data:
                    # 获取最后一个结果
                    last_result = payload_msg_data[-1]
                    asr_text = last_result.get("text", "")
                    is_interim = last_result.get("is_interim", True)
                    # 只在最终结果时输出并发布到话题
                    if not is_interim and asr_text:
                        print(f"[ASR 完整识别结果]: {asr_text}")
                        # 发布到 /chat_history 话题
                        if self._ros2_mic:
                            self._ros2_mic.publish_chat_history(asr_text, speaker="PERSON")

            if event == 350 and self.is_sending_chat_tts_text and payload_msg.get("tts_type") in ["chat_tts_text", "external_rag"]:
                while not self.audio_queue.empty():
                    try:
                        self.audio_queue.get_nowait()
                    except queue.Empty:
                        continue
                self.is_sending_chat_tts_text = False

            if event == 459:
                self.is_user_querying = False
                # 安抚话术：仅在 config.enable_filler_speech 开启时下发
                # 原代码 random.randint(...) % 1 == 0 是永真 demo，会在每次一句话结束后
                # 都插入一句“请稍等，正在为您查询。”，短问答也被打断。
                if getattr(config, "enable_filler_speech", False):
                    self.is_sending_chat_tts_text = True
                    asyncio.create_task(self.trigger_chat_tts_text("请稍等，正在为您查询。"))
                    asyncio.create_task(self.trigger_chat_rag_text())
            
            # TTS 文本流式返回（event 550）
            if event == 550:
                content = payload_msg.get("content", "")
                if content:
                    # 检测是否以 "{" 开头（可能是 JSON 意图格式），立即停止 TTS
                    if content.startswith("{"):
                        # 设置 TTS 静音标志位，整个周期内禁止音频入队
                        self.is_muting_tts = True
                        # 清空音频队列，停止当前 TTS 播报
                        while not self.audio_queue.empty():
                            try:
                                self.audio_queue.get_nowait()
                            except queue.Empty:
                                continue
                        print(f"[TTS 意图检测]: 检测到 JSON 开头，已停止当前 TTS 播报，静音整个周期")
                    
                    self.tts_text_buffer += content

            # TTS 结束（event 359），打印完整文本并发布到话题
            if event == 359:
                if self.tts_text_buffer:
                    print(f"[TTS 完整回复]: {self.tts_text_buffer}")
                    # 检测是否为 JSON 意图格式，如果是则不发布到 /chat_history
                    stripped = self.tts_text_buffer.strip()
                    is_json_intent = False
                    if stripped.startswith("{") and "intent" in stripped:
                        try:
                            import json
                            json.loads(stripped)
                            is_json_intent = True
                            print(f"[TTS 跳过]: 检测到 JSON 意图格式，不发布到 /chat_history")
                        except json.JSONDecodeError:
                            pass
                    
                    # 只有非 JSON 格式的自然语言才发布到话题
                    if not is_json_intent and self._ros2_mic:
                        self._ros2_mic.publish_chat_history(self.tts_text_buffer, speaker="ROBOT")
                    self.tts_text_buffer = ""
        elif response['message_type'] == 'SERVER_ERROR':
            print(f"服务器错误: {response['payload_msg']}")
            raise Exception("服务器错误")

    async def trigger_chat_tts_text(self, text: str):
        """发送ChatTTSText请求"""
        print(f"hit ChatTTSText event, start sending: {text}")
        await self.client.chat_tts_text(
            is_user_querying=self.is_user_querying,
            start=True,
            end=False,
            content=text,
        )
        await self.client.chat_tts_text(
            is_user_querying=self.is_user_querying,
            start=False,
            end=True,
            content="",
        )

    async def trigger_chat_rag_text(self):
        await asyncio.sleep(5) # 模拟查询外部RAG的耗时，这里为了不影响GTA安抚话术的播报，直接sleep 5秒
        print("hit ChatRAGText event, start sending...")
        await self.client.chat_rag_text(self.is_user_querying, external_rag='[{"title":"北京天气","content":"今天北京整体以晴到多云为主，但西部和北部地带可能会出现分散性雷阵雨，特别是午后至傍晚时段需注意突发降雨。\n💨 风况与湿度\n风力较弱，一般为 2–3 级南风或西南风\n白天湿度较高，早晚略凉爽"}]')

    async def _tts_topic_loop(self):
        """轮询 /doubao_tts 话题队列，收到文本后发送给大模型做 TTS"""
        self._tts_session_initialized = False
        while self.is_running:
            if self._ros2_mic is None:
                await asyncio.sleep(0.1)
                continue
            text = self._ros2_mic.get_tts_text()
            if text:
                if not self._tts_session_initialized:
                    # 首次 TTS：用 chat_text_query 激活会话，直接播报用户要 TTS 的文本
                    # 构造 prompt 让模型只复述文本，不产生额外回复
                    query_text = f"请直接播报以下内容，不要添加任何其他内容：{text}"
                    print(f"[doubao_tts] 首次 TTS，激活会话并播报: {text}")
                    await self.client.chat_text_query(query_text)
                    self._tts_session_initialized = True
                else:
                    # 后续 TTS：用 chat_tts_text 直接合成
                    print(f"[doubao_tts] 发送 TTS: {text}")
                    await self.trigger_chat_tts_text(text)
            else:
                await asyncio.sleep(0.1)

    def _keyboard_signal(self, sig, frame):
        print(f"receive keyboard Ctrl+C")
        self.stop()

    async def _async_stop(self):
        """异步停止（用于 asyncio 信号处理）"""
        print(f"receive keyboard Ctrl+C")
        self.stop()

    def stop(self):
        self.is_recording = False
        self.is_playing = False
        self.is_running = False

    async def receive_loop(self):
        try:
            while True:
                response = await self.client.receive_server_response()
                self.handle_server_response(response)
                if 'event' in response and (response['event'] == 152 or response['event'] == 153):
                    print(f"receive session finished event: {response['event']}")
                    self.is_session_finished = True
                    break
                if 'event' in response and response['event'] == 359:
                    if self.is_audio_file_input:
                        print(f"receive tts ended event")
                        self.is_session_finished = True
                        break
                    else:
                        if not self.say_hello_over_event.is_set():
                            print(f"receive tts sayhello ended event")
                            self.say_hello_over_event.set()
                        if self.mod == "text":
                            print("请输入内容：")

        except asyncio.CancelledError:
            print("接收任务已取消")
        except Exception as e:
            print(f"接收消息错误: {e}")
        finally:
            self.stop()
            self.is_session_finished = True

    async def process_audio_file(self) -> None:
        await self.process_audio_file_input(self.audio_file_path)

    async def process_text_input(self) -> None:
        await self.client.say_hello()
        await self.say_hello_over_event.wait()

        """主逻辑：处理文本输入和WebSocket通信"""
        # 确保连接最终关闭
        try:
            # 启动输入监听线程
            input_queue = queue.Queue()
            input_thread = threading.Thread(target=self.input_listener, args=(input_queue,), daemon=True)
            input_thread.start()
            # 主循环：处理输入和上下文结束
            while self.is_running:
                try:
                    # 检查是否有输入（非阻塞）
                    input_str = input_queue.get_nowait()
                    if input_str is None:
                        # 输入流关闭
                        print("Input channel closed")
                        break
                    if input_str:
                        # 发送输入内容
                        await self.client.chat_text_query(input_str)
                except queue.Empty:
                    # 无输入时短暂休眠
                    await asyncio.sleep(0.1)
                except Exception as e:
                    print(f"Main loop error: {e}")
                    break
        finally:
            print("exit text input")

    def input_listener(self, input_queue: queue.Queue) -> None:
        """在单独线程中监听标准输入"""
        print("Start listening for input")
        try:
            while True:
                # 读取标准输入（阻塞操作）
                line = sys.stdin.readline()
                if not line:
                    # 输入流关闭
                    input_queue.put(None)
                    break
                input_str = line.strip()
                input_queue.put(input_str)
        except Exception as e:
            print(f"Input listener error: {e}")
            input_queue.put(None)

    async def process_audio_file_input(self, audio_file_path: str) -> None:
        # 读取WAV文件
        with wave.open(audio_file_path, 'rb') as wf:
            chunk_size = config.input_audio_config["chunk"]
            framerate = wf.getframerate()  # 采样率（如16000Hz）
            # 时长 = chunkSize（帧数） ÷ 采样率（帧/秒）
            sleep_seconds = chunk_size / framerate
            print(f"开始处理音频文件: {audio_file_path}")

            # 分块读取并发送音频数据
            while True:
                audio_data = wf.readframes(chunk_size)
                if not audio_data:
                    break  # 文件读取完毕

                await self.client.task_request(audio_data)
                # sleep与chunk对应的音频时长一致，模拟实时输入
                await asyncio.sleep(sleep_seconds)

            print(f"音频文件处理完成，等待服务器响应...")

    async def process_silence_audio(self) -> None:
        """发送一帧 10ms 静音 PCM（320 字节 = 160 samples @ 16kHz/16-bit/mono）。

        【DEPRECATED】当前项目未调用此函数：
        - ROS2 模式下的 idle 保活已由 ros2_mic_source.Ros2MicSource.read() 中的
          「超一帧时长未收到真实 PCM 则返回 chunk_size 字节静音」策略接管；
        - pyaudio 模式下麦克风本身持续输出环境本底声，不存在 idle 超时；
        - ASR EOS（event=459）由 AVVTN VAD 段尾驱动，不需客户端补静音。

        保留作为备用工具（如需手动触发单次静音推送，可直接调用），但请勿在主流程保活
        路径中使用此函数，避免与 Ros2MicSource 重复推流、增加不必要的 audio token 计费。
        """
        silence_data = b'\x00' * 320
        await self.client.task_request(silence_data)

    async def process_microphone_input(self) -> None:
        # 本项目由 AVVTN 唤醒词驱动（喊唤醒词后才开始对话），C++ 端有独立的唤醒应答音，
        # 不需要豆包再主动播报 "您好,您有什么需要呢？" 迎宾语。
        # 同时去掉之前的硬编码测试文本 chat_text_query("你好,我也叫豆包")，避免每次启动
        # 都触发一轮无意义对话。
        # say_hello_over_event 直接置位，避免下游若有依赖时死锁。
        self.say_hello_over_event.set()

        """处理麦克风输入"""
        chunk_size_bytes = config.input_audio_config["chunk"] * 2  # paInt16 = 2 bytes/sample
        if self.mic_source == "ros2":
            # 从 C++ AVVTN 发布的 /avvtn/mic_pcm 订阅 AEC 后的干净 PCM
            from ros2_mic_source import Ros2MicSource
            self._ros2_mic = Ros2MicSource()
            self._ros2_mic.start()
            print("[豆包] mic-source=ros2，等待 /avvtn/mic_pcm 数据...")

            # 启动 TTS 话题轮询任务（复用 Ros2MicSource 节点的 TTS 队列）
            asyncio.create_task(self._tts_topic_loop())

            while self.is_recording:
                try:
                    audio_data = await self._ros2_mic.read(chunk_size_bytes)
                    if not audio_data:
                        await asyncio.sleep(0.05)
                        continue
                    save_input_pcm_to_wav(audio_data, "input.pcm")
                    await self.client.task_request(audio_data)
                except Exception as e:
                    print(f"从 ROS2 读取 PCM 出错: {e}")
                    await asyncio.sleep(0.1)
            return

        # 默认 pyaudio 路径
        stream = self.audio_device.open_input_stream()
        print("已打开麦克风，请讲话...")

        while self.is_recording:
            try:
                # 添加exception_on_overflow=False参数来忽略溢出错误
                audio_data = stream.read(config.input_audio_config["chunk"], exception_on_overflow=False)
                save_input_pcm_to_wav(audio_data, "input.pcm")
                await self.client.task_request(audio_data)
                await asyncio.sleep(0.01)  # 避免CPU过度使用
            except Exception as e:
                print(f"读取麦克风数据出错: {e}")
                await asyncio.sleep(0.1)  # 给系统一些恢复时间

    async def start(self) -> None:
        """启动对话会话"""
        loop = asyncio.get_event_loop()
        # 注册 Ctrl+C 信号处理
        loop.add_signal_handler(signal.SIGINT, lambda: asyncio.create_task(self._async_stop()))
        
        try:
            await self.client.connect()

            if self.mod == "text":
                asyncio.create_task(self.process_text_input())
                asyncio.create_task(self.receive_loop())
                while self.is_running:
                    await asyncio.sleep(0.1)
            else:
                if self.is_audio_file_input:
                    asyncio.create_task(self.process_audio_file())
                    await self.receive_loop()
                else:
                    asyncio.create_task(self.process_microphone_input())
                    asyncio.create_task(self.receive_loop())
                    while self.is_running:
                        await asyncio.sleep(0.1)

            await self.client.finish_session()
            while not self.is_session_finished:
                await asyncio.sleep(0.1)
            await self.client.finish_connection()
            await asyncio.sleep(0.1)
            await self.client.close()
            print(f"dialog request logid: {self.client.logid}, chat mod: {self.mod}")
            save_output_to_file(self.audio_buffer, "output.pcm")
        except Exception as e:
            print(f"会话错误: {e}")
        finally:
            if not self.is_audio_file_input:
                self.audio_device.cleanup()
            if self._ros2_mic is not None:
                self._ros2_mic.stop()


def save_input_pcm_to_wav(pcm_data: bytes, filename: str) -> None:
    """保存PCM数据为WAV文件"""
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(config.input_audio_config["channels"])
        wf.setsampwidth(2)  # paInt16 = 2 bytes
        wf.setframerate(config.input_audio_config["sample_rate"])
        wf.writeframes(pcm_data)


def save_output_to_file(audio_data: bytes, filename: str) -> None:
    """保存原始PCM音频数据到文件"""
    if not audio_data:
        print("No audio data to save.")
        return
    try:
        with open(filename, 'wb') as f:
            f.write(audio_data)
    except IOError as e:
        print(f"Failed to save pcm file: {e}")
