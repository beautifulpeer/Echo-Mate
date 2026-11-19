import os

import requests

from config.settings import global_settings
from tools.logger import logger

try:
    import dashscope
    from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer
except ImportError:
    dashscope = None


class TTSModel:
    def __init__(self):
        self.callback = None
        self.text_buffer = ""
        self.synthesizer = None
        if global_settings.LLM_PROVIDER == "dashscope":
            if dashscope is None:
                raise RuntimeError("dashscope is required for DashScope TTS")
            self.synthesizer = SpeechSynthesizer(
                model="cosyvoice-v1", voice="longxiaochun",
                format=AudioFormat.PCM_16000HZ_MONO_16BIT,
                callback=None,
            )

    def tts_stream_set(self, on_open=None, on_complete=None, on_error=None,
                       on_close=None, on_data=None):
        self.callback = {
            "open": on_open,
            "complete": on_complete,
            "error": on_error,
            "close": on_close,
            "data": on_data,
        }
        self.text_buffer = ""
        if global_settings.LLM_PROVIDER == "dashscope":
            class Callback(ResultCallback):
                def on_open(inner_self):
                    if on_open: on_open()
                def on_complete(inner_self):
                    if on_complete: on_complete()
                def on_error(inner_self, message):
                    if on_error: on_error(message)
                def on_close(inner_self):
                    if on_close: on_close()
                def on_data(inner_self, data):
                    if on_data: on_data(data)
            self.synthesizer = SpeechSynthesizer(
                model="cosyvoice-v1", voice="longxiaochun",
                format=AudioFormat.PCM_16000HZ_MONO_16BIT,
                callback=Callback(),
            )
            self.synthesizer.streaming_call("")
        elif on_open:
            on_open()
        return True

    def _minimax_synthesize(self, text):
        response = requests.post(
            global_settings.MINIMAX_BASE_URL + "/t2a_v2",
            headers=self._headers(),
            json={
                "model": os.getenv("MINIMAX_TTS_MODEL", "speech-2.8-turbo"),
                "text": text,
                "stream": False,
                "voice_setting": {
                    "voice_id": os.getenv("MINIMAX_TTS_VOICE", "male-qn-qingse"),
                    "speed": 1.0, "vol": 1.0, "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 16000, "bitrate": 128000,
                    "format": "pcm", "channel": 1,
                },
                "output_format": "hex",
            },
            timeout=global_settings.API_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("base_resp", {}).get("status_code", 0) != 0:
            raise RuntimeError(payload.get("base_resp", {}).get("status_msg", "MiniMax TTS failed"))
        audio = bytes.fromhex(payload["data"]["audio"])
        if self.callback and self.callback["data"]:
            self.callback["data"](audio)

    def _headers(self):
        if not global_settings.MINIMAX_API_KEY:
            raise RuntimeError("MINIMAX_API_KEY is not set")
        return {
            "Authorization": "Bearer " + global_settings.MINIMAX_API_KEY,
            "Content-Type": "application/json",
        }

    def tts_stream_speech_synthesis(self, text_chunk):
        if not text_chunk:
            return True
        if global_settings.LLM_PROVIDER == "dashscope":
            self.synthesizer.streaming_call(text_chunk)
            return True
        self.text_buffer += text_chunk
        if len(self.text_buffer) >= 80 or any(mark in text_chunk for mark in "。！？!?；;\n"):
            text, self.text_buffer = self.text_buffer, ""
            try:
                self._minimax_synthesize(text)
            except Exception as exc:
                logger.error("MiniMax TTS failed: %s" % exc)
                if self.callback and self.callback["error"]:
                    self.callback["error"](str(exc))
                return False
        return True

    def tts_stream_close(self):
        if global_settings.LLM_PROVIDER == "dashscope":
            self.synthesizer.streaming_complete()
            logger.info("Request ID: %s" % self.synthesizer.get_last_request_id())
            return
        if self.text_buffer:
            text, self.text_buffer = self.text_buffer, ""
            self._minimax_synthesize(text)
        if self.callback and self.callback["complete"]:
            self.callback["complete"]()
        if self.callback and self.callback["close"]:
            self.callback["close"]()
