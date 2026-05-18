import os
import uuid
import pyaudio

# ---- 系统 prompt --------------------------------------------------------
# system_role 从外部 markdown 文件加载，便于产品/运营独立修改 prompt 而不动 Python 代码。
# 文件路径默认 prompts/cmcc_lingxi.md，可通过环境变量 SYSTEM_PROMPT_FILE 覆盖（例如多套人设切换）。
_PROMPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PROMPT = os.path.join(_PROMPT_DIR, "prompts", "cmcc_lingxi.md")
_SYSTEM_PROMPT_FILE = os.environ.get("SYSTEM_PROMPT_FILE", _DEFAULT_PROMPT)
with open(_SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as _f:
    _SYSTEM_ROLE = _f.read()

# 配置信息
ws_connect_config = {
    "base_url": "wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
    "headers": {
        "X-Api-App-ID": "5244401887",
        "X-Api-Access-Key": "1cuNco4HeJZVsl-IoBQn9r5ZjUs8ouxj",
        "X-Api-Resource-Id": "volc.speech.dialog",  # 固定值
        "X-Api-App-Key": "PlgvMymc7f3tQnJ6",  # 固定值
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
}

start_session_req = {
    "asr": {
        "extra": {
            "end_smooth_window_ms": 1500,
        },
    },
    "tts": {
        "speaker": "zh_female_vv_jupiter_bigtts",
        # "speaker": "S_XXXXXX",  // 指定自定义的复刻音色,需要填下character_manifest
        # "speaker": "ICL_zh_female_aojiaonvyou_tob" // 指定官方复刻音色，不需要填character_manifest
        "audio_config": {
            "channel": 1,
            "format": "pcm",
            "sample_rate": 24000
        },
    },
    "dialog": {
        "bot_name": "灵犀",
        "system_role": _SYSTEM_ROLE,
        # speaking_style 已在 system_role 内详述，这里不再重复以免冲突
        "location": {
          "city": "南京",
        },
        "extra": {
            "strict_audit": False,
            "audit_response": "抱歉，这个问题我暂时不能回答，请您去人工柜台。",
            "recv_timeout": 10,
            "input_mod": "audio"
        }
    }
}

input_audio_config = {
    "chunk": 3200,
    "format": "pcm",
    "channels": 1,
    "sample_rate": 16000,
    "bit_size": pyaudio.paInt16
}

output_audio_config = {
    "chunk": 3200,
    "format": "pcm",
    "channels": 1,
    "sample_rate": 24000,
    "bit_size": pyaudio.paFloat32
}

# ---- 对话体验开关 ----------------------------------------------------------
# 安抚话术：在豆包 ASR 判定一句话说完（event=459）后，是否主动下发
# ChatTTSText 先播一段“请稍等”话术，同时后台去查 RAG。默认关闭，
# 避免短问答场景也被安抚话术打断。需要时可设为 True 开启。
enable_filler_speech: bool = False
