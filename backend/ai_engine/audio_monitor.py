"""
Audio analysis — Voice Activity Detection.
Detects if someone is speaking during the exam.
"""

import numpy as np
import torch
import logging
from typing import Optional

logger = logging.getLogger("ai_engine.audio")


class AudioMonitor:
    def __init__(self):
        self.vad_model = None
        self.vad_loaded = False
        self._load_vad()

        # Ambient noise calibration
        self.ambient_rms_baseline: Optional[float] = None
        self.calibration_frames = 0
        self.calibration_rms_sum = 0.0

    def _load_vad(self):
        try:
            self.vad_model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self.get_speech_timestamps = utils[0]
            self.vad_loaded = True
            logger.info("Silero VAD loaded successfully")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD: {e}")
            logger.warning("Falling back to energy-based speech detection")
            self.vad_loaded = False

    def analyze_chunk(self, audio_data: list, sample_rate: int = 16000) -> dict:
        """
        Analyze an audio chunk (~1 second).
        audio_data: list of float samples [-1.0 to 1.0]
        """
        result = {
            "has_speech": False,
            "speech_confidence": 0.0,
            "audio_rms": 0.0,
            "is_silent": False,
            "flags": [],
        }

        audio = np.array(audio_data, dtype=np.float32)

        if len(audio) == 0:
            return result

        # Compute RMS energy
        rms = float(np.sqrt(np.mean(audio ** 2)))
        result["audio_rms"] = round(rms, 6)

        # Calibrate ambient noise (first 5 seconds)
        if self.calibration_frames < 5:
            self.calibration_rms_sum += rms
            self.calibration_frames += 1
            if self.calibration_frames == 5:
                self.ambient_rms_baseline = self.calibration_rms_sum / 5
                logger.info(f"Ambient noise baseline: {self.ambient_rms_baseline:.6f}")
            return result

        # Check for suspicious silence (mic covered/muted)
        if self.ambient_rms_baseline and rms < self.ambient_rms_baseline * 0.05:
            result["is_silent"] = True

        # Voice Activity Detection
        if self.vad_loaded:
            try:
                tensor = torch.from_numpy(audio)
                if tensor.dim() == 1:
                    tensor = tensor.unsqueeze(0)

                # Silero VAD expects 16kHz audio
                if sample_rate != 16000:
                    # Simple resampling by interpolation
                    target_len = int(len(audio) * 16000 / sample_rate)
                    audio_16k = np.interp(
                        np.linspace(0, len(audio), target_len),
                        np.arange(len(audio)),
                        audio,
                    )
                    tensor = torch.from_numpy(audio_16k.astype(np.float32)).unsqueeze(0)

                speech_timestamps = self.get_speech_timestamps(
                    tensor.squeeze(), self.vad_model, sampling_rate=16000
                )

                if speech_timestamps:
                    result["has_speech"] = True
                    # Estimate confidence from proportion of speech
                    total_speech = sum(
                        ts["end"] - ts["start"] for ts in speech_timestamps
                    )
                    result["speech_confidence"] = min(
                        total_speech / tensor.shape[-1], 1.0
                    )

            except Exception as e:
                logger.debug(f"VAD error: {e}")
                # Fallback to energy-based detection
                result["has_speech"] = self._energy_based_vad(audio)
        else:
            result["has_speech"] = self._energy_based_vad(audio)

        # Generate flags
        if result["has_speech"]:
            result["flags"].append({
                "flag_type": "SPEECH_DETECTED",
                "severity": "MEDIUM",
                "message": f"Voice activity detected (confidence: {result['speech_confidence']:.0%})",
                "risk_points": 2,
            })

        return result

    def _energy_based_vad(self, audio: np.ndarray) -> bool:
        """Simple energy + zero-crossing rate based VAD."""
        rms = np.sqrt(np.mean(audio ** 2))

        # Zero-crossing rate (speech has moderate ZCR)
        zero_crossings = np.sum(np.abs(np.diff(np.sign(audio)))) / (2 * len(audio))

        # Speech typically has RMS > ambient*3 and ZCR between 0.02-0.2
        if self.ambient_rms_baseline:
            energy_threshold = self.ambient_rms_baseline * 3
        else:
            energy_threshold = 0.01

        return rms > energy_threshold and 0.02 < zero_crossings < 0.25