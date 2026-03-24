import cv2
import numpy as np
import logging

logger = logging.getLogger('ai_engine.gaze')


class GazeTracker:
    def __init__(self):
        self.face_mesh = None
        self.use_mediapipe = False

        try:
            import mediapipe as mp
            # Try new API first (0.10.14+)
            if hasattr(mp.solutions, 'face_mesh'):
                self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self.use_mediapipe = True
                logger.info('MediaPipe FaceMesh loaded (legacy API)')
            else:
                # New task-based API
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision
                logger.info('MediaPipe new API detected but using OpenCV fallback for simplicity')
                self.use_mediapipe = False
        except Exception as e:
            logger.warning(f'MediaPipe not available: {e}')
            logger.warning('Gaze tracking will use OpenCV cascade fallback')
            self.use_mediapipe = False

        # OpenCV fallback: Haar cascade for eye detection
        if not self.use_mediapipe:
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            self.eye_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_eye.xml'
            )

    def analyze(self, frame):
        result = {
            'gaze_direction': 'UNKNOWN',
            'head_pose': {'yaw': 0, 'pitch': 0},
            'looking_at_screen': True,
            'iris_position': None,
            'flags': [],
        }

        if self.use_mediapipe and self.face_mesh is not None:
            return self._analyze_mediapipe(frame, result)
        else:
            return self._analyze_opencv(frame, result)

    def _analyze_mediapipe(self, frame, result):
        LEFT_IRIS = [474, 475, 476, 477]
        RIGHT_IRIS = [469, 470, 471, 472]
        LEFT_EYE_INNER = 362
        LEFT_EYE_OUTER = 263
        RIGHT_EYE_INNER = 133
        RIGHT_EYE_OUTER = 33
        NOSE_TIP = 1
        CHIN = 152
        LEFT_EYE_LEFT = 33
        RIGHT_EYE_RIGHT = 263
        LEFT_MOUTH = 61
        RIGHT_MOUTH = 291

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mesh_results = self.face_mesh.process(rgb)

        if not mesh_results.multi_face_landmarks:
            return result

        landmarks = mesh_results.multi_face_landmarks[0]
        h, w = frame.shape[:2]

        left_iris = self._get_iris_center(landmarks, LEFT_IRIS, w, h)
        right_iris = self._get_iris_center(landmarks, RIGHT_IRIS, w, h)
        left_inner = self._get_point(landmarks, LEFT_EYE_INNER, w, h)
        left_outer = self._get_point(landmarks, LEFT_EYE_OUTER, w, h)
        right_inner = self._get_point(landmarks, RIGHT_EYE_INNER, w, h)
        right_outer = self._get_point(landmarks, RIGHT_EYE_OUTER, w, h)

        left_ratio = self._iris_position_ratio(left_iris, left_inner, left_outer)
        right_ratio = self._iris_position_ratio(right_iris, right_inner, right_outer)

        if left_ratio is not None and right_ratio is not None:
            avg_ratio = (left_ratio + right_ratio) / 2
            result['iris_position'] = round(avg_ratio, 3)

            if avg_ratio < 0.30:
                result['gaze_direction'] = 'LEFT'
                result['looking_at_screen'] = False
            elif avg_ratio > 0.70:
                result['gaze_direction'] = 'RIGHT'
                result['looking_at_screen'] = False
            else:
                result['gaze_direction'] = 'CENTER'
                result['looking_at_screen'] = True

        # Head pose
        nose = self._get_point(landmarks, NOSE_TIP, w, h)
        left_eye = self._get_point(landmarks, LEFT_EYE_LEFT, w, h)
        right_eye = self._get_point(landmarks, RIGHT_EYE_RIGHT, w, h)
        left_mouth = self._get_point(landmarks, LEFT_MOUTH, w, h)
        right_mouth = self._get_point(landmarks, RIGHT_MOUTH, w, h)
        chin = self._get_point(landmarks, CHIN, w, h)

        eye_cx = (left_eye[0] + right_eye[0]) / 2
        mouth_cx = (left_mouth[0] + right_mouth[0]) / 2
        face_cx = (eye_cx + mouth_cx) / 2
        face_width = abs(right_eye[0] - left_eye[0])

        if face_width > 1:
            yaw = ((nose[0] - face_cx) / face_width) * 90
            eye_cy = (left_eye[1] + right_eye[1]) / 2
            nose_to_eyes = nose[1] - eye_cy
            nose_to_chin = chin[1] - nose[1]
            if nose_to_chin > 0:
                pitch = ((nose_to_eyes / nose_to_chin) - 0.7) * 60
            else:
                pitch = 0
            result['head_pose'] = {'yaw': round(yaw, 1), 'pitch': round(pitch, 1)}

            if abs(yaw) > 30:
                result['looking_at_screen'] = False
                result['gaze_direction'] = 'LEFT' if yaw < 0 else 'RIGHT'
            if abs(pitch) > 25:
                result['looking_at_screen'] = False
                result['gaze_direction'] = 'DOWN' if pitch > 0 else 'UP'

        return result

    def _analyze_opencv(self, frame, result):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]

        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        if len(faces) == 0:
            return result

        # Get the largest face
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
        face_center_x = x + fw / 2
        frame_center_x = w / 2

        # Simple head direction based on face position in frame
        offset_ratio = (face_center_x - frame_center_x) / frame_center_x

        if offset_ratio < -0.3:
            result['gaze_direction'] = 'LEFT'
            result['looking_at_screen'] = False
        elif offset_ratio > 0.3:
            result['gaze_direction'] = 'RIGHT'
            result['looking_at_screen'] = False
        else:
            result['gaze_direction'] = 'CENTER'
            result['looking_at_screen'] = True

        result['head_pose'] = {'yaw': round(offset_ratio * 45, 1), 'pitch': 0}

        # Check if eyes are visible (if not, head might be turned too far)
        face_roi = gray[y:y+fh, x:x+fw]
        eyes = self.eye_cascade.detectMultiScale(face_roi, 1.1, 3)
        if len(eyes) == 0:
            result['looking_at_screen'] = False
            result['gaze_direction'] = 'AWAY'

        return result

    def _get_iris_center(self, landmarks, iris_indices, w, h):
        points = []
        for idx in iris_indices:
            lm = landmarks.landmark[idx]
            points.append((lm.x * w, lm.y * h))
        if points:
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            return (cx, cy)
        return None

    def _get_point(self, landmarks, idx, w, h):
        lm = landmarks.landmark[idx]
        return (lm.x * w, lm.y * h)

    def _iris_position_ratio(self, iris_center, eye_inner, eye_outer):
        if iris_center is None or eye_inner is None or eye_outer is None:
            return None
        eye_width = np.sqrt((eye_outer[0] - eye_inner[0])**2 + (eye_outer[1] - eye_inner[1])**2)
        if eye_width < 1:
            return None
        iris_dist = np.sqrt((iris_center[0] - eye_inner[0])**2 + (iris_center[1] - eye_inner[1])**2)
        return min(max(iris_dist / eye_width, 0), 1)
