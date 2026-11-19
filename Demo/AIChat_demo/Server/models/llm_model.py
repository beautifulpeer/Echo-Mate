import json
import re
from datetime import datetime

import requests

try:
    import dashscope
except ImportError:
    dashscope = None

from config.settings import global_settings
from tools.logger import logger


class LLMModel:
    def __init__(self, model_name=None):
        self.model_name = model_name or global_settings.CHAT_MODEL
        self.custom_system_prompt = False
        self.messages = [{"role": "system", "content": self._default_system_content()}]

    def _default_system_content(self):
        now = datetime.now().astimezone().strftime("%Y年%m月%d日 %H:%M:%S %Z")
        return (
            "你是实体桌面机器人 Echo，客户端运行在瑞芯微 RV1106 开发板上，"
            "不是电脑里的纯软件助手。你有麦克风、扬声器、屏幕、摄像头和运动机构。"
            "你能通过已注册的 robot_move 功能前进、后退、左转和右转；"
            "功能调用由服务端识别并下发给开发板执行。"
            "你通过网络连接 MiniMax 服务，但没有浏览器或任意网页检索能力。"
            f"当前服务端时间是：{now}。请始终使用中文，快速、简洁地回答。"
        )

    def set_model_sys_content(self, content):
        self.custom_system_prompt = True
        self.messages[0]["content"] = content

    def add_message(self, role, content):
        self.messages.append({"role": role, "content": content})

    def clear_messages(self):
        self.custom_system_prompt = False
        self.messages = [{"role": "system", "content": self._default_system_content()}]

    def _refresh_runtime_context(self):
        if not self.custom_system_prompt:
            self.messages[0]["content"] = self._default_system_content()

    def _add_question_once(self, question):
        if question and not (
            self.messages and self.messages[-1].get("role") == "user"
            and self.messages[-1].get("content") == question
        ):
            self.add_message("user", question)

    def _minimax_headers(self):
        if not global_settings.MINIMAX_API_KEY:
            raise RuntimeError("MINIMAX_API_KEY is not set")
        return {
            "Authorization": "Bearer " + global_settings.MINIMAX_API_KEY,
            "Content-Type": "application/json",
        }

    def _minimax_url(self):
        return global_settings.MINIMAX_BASE_URL + "/chat/completions"

    @staticmethod
    def _strip_thinking(text):
        return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()

    def get_LLM_response(self, question):
        self._refresh_runtime_context()
        self._add_question_once(question)
        try:
            if global_settings.LLM_PROVIDER == "minimax":
                response = requests.post(
                    self._minimax_url(),
                    headers=self._minimax_headers(),
                    json={"model": self.model_name, "messages": self.messages, "stream": False},
                    timeout=global_settings.API_TIMEOUT,
                )
                response.raise_for_status()
                content = self._strip_thinking(
                    response.json()["choices"][0]["message"]["content"]
                )
            else:
                if dashscope is None:
                    raise RuntimeError("dashscope is required for the DashScope provider")
                response = dashscope.Generation.call(
                    api_key=dashscope.api_key, model=self.model_name,
                    messages=self.messages, result_format="message", stream=False,
                    incremental_output=False, enable_search=True,
                )
                if response["status_code"] != 200:
                    raise RuntimeError("DashScope status: %s" % response["status_code"])
                content = response["output"]["choices"][0]["message"]["content"]
            self.add_message("assistant", content)
            return content
        except Exception as exc:
            logger.error("LLM non-stream request failed: %s" % exc)
            return "抱歉，我暂时无法处理您的请求。"

    def get_LLM_response_stream(self, question):
        self._refresh_runtime_context()
        self._add_question_once(question)
        full_text = ""
        prelude = ""
        reasoning_finished = False
        try:
            if global_settings.LLM_PROVIDER == "minimax":
                response = requests.post(
                    self._minimax_url(),
                    headers=self._minimax_headers(),
                    json={"model": self.model_name, "messages": self.messages, "stream": True},
                    timeout=global_settings.API_TIMEOUT,
                    stream=True,
                )
                response.raise_for_status()
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line or not raw_line.startswith("data:"):
                        continue
                    data = raw_line[5:].strip()
                    if data == "[DONE]":
                        break
                    delta = json.loads(data).get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        if not reasoning_finished:
                            prelude += delta
                            if "</think>" in prelude:
                                delta = prelude.split("</think>", 1)[1].lstrip()
                                reasoning_finished = True
                            elif "<think>" in prelude or len(prelude) < 16:
                                continue
                            else:
                                delta = prelude
                                reasoning_finished = True
                        if delta:
                            full_text += delta
                            yield delta
            else:
                if dashscope is None:
                    raise RuntimeError("dashscope is required for the DashScope provider")
                responses = dashscope.Generation.call(
                    api_key=dashscope.api_key, model=self.model_name,
                    messages=self.messages, result_format="message", stream=True,
                    incremental_output=True, enable_search=True,
                )
                for response in responses:
                    if response["status_code"] != 200:
                        raise RuntimeError("DashScope status: %s" % response["status_code"])
                    for choice in response["output"]["choices"]:
                        chunk = choice["message"]["content"]
                        full_text += chunk
                        yield chunk
            self.add_message("assistant", full_text)
        except Exception as exc:
            logger.error("LLM stream request failed: %s" % exc)
            yield -1
