import urllib.request
import os

os.makedirs("ai_models", exist_ok=True)

proto_url = "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
model_url = "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"

print("Downloading deploy.prototxt...")
urllib.request.urlretrieve(proto_url, "ai_models/deploy.prototxt")
size1 = os.path.getsize("ai_models/deploy.prototxt")
print(f"  Downloaded: {size1} bytes")

print("Downloading face model (10MB)...")
urllib.request.urlretrieve(model_url, "ai_models/res10_300x300_ssd.caffemodel")
size2 = os.path.getsize("ai_models/res10_300x300_ssd.caffemodel")
print(f"  Downloaded: {size2} bytes")

if size1 < 1000:
    print("WARNING: prototxt file is too small, download may have failed!")
elif size2 < 5000000:
    print("WARNING: caffemodel file is too small, download may have failed!")
else:
    print("\nBoth files downloaded successfully!")

# Quick test
import cv2
try:
    net = cv2.dnn.readNetFromCaffe("ai_models/deploy.prototxt", "ai_models/res10_300x300_ssd.caffemodel")
    print("Model loaded into OpenCV successfully!")
except Exception as e:
    print(f"ERROR loading model: {e}")