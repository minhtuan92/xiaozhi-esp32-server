import math

import numpy as np


class HighPass:
    """2nd-order Butterworth high-pass (biquad) for 16-bit mono PCM, with state kept across frames.

    Removes low-frequency rumble/DC drift (breath, table vibration) that dominates some MEMS mics,
    before the audio reaches VAD and ASR.
    """

    def __init__(self, cutoff_hz: float, sample_rate: int = 16000):
        w0 = 2.0 * math.pi * cutoff_hz / sample_rate
        alpha = math.sin(w0) / (2.0 * math.sqrt(0.5))  # Q = 1/sqrt(2)
        cos_w0 = math.cos(w0)
        a0 = 1.0 + alpha
        self.b0 = (1.0 + cos_w0) / 2.0 / a0
        self.b1 = -(1.0 + cos_w0) / a0
        self.b2 = (1.0 + cos_w0) / 2.0 / a0
        self.a1 = -2.0 * cos_w0 / a0
        self.a2 = (1.0 - alpha) / a0
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    def process(self, pcm_bytes: bytes) -> bytes:
        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float64)
        y = np.empty_like(x)
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        x1, x2, y1, y2 = self.x1, self.x2, self.y1, self.y2
        for i in range(len(x)):
            xi = x[i]
            yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2, x1 = x1, xi
            y2, y1 = y1, yi
            y[i] = yi
        self.x1, self.x2, self.y1, self.y2 = x1, x2, y1, y2
        return np.clip(y, -32768, 32767).astype(np.int16).tobytes()
