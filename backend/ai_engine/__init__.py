import logging

logger = logging.getLogger("ai_engine")


class AIEngine:
    def __init__(self):
        self._face_verifier = None
        self._object_detector = None
        self._gaze_tracker = None
        self._audio_monitor = None
        self._risk_scorer = None
        self._loaded = False

    def load_all(self):
        if self._loaded:
            return

        logger.info("Loading AI models...")

        from .face_verifier import FaceVerifier
        from .object_detector import ObjectDetector
        from .gaze_tracker import GazeTracker
        from .audio_monitor import AudioMonitor
        from .risk_scorer import RiskScorer

        self._face_verifier = FaceVerifier()
        logger.info("  Face Verifier loaded")

        self._object_detector = ObjectDetector()
        logger.info("  Object Detector loaded")

        self._gaze_tracker = GazeTracker()
        logger.info("  Gaze Tracker loaded")

        self._audio_monitor = AudioMonitor()
        logger.info("  Audio Monitor loaded")

        self._risk_scorer = RiskScorer()
        logger.info("  Risk Scorer loaded")

        self._loaded = True
        logger.info("All AI models loaded successfully.")

    @property
    def face(self):
        return self._face_verifier

    @property
    def objects(self):
        return self._object_detector

    @property
    def gaze(self):
        return self._gaze_tracker

    @property
    def audio(self):
        return self._audio_monitor

    @property
    def risk(self):
        return self._risk_scorer


ai = AIEngine()
