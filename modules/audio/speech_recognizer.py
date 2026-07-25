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

import numpy as np
# ── numpy 1.24+ 兼容旧版 numba ──
if not hasattr(np, 'long'):
    np.long = np.int_
if not hasattr(np, 'float'):
    np.float = np.float64

import whisper
import torch
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
            model_name: str = "tiny",
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
    def transcribe(self, audio_bytes: bytes) -> str:
        """传入音频 bytes（WAV / WebM / 原始 PCM），返回转写文本。
        Whisper 内部用 ffmpeg 解码，支持多种格式。"""
        try:
            # 尝试解析为 WAV（用于降噪预处理）
            try:
                audio, sr = self._wav_to_numpy(audio_bytes)
                if self.enable_denoise:
                    audio = self._denoise(audio, sr)
                # 降噪后重新编码为 WAV 写入临时文件
                denoised_wav = self._numpy_to_wav(audio, sr)
                suffix = ".wav"
                file_bytes = denoised_wav
            except Exception:
                # 非 WAV 格式（如 WebM/Opus）→ 跳过降噪，直接传给 Whisper
                suffix = ".audio"
                file_bytes = audio_bytes

            # Whisper 用 ffmpeg 解码，支持 WAV/WebM/MP3 等
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fp:
                fp.write(file_bytes)
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

    # ---- numpy → WAV 编码 ----
    @staticmethod
    def _numpy_to_wav(samples: "np.ndarray", sr: int) -> bytes:
        """float32 numpy array → WAV bytes"""
        import io
        samples_int16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        with io.BytesIO() as buf:
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(samples_int16.tobytes())
            return buf.getvalue()

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


# 模块级快捷函数（供 backend/main.py 的 voice_state 等导入）
def transcribe(wav_bytes: bytes) -> str:
    """懒加载单例，WAV bytes → 转写文本"""
    global _recognizer
    if _recognizer is None:
        _recognizer = SpeechRecognizer(model_name="tiny", language="zh")
    return _recognizer.transcribe(wav_bytes)


_recognizer = None
