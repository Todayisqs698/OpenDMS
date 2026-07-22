"""
AudioPipeline — 独立音频处理线程

串联: Recorder(VAD分段) → SpeechRecognizer(降噪+Whisper) → 结果队列

与视觉管线完全解耦，不阻塞摄像头主循环。
"""
import time
import logging
import threading

logger = logging.getLogger(__name__)


class AudioPipeline:
    """独立线程的音频管线：录音 → 转写 → 队列"""

    def __init__(self, recognizer=None):
        from modules.audio.recorder import Recorder
        from modules.audio.speech_recognizer import SpeechRecognizer

        self.recorder = Recorder(
            rate=16000,
            frame_ms=30,
            silence_limit=1.0,
            channels=1,
            aggressiveness=3,
        )
        self.recognizer = recognizer or SpeechRecognizer(
            model_name="turbo",
            language="zh",
            device="cpu",
            enable_denoise=True,
        )
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_text = ""
        self._last_ts = 0.0
        self._lock = threading.Lock()

    # ---- 生命周期 ----
    def start(self):
        """启动音频处理线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="audio-pipeline")
        self._thread.start()
        logger.info("音频管线已启动")

    def stop(self):
        """停止音频处理线程"""
        self._running = False
        logger.info("音频管线已停止")

    def pause(self):
        """暂停录音（TTS 播报前）"""
        self.recorder.pause()

    def resume(self):
        """恢复录音（TTS 播报后）"""
        self.recorder.resume()

    # ---- 结果获取（线程安全）----
    def get_result(self, timeout: float = 0.0) -> dict | None:
        """非阻塞获取最新识别结果，无结果返回 None"""
        return self.recognizer.get_result(timeout)

    @property
    def has_result(self) -> bool:
        return self.recognizer.has_result

    @property
    def last_text(self) -> str:
        with self._lock:
            return self._last_text

    # ---- 内部循环 ----
    def _loop(self):
        """音频线程主循环：录音 → VAD 分段 → 降噪 → Whisper → 队列"""
        logger.info("音频线程启动")
        try:
            for seg in self.recorder.record_stream():
                if not self._running:
                    break
                wav_bytes = seg["wav"]
                ts = seg["ts"]

                # Whisper 转写（含降噪）
                text = self.recognizer.transcribe(wav_bytes)

                if text:
                    # 推入队列供主循环消费
                    self.recognizer.put_result(text)
                    with self._lock:
                        self._last_text = text
                        self._last_ts = ts
        except Exception as e:
            logger.error(f"音频线程异常: {e}", exc_info=True)
        logger.info("音频线程退出")
