content = """import cv2
import numpy as np
from pathlib import Path
import logging

logger = logging.getLogger('ai_engine.face')


class FaceVerifier:
    def __init__(self):
        # Use Haar Cascade (more reliable across different cameras)
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.alt_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
        )

        # Also try DNN if available
        self.dnn_detector = None
        try:
            models_dir = Path(__file__).parent.parent / 'ai_models'
            proto = str(models_dir / 'deploy.prototxt')
            model = str(models_dir / 'res10_300x300_ssd.caffemodel')
            if Path(proto).exists() and Path(model).exists():
                self.dnn_detector = cv2.dnn.readNetFromCaffe(proto, model)
                logger.info('DNN face detector loaded as backup')
        except Exception as e:
            logger.warning(f'DNN face detector not available: {e}')

        logger.info('Face verifier initialized (Haar + DNN)')

    def detect_faces(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        h, w = frame.shape[:2]

        faces = []

        # Method 1: Haar Cascade (primary)
        detections = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        for (x, y, fw, fh) in detections:
            x1, y1, x2, y2 = x, y, x + fw, y + fh
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 - x1 > 30 and y2 - y1 > 30:
                faces.append({
                    'bbox': (x1, y1, x2, y2),
                    'confidence': 0.85,
                    'crop': frame[y1:y2, x1:x2].copy(),
                })

        # Method 2: Alt cascade if primary found nothing
        if len(faces) == 0:
            detections = self.alt_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=3,
                minSize=(50, 50),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            for (x, y, fw, fh) in detections:
                x1, y1, x2, y2 = x, y, x + fw, y + fh
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                if x2 - x1 > 30 and y2 - y1 > 30:
                    faces.append({
                        'bbox': (x1, y1, x2, y2),
                        'confidence': 0.75,
                        'crop': frame[y1:y2, x1:x2].copy(),
                    })

        # Method 3: DNN detector as last resort
        if len(faces) == 0 and self.dnn_detector is not None:
            blob = cv2.dnn.blobFromImage(
                cv2.resize(frame, (300, 300)), 1.0, (300, 300),
                (104.0, 177.0, 123.0)
            )
            self.dnn_detector.setInput(blob)
            dnn_detections = self.dnn_detector.forward()
            for i in range(dnn_detections.shape[2]):
                confidence = dnn_detections[0, 0, i, 2]
                if confidence > 0.5:
                    box = dnn_detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                    x1, y1, x2, y2 = box.astype(int)
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    if x2 - x1 > 30 and y2 - y1 > 30:
                        faces.append({
                            'bbox': (x1, y1, x2, y2),
                            'confidence': float(confidence),
                            'crop': frame[y1:y2, x1:x2].copy(),
                        })

        return faces

    def extract_embedding(self, face_crop):
        face_resized = cv2.resize(face_crop, (100, 100))
        hsv = cv2.cvtColor(face_resized, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)

        # Combine color histogram + LBP-like texture
        hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [16], [0, 256])
        hist_v = cv2.calcHist([hsv], [2], None, [16], [0, 256])

        # Add spatial info (divide face into 4 quadrants)
        mid_y, mid_x = gray.shape[0] // 2, gray.shape[1] // 2
        q1 = cv2.calcHist([gray[:mid_y, :mid_x]], [0], None, [16], [0, 256])
        q2 = cv2.calcHist([gray[:mid_y, mid_x:]], [0], None, [16], [0, 256])
        q3 = cv2.calcHist([gray[mid_y:, :mid_x]], [0], None, [16], [0, 256])
        q4 = cv2.calcHist([gray[mid_y:, mid_x:]], [0], None, [16], [0, 256])

        embedding = np.concatenate([
            hist_h.flatten(), hist_s.flatten(), hist_v.flatten(),
            q1.flatten(), q2.flatten(), q3.flatten(), q4.flatten()
        ])
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding

    def compare_embeddings(self, emb1, emb2):
        if emb1 is None or emb2 is None:
            return 0.0
        if len(emb1) != len(emb2):
            return 0.0
        dot = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))

    def verify_frame(self, frame, baseline_embedding):
        result = {
            'face_count': 0,
            'face_detected': False,
            'identity_match': False,
            'similarity': 0.0,
            'flags': [],
            'face_bbox': None,
            'face_crop': None,
        }

        faces = self.detect_faces(frame)
        result['face_count'] = len(faces)

        if len(faces) == 0:
            result['flags'].append({
                'flag_type': 'NO_FACE_DETECTED',
                'severity': 'HIGH',
                'message': 'No face detected in frame',
                'risk_points': 3,
            })
            return result

        if len(faces) > 1:
            result['flags'].append({
                'flag_type': 'MULTIPLE_FACES',
                'severity': 'CRITICAL',
                'message': str(len(faces)) + ' faces detected in frame',
                'risk_points': 8,
            })

        primary = max(faces, key=lambda f: (f['bbox'][2] - f['bbox'][0]) * (f['bbox'][3] - f['bbox'][1]))
        result['face_detected'] = True
        result['face_bbox'] = primary['bbox']
        result['face_crop'] = primary['crop']

        if baseline_embedding is not None:
            current_embedding = self.extract_embedding(primary['crop'])
            similarity = self.compare_embeddings(baseline_embedding, current_embedding)
            result['similarity'] = similarity
            if similarity >= 0.4:
                result['identity_match'] = True
            else:
                result['flags'].append({
                    'flag_type': 'IDENTITY_MISMATCH',
                    'severity': 'CRITICAL',
                    'message': 'Face does not match enrolled student (similarity: ' + str(round(similarity, 2)) + ')',
                    'risk_points': 10,
                })

        return result
"""

with open('ai_engine/face_verifier.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('face_verifier.py updated (' + str(len(content.strip().split(chr(10)))) + ' lines)')
print('Now run: python test_ai2.py')