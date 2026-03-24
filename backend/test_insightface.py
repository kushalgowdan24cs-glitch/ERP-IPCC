import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis

def test_installation():
    try:
        print("Importing modules and initializing...")
        
        # Initialize the FaceAnalysis app
        # 'buffalo_l' is the standard model pack for InsightFace
        app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        
        # ctx_id=-1 explicitly forces CPU usage
        app.prepare(ctx_id=-1, det_size=(640, 640))
        
        print("\n✅ Success! InsightFace and ONNX Runtime are installed and initialized correctly.")
        
    except Exception as e:
        print(f"\n❌ An error occurred during initialization:\n{e}")

if __name__ == "__main__":
    test_installation()