"""
SpeechRecognizer — Whisper-turbo 类封装 + 噪声降噪 + 队列输出

- 单例加载 whisper 模型
- noisereduce 频谱降噪预处理
- 线程安全的结果队列
"""
import os
import logging
import tempfile
import queue
import threading

import whisper
import torch
import numpy as np
from io import BytesIO
import wave

logger = logging.getLogger(__name__)

# ---- 噪声降噪：尝试加载 noisereduce，不可用则跳过 ----
try:
    import noisereduce as nr

    _NOISEREDUCE_AVAILABLE = True
except ImportError:
    _NOISEREDUCE_AVAILABLE = False


class SpeechRecognizer:
    """Whisper STT + 可选噪声降噪 + 结果队列"""

    def __init__(
            self,
            model_name: str = "turbo",
            language: str = "zh",
            device: str = "cpu",
            enable_denoise: bool = True,
    ):
        self.model_name = model_name
        self.language = language
        self.device = device
        self.enable_denoise = enable_denoise and _NOISEREDUCE_AVAILABLE

        logger.info(f"加载 Whisper 模型: {model_name} (device={device})")
        self._model = whisper.load_model(model_name).to(device)
        self._result_queue: queue.Queue = queue.Queue()
        self._running = False

        if self.enable_denoise:
            logger.info("噪声降噪已启用 (noisereduce)")
        elif enable_denoise and not _NOISEREDUCE_AVAILABLE:
            logger.warning("noisereduce 未安装，降噪已禁用。安装: pip install noisereduce")

    # ---- 降噪 ----
    def _denoise(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """频谱降噪：去除稳态背景噪声（引擎声、风噪等）"""
        if not self.enable_denoise or len(audio) < sr // 10:  # 太短不处理
            return audio
        try:
            # 取前 0.3 秒作为噪声样本，用频谱门降噪
            noise_sample = audio[: int(sr * 0.3)]
            if len(noise_sample) < sr // 10:
                noise_sample = audio[: len(audio) // 2]
            reduced = nr.reduce_noise(
                y=audio, sr=sr,
                y_noise=noise_sample,
                prop_decrease=0.8,
                stationary=True,
            )
            return reduced.astype(np.float32)
        except Exception:
            return audio

    # ---- WAV 解码 ----
    @staticmethod
    def _wav_to_numpy(wav_bytes: bytes):
        """WAV bytes → (samples_float32, sample_rate)"""
        with wave.open(BytesIO(wav_bytes), "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            return samples, sr

    # ---- 转写 ----
    def transcribe(self, wav_bytes: bytes) -> str:
        """传入 WAV bytes，返回转写文本。降噪在 Whisper 前执行。"""
        try:
            audio, sr = self._wav_to_numpy(wav_bytes)

            if self.enable_denoise:
                audio = self._denoise(audio, sr)

            # Whisper 需要 WAV 文件路径（Windows ffmpeg 兼容）
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fp:
                fp.write(wav_bytes)
                fp.flush()
                temp_path = fp.name

            try:
                res = self._model.transcribe(
                    temp_path,
                    language=self.language,
                    fp16=self.device.startswith("cuda"),
                    word_timestamps=False,
                    verbose=False,
                )
                text = res["text"].strip()
                if text:
                    logger.info(f"[STT] {text}")
                return text
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        except Exception as e:
            logger.error(f"转写失败: {e}")
            return ""

    # ---- 队列接口（供外部消费）----
    def put_result(self, text: str):
        """将识别结果放入队列"""
        if text:
            self._result_queue.put({"text": text, "ts": __import__("time").time()})

    def get_result(self, timeout: float = 0.0):
        """非阻塞获取结果，无结果返回 None"""
        try:
            return self._result_queue.get_nowait()
        except queue.Empty:
            return None

    @property
    def has_result(self) -> bool:
        return not self._result_queue.empty()
