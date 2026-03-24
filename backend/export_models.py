import os
import shutil
from pathlib import Path
from ultralytics import YOLO

def build_model_repository():
    print("🚀 Initializing Enterprise Model Export for Triton...")
    
    # Define paths based on your project structure
    base_repo = Path("../model_repository")
    yolo_dir = base_repo / "yolov8_detector"
    yolo_version_dir = yolo_dir / "1"
    
    # Clean and recreate directories
    if yolo_dir.exists():
        shutil.rmtree(yolo_dir)
    yolo_version_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export YOLOv8 to ONNX format
    print("📦 Downloading and exporting YOLOv8...")
    model = YOLO("yolov8n.pt")  # Use the nano version for ultra-fast CPU/GPU inference
    
    # Export to ONNX (dynamic axes allow Triton to batch multiple students at once)
    export_path = model.export(format="onnx", imgsz=640, dynamic=True, simplify=True)
    
    # Move the exported model to the strict Triton folder structure
    shutil.move(export_path, yolo_version_dir / "model.onnx")

    # 2. Write the Triton config.pbtxt file
    print("📝 Writing Triton Configuration...")
    config_content = """name: "yolov8_detector"
platform: "onnxruntime_onnx"
max_batch_size: 32

input [
  {
    name: "images"
    data_type: TYPE_FP32
    dims: [ 3, 640, 640 ]
  }
]
output [
  {
    name: "output0"
    data_type: TYPE_FP32
    dims: [ -1, -1 ]
  }
]

dynamic_batching {
  preferred_batch_size: [ 8, 16, 32 ]
  max_queue_delay_microseconds: 50000
}
"""
    with open(yolo_dir / "config.pbtxt", "w") as f:
        f.write(config_content)
        
    print("✅ Model Repository successfully built and formatted for Triton!")

if __name__ == "__main__":
    build_model_repository()