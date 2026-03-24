import cv2
import time
from ai_engine import ai

print("Loading AI models...")
ai.load_all()
print("Models loaded!\n")

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Cannot open webcam!")
    exit()

print("Warming up camera (3 seconds)...")
time.sleep(2)

# Grab several frames to flush the buffer
for i in range(10):
    cap.read()
    time.sleep(0.1)

print("Capturing real frame now...")
ret, frame = cap.read()
cap.release()

if not ret or frame is None:
    print("ERROR: Failed to capture frame!")
    exit()

print(f"Frame size: {frame.shape}")
cv2.imwrite("test_frame2.jpg", frame)
print("Frame saved as test_frame2.jpg\n")

# Check brightness
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
brightness = gray.mean()
print(f"Frame brightness: {brightness:.1f} (should be > 50)")

if brightness < 30:
    print("WARNING: Frame is very dark! Turn on lights or check camera.")
else:
    print("Brightness OK\n")

# Face Detection
print("=" * 40)
print("FACE DETECTION")
faces = ai.face.detect_faces(frame)
print(f"Faces found: {len(faces)}")
for f in faces:
    print(f"  confidence={f['confidence']:.2f} bbox={f['bbox']}")

# Object Detection
print()
print("=" * 40)
print("OBJECT DETECTION")
obj = ai.objects.detect(frame)
print(f"Objects: {len(obj['objects'])}")
for o in obj['objects']:
    print(f"  {o['class_name']}: {o['confidence']:.2f}")
print(f"Flags: {obj['flags']}")

# Gaze
print()
print("=" * 40)
print("GAZE TRACKING")
gaze = ai.gaze.analyze(frame)
print(f"Direction: {gaze['gaze_direction']}")
print(f"Looking at screen: {gaze['looking_at_screen']}")

print()
print("=" * 40)
print("DONE - Open test_frame2.jpg to verify your face is visible")