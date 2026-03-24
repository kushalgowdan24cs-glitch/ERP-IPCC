import cv2
import numpy as np
from ai_engine import ai

print("Loading AI models...")
ai.load_all()
print("Models loaded!\n")

# Capture one frame from your webcam
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Cannot open webcam!")
    exit()

print("Capturing frame from webcam...")
ret, frame = cap.read()
cap.release()

if not ret or frame is None:
    print("ERROR: Failed to capture frame!")
    exit()

print(f"Frame captured: {frame.shape}\n")

# Test 1: Face Detection
print("=" * 40)
print("TEST 1: Face Detection")
print("=" * 40)
faces = ai.face.detect_faces(frame)
print(f"Faces found: {len(faces)}")
for i, face in enumerate(faces):
    print(f"  Face {i+1}: confidence={face['confidence']:.2f}, bbox={face['bbox']}")

# Test 2: Face Verification (with no baseline)
print()
print("=" * 40)
print("TEST 2: Face Verification")
print("=" * 40)
result = ai.face.verify_frame(frame, None)
print(f"Face detected: {result['face_detected']}")
print(f"Face count: {result['face_count']}")
print(f"Flags: {result['flags']}")

# Test 3: Object Detection
print()
print("=" * 40)
print("TEST 3: Object Detection")
print("=" * 40)
obj_result = ai.objects.detect(frame)
print(f"Objects found: {len(obj_result['objects'])}")
for obj in obj_result['objects']:
    print(f"  {obj['class_name']}: {obj['confidence']:.2f}")
print(f"Person count: {obj_result['person_count']}")
print(f"Flags: {obj_result['flags']}")

# Test 4: Gaze Tracking
print()
print("=" * 40)
print("TEST 4: Gaze Tracking")
print("=" * 40)
gaze_result = ai.gaze.analyze(frame)
print(f"Gaze direction: {gaze_result['gaze_direction']}")
print(f"Looking at screen: {gaze_result['looking_at_screen']}")
print(f"Head pose: {gaze_result['head_pose']}")

# Test 5: Try with a phone in view (simulate)
print()
print("=" * 40)
print("SUMMARY")
print("=" * 40)
print(f"Face detection:   {'WORKING' if len(faces) > 0 else 'NO FACE FOUND'}")
print(f"Object detection: {'WORKING' if len(obj_result['objects']) > 0 else 'NO OBJECTS (might be ok)'}")
print(f"Gaze tracking:    {'WORKING' if gaze_result['gaze_direction'] != 'UNKNOWN' else 'NOT DETECTING'}")

# Save the frame so you can see what the camera captured
cv2.imwrite("test_frame.jpg", frame)
print(f"\nFrame saved as test_frame.jpg - open it to see what camera captured")