import time
import os
import re
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
        # Optional Whisper prompt: names/vocabulary hints (e.g. "Tuấn, Xin chào, Hello")
        self.prompt = str(config.get("prompt") or "").strip()
        # If auto-detect returns a language outside this list, retry forced to the fallback
        self.allowed_languages = [str(x).lower() for x in (config.get("allowed_languages") or [])]
        self.fallback_language = str(config.get("fallback_language") or "vi").lower()
        self.output_dir = config.get("output_dir")
        self.delete_audio_file = delete_audio_file

        os.makedirs(self.output_dir, exist_ok=True)

    def requires_file(self) -> bool:
        return True

    _LANG_CODES = {"vietnamese": "vi", "english": "en", "chinese": "zh"}
    _FILLERS = {"uhm", "um", "umm", "ummm", "uh", "ư", "ừ", "ừm", "hmm", "hm", "ah", "ờ", "à", "eh", "oh"}

    def _post(self, file_path, data, headers):
        with open(file_path, "rb") as audio_file:
            return requests.post(self.api_url, files={"file": audio_file}, data=data, headers=headers)

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
        # Whisper sometimes appends a "translation" in another script, or repeats the sentence
        lang = str(result.get("language") or "").lower()
        if lang not in ("chinese", "zh", "japanese", "ja"):
            text = re.sub(r"[぀-ヿ㐀-鿿豈-﫿]+[，。！？、,.!? ]*", "", text)
        text = text.strip()
        m = re.match(r"^(.{6,}?)\s*\1$", text, re.S)
        if m:
            text = m.group(1).strip()
        low = text.lower()
        if re.sub(r"[\s.,!?…]+", "", low) in self._FILLERS:
            logger.bind(tag=TAG).info(f"[LOC] bo tieng am u: {text}")
            return ""
        # Whisper sometimes echoes the prompt back on silence/noise
        pl = self.prompt.lower()
        if pl and (pl in low or (low.rstrip(". ") in pl and len(low) >= 0.8 * len(pl))):
            logger.bind(tag=TAG).info(f"[LOC] bo prompt lap lai: {text}")
            return ""
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
            if self.prompt:
                data["prompt"] = self.prompt
            # verbose_json returns per-segment no_speech_prob / avg_logprob for filtering
            data["response_format"] = "verbose_json"


            start_time = time.time()
            response = self._post(file_path, data, headers)
            logger.bind(tag=TAG).debug(
                f"语音识别耗时: {time.time() - start_time:.3f}s | 结果: {response.text}"
            )
            if response.status_code == 200 and self.allowed_languages and not self.language:
                detected = str(response.json().get("language") or "").lower()
                if detected and not any(
                    detected.startswith(a) or self._LANG_CODES.get(detected) == a
                    for a in self.allowed_languages
                ):
                    logger.bind(tag=TAG).info(
                        f"[LOC] ngon ngu '{detected}' ngoai danh sach, thu lai bang '{self.fallback_language}'"
                    )
                    retry = self._post(file_path, {**data, "language": self.fallback_language}, headers)
                    if retry.status_code == 200:
                        response = retry

            if response.status_code == 200:
                text = self._filter_hallucination(response.json())
                return text, file_path
            else:
                raise Exception(f"API请求失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return "", None
        
