import os

try:
    import dashscope
except ImportError:
    dashscope = None


class Settings:
    protocol_version = int(os.getenv("AICHAT_PROTOCOL_VERSION", "2"))

    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "minimax").lower()
    MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
    MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/")
    INTENT_MODEL = os.getenv("INTENT_MODEL", "MiniMax-M2.7")
    CHAT_MODEL = os.getenv("CHAT_MODEL", "MiniMax-M2.7")

    ASR_DEVICE = os.getenv("ASR_DEVICE", "cpu")
    VAD_DEVICE = os.getenv("VAD_DEVICE", "cpu")
    API_TIMEOUT = int(os.getenv("LLM_API_TIMEOUT", "60"))

    def __init__(self):
        if dashscope is not None:
            dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")

    def Set_API_Key(self, aliyun_api_key):
        # Protocol v2 clients still send this legacy field. MiniMax credentials
        # stay on the server and are never accepted from the device.
        if self.LLM_PROVIDER == "dashscope" and aliyun_api_key:
            if dashscope is None:
                raise RuntimeError("dashscope is required for the DashScope provider")
            dashscope.api_key = aliyun_api_key


global_settings = Settings()
