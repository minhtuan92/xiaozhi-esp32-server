import base64
import os
import time
import asyncio
from typing import Optional, Tuple, List

import requests

from config.logger import setup_logging
from core.providers.asr.dto.dto import InterfaceType
from core.providers.asr.base import ASRProviderBase

TAG = __name__
logger = setup_logging()

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class ASRProvider(ASRProviderBase):
    """Google Cloud Speech-to-Text v2 (Chirp 3), one-shot `recognize` per utterance."""

    def __init__(self, config: dict, delete_audio_file: bool):
        self.interface_type = InterfaceType.NON_STREAM
        self.project_id = config.get("project_id")
        self.location = config.get("location", "us")
        self.model = config.get("model_name", "chirp_3")
        languages = config.get("language_codes", ["auto"])
        self.language_codes = [languages] if isinstance(languages, str) else list(languages)
        self.credentials_file = config.get("credentials_file")
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file
        self._credentials = None
        os.makedirs(self.output_dir, exist_ok=True)

    def requires_file(self) -> bool:
        return True

    @property
    def endpoint(self) -> str:
        host = (
            "speech.googleapis.com"
            if self.location == "global"
            else f"{self.location}-speech.googleapis.com"
        )
        return (
            f"https://{host}/v2/projects/{self.project_id}"
            f"/locations/{self.location}/recognizers/_:recognize"
        )

    def build_request(self, audio_bytes: bytes) -> dict:
        return {
            "config": {
                "autoDecodingConfig": {},
                "languageCodes": self.language_codes,
                "model": self.model,
            },
            "content": base64.b64encode(audio_bytes).decode("ascii"),
        }

    @staticmethod
    def parse_response(payload: dict) -> str:
        parts = []
        for result in payload.get("results", []):
            alternatives = result.get("alternatives") or []
            if alternatives:
                parts.append(alternatives[0].get("transcript", "").strip())
        return " ".join(p for p in parts if p)

    def _access_token(self) -> str:
        # google-auth is imported lazily so the server stays light unless Chirp is selected
        import google.auth
        import google.auth.transport.requests
        from google.oauth2 import service_account

        if self._credentials is None:
            if self.credentials_file:
                self._credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_file, scopes=SCOPES
                )
            else:
                self._credentials, _ = google.auth.default(scopes=SCOPES)
        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        return self._credentials.token

    def _recognize(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            body = self.build_request(f.read())
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        response = requests.post(self.endpoint, json=body, headers=headers, timeout=30)
        if response.status_code != 200:
            raise Exception(f"API请求失败: {response.status_code} - {response.text}")
        return self.parse_response(response.json())

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, artifacts=None
    ) -> Tuple[Optional[str], Optional[str]]:
        try:
            if artifacts is None:
                return "", None
            file_path = artifacts.file_path
            start_time = time.time()
            text = await asyncio.to_thread(self._recognize, file_path)
            logger.bind(tag=TAG).debug(
                f"语音识别耗时: {time.time() - start_time:.3f}s | 结果: {text}"
            )
            return text, file_path
        except Exception as e:
            logger.bind(tag=TAG).error(f"语音识别失败: {e}")
            return "", None
