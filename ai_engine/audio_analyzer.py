"""
Audio Analyzer — analyzes audio for talking detection.
"""
import logging
import struct
import math

logger = logging.getLogger(__name__)

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


class AudioAnalyzer:
    """Captures and analyzes audio input for speech detection."""

    def __init__(self, threshold=500, sample_rate=44100, chunk_size=1024):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.stream = None
        self.audio = None
        self.is_running = False

    def start(self):
        """Start audio capture."""
        if not HAS_PYAUDIO:
            logger.warning("pyaudio not available")
            return False

        try:
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )
            self.is_running = True
            return True
        except Exception as e:
            logger.error(f"Audio start failed: {e}")
            return False

    def stop(self):
        """Stop audio capture."""
        self.is_running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()

    def get_rms(self):
        """Get current RMS audio level."""
        if not self.stream:
            return 0
        try:
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            count = len(data) // 2
            shorts = struct.unpack(f'{count}h', data)
            return math.sqrt(sum(s * s for s in shorts) / count) if count else 0
        except Exception:
            return 0

    def is_talking(self):
        """Check if talking is detected."""
        return self.get_rms() > self.threshold
