"""
Talking detector — detects speech using audio analysis or browser input.
"""
import logging
import struct
import math

logger = logging.getLogger(__name__)

# Try to import pyaudio for local mic capture
try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False
    logger.info("pyaudio not available — use browser-based audio detection")


class TalkingDetector:
    """
    Detects talking using audio level analysis.

    Local mode: captures from microphone via PyAudio.
    Browser mode: receives audio levels from the browser via WebSocket.
    """

    def __init__(self, threshold=500, sample_rate=44100, chunk_size=1024):
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.stream = None
        self.audio = None
        self.is_running = False

    def start_local(self):
        """Start capturing audio from local microphone."""
        if not HAS_PYAUDIO:
            logger.error("pyaudio is required for local audio capture")
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
            logger.info("Local audio capture started")
            return True
        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}")
            return False

    def stop(self):
        """Stop audio capture."""
        self.is_running = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
        self.stream = None
        self.audio = None

    def get_audio_level(self):
        """Read current audio RMS level from microphone."""
        if not self.stream:
            return 0

        try:
            data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            count = len(data) // 2
            shorts = struct.unpack(f'{count}h', data)

            sum_squares = sum(s * s for s in shorts)
            rms = math.sqrt(sum_squares / count) if count > 0 else 0
            return rms
        except Exception as e:
            logger.error(f"Audio read error: {e}")
            return 0

    def is_talking(self, audio_level=None):
        """Check if audio level exceeds the talking threshold."""
        if audio_level is None:
            audio_level = self.get_audio_level()
        return audio_level > self.threshold

    @staticmethod
    def process_browser_audio(rms_level, threshold=500):
        """
        Process audio level sent from the browser.
        Returns True if talking is detected.
        """
        return rms_level > threshold
