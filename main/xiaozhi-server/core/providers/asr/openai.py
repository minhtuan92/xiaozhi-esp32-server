import time
import os
from config.logger import setup_logging
from typing import Optional, Tuple, List
from core.providers.asr.dto.dto import InterfaceType
from core.providers.asr.base import ASRProviderBase

import requests

TAG = __name__
logger = setup_logging()

class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        self.interface_type = InterfaceType.NON_STREAM
        self.api_key = config.get("api_key")
        self.api_url = config.get("base_url")
        self.model = config.get("model_name")
        # Optional: ISO-639-1 code (vi, en, zh). Empty/"auto" lets Whisper detect.
        language = str(config.get("language") or "").strip().lower()
        self.language = "" if language == "auto" else language
        self.temperature = config.get("temperature")
        self.output_dir = config.get("output_dir")
        self.delete_audio_file = delete_audio_file

        os.makedirs(self.output_dir, exist_ok=True)

    def requires_file(self) -> bool:
        return True

    # Phrases Whisper tends to invent on silence/noise (lower-case, substring match)
    _HALLUCINATIONS = (
        "thanks for watching", "thank you for watching", "subtitles by",
        "amara.org", "please subscribe", "like and subscribe",
        "cảm ơn các bạn đã theo dõi", "cảm ơn các bạn đã xem",
        "hãy subscribe", "đăng ký kênh", "ghiền mì gõ",
        "字幕", "请不吝点赞",
    )

    def _filter_hallucination(self, result: dict) -> str:
        """Drop segments Whisper itself flags as non-speech, and known stock phrases."""
        segments = result.get("segments")
        if segments:
            kept = [
                s.get("text", "")
                for s in segments
                if not (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -0.7)
            ]
            text = "".join(kept)
        else:
            text = result.get("text", "")
        text = text.strip()
        low = text.lower()
        if any(p in low for p in self._HALLUCINATIONS):
            logger.bind(tag=TAG).info(f"[LOC] bo cau ao giac: {text}")
            return ""
        return text

    async def speech_to_text(self, opus_data: List[bytes], session_id: str, artifacts=None) -> Tuple[Optional[str], Optional[str]]:
        file_path = None
        try:
            if artifacts is None:
                return "", None
            file_path = artifacts.file_path
                
            logger.bind(tag=TAG).info(f"file path: {file_path}")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }
            
            # 使用data参数传递模型名称
            data = {
                "model": self.model
            }
            if self.language:
                data["language"] = self.language
            if self.temperature is not None:
                data["temperature"] = self.temperature
            # verbose_json returns per-segment no_speech_prob / avg_logprob for filtering
            data["response_format"] = "verbose_json"


            with open(file_path, "rb") as audio_file:  # 使用with语句确保文件关闭
                files = {
                    "file": audio_file
                }

                start_time = time.time()
                response = requests.post(
                    self.api_url,
                    files=files,
                    data=data,
                    headers=headers
                )
                logger.bind(tag=TAG).debug(
                    f"语音识别耗时: {time.time() - start_time:.3f}s | 结果: {response.text}"
                )

            if response.status_code == 200:
                text = self._filter_hallucination(response.json())
                return text, file_path
            else:
                raise Exception(f"API请求失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return "", None
        
