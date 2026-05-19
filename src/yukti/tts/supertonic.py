"""Local Supertonic TTS (bundled ONNX models under assets/)."""

from pathlib import Path

import numpy as np
import soundfile as sf

from yukti.config import TTS_ONNX_DIR, TTS_VOICES_DIR
from yukti.tts.engine import load_text_to_speech, load_voice_style


class LocalTTS:
    def __init__(
        self,
        voice: str = "F2",
        lang: str = "en",
        total_step: int = 8,
        speed: float = 1.05,
    ):
        if not TTS_ONNX_DIR.is_dir():
            raise FileNotFoundError(
                f"TTS models missing at {TTS_ONNX_DIR}. Run scripts/setup_assets.sh"
            )
        self.lang = lang
        self.total_step = total_step
        self.speed = speed
        voice_path = TTS_VOICES_DIR / f"{voice}.json"
        if not voice_path.is_file():
            raise FileNotFoundError(f"Voice not found: {voice_path}")
        self._tts = load_text_to_speech(str(TTS_ONNX_DIR), use_gpu=False)
        self._style = load_voice_style([str(voice_path)], verbose=False)
        self.sample_rate = self._tts.sample_rate

    def synthesize(self, text: str) -> np.ndarray:
        wav, duration = self._tts(text, self.lang, self._style, self.total_step, self.speed)
        samples = int(self.sample_rate * duration[0].item())
        return wav[0, :samples]

    def synthesize_to_file(self, text: str, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        audio = self.synthesize(text)
        sf.write(path, audio, self.sample_rate)
        return path
