import queue

from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    """No-speaker mode: no audio is synthesized or sent and the device is never told "tts start".

    The translation text is still logged ([DICH]) by the connection. Because the device never enters
    the speaking state, its microphone keeps streaming and the next sentence can be spoken right
    away (no half-duplex wait, no lost sentence starts). send_stt_message() checks `mute_device`.
    """

    mute_device = True

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)

    async def text_to_speak(self, text, output_file):
        # Never called: the worker threads below only drain their queues.
        return None

    def tts_text_priority_thread(self):
        while not self.conn.stop_event.is_set():
            try:
                self.tts_text_queue.get(timeout=1)
            except queue.Empty:
                continue

    def _audio_play_priority_thread(self):
        while not self.conn.stop_event.is_set():
            try:
                self.tts_audio_queue.get(timeout=1)
            except queue.Empty:
                continue
