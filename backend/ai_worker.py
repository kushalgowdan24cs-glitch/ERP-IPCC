import os
import asyncio
import logging
import cv2
import numpy as np
from redis.asyncio import Redis
import tritonclient.grpc.aio as grpcclient

# ─── CONFIGURATION ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AI_Worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TRITON_URL = os.getenv("TRITON_URL", "localhost:8001") # Triton gRPC port

STREAM_IN = "video_frames_queue"
STREAM_OUT = "raw_ai_detections"
GROUP_NAME = "ai_swarm"
WORKER_NAME = f"worker_{os.getpid()}"
BATCH_SIZE = 16  # Process 16 students simultaneously

redis_client = Redis.from_url(REDIS_URL)

async def setup_redis_group():
    """Creates the Consumer Group if it doesn't exist."""
    try:
        await redis_client.xgroup_create(STREAM_IN, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"Consumer group '{GROUP_NAME}' ready.")
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            logger.error(f"Redis Group Error: {e}")

def preprocess_yolo(jpg_bytes):
    """Decodes JPEG and formats it for YOLOv8 (1, 3, 640, 640)"""
    np_arr = np.frombuffer(jpg_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    img = cv2.resize(img, (640, 640))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Normalize and transpose to CHW
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))
    return img

async def process_batch():
    """Pulls a batch of frames, hits Triton, and pushes results."""
    try:
        triton_client = grpcclient.InferenceServerClient(url=TRITON_URL)
    except Exception as e:
        logger.error(f"Failed to connect to Triton: {e}")
        return

    while True:
        try:
            # 1. Pull up to BATCH_SIZE frames from Redis (Block for 1 second)
            # '>' means give me messages that haven't been assigned to any worker yet
            messages = await redis_client.xreadgroup(
                GROUP_NAME, WORKER_NAME, {STREAM_IN: '>'}, count=BATCH_SIZE, block=1000
            )

            if not messages:
                continue # No frames in queue, wait.

            stream_data = messages[0][1] # List of (message_id, data)
            
            batch_images = []
            metadata_list = []
            message_ids = []

            # 2. Prepare the Batch
            for msg_id, data in stream_data:
                try:
                    student_id = data[b'student_id'].decode('utf-8')
                    timestamp = data[b'timestamp'].decode('utf-8')
                    jpg_bytes = data[b'frame_data']
                    
                    img_tensor = preprocess_yolo(jpg_bytes)
                    batch_images.append(img_tensor)
                    metadata_list.append({"student_id": student_id, "timestamp": timestamp})
                    message_ids.append(msg_id)
                except Exception as e:
                    logger.error(f"Corrupt frame skipped: {e}")
                    await redis_client.xack(STREAM_IN, GROUP_NAME, msg_id)

            if not batch_images:
                continue

            # 3. Stack into a single massive Numpy array: Shape (N, 3, 640, 640)
            input_batch = np.stack(batch_images)
            
            # 4. Fire to NVIDIA Triton Inference Server via gRPC
            inputs = [grpcclient.InferInput("images", input_batch.shape, "FP32")]
            inputs[0].set_data_from_numpy(input_batch)
            
            # This takes ~10ms for 16 frames on a modern GPU. Unbeatable.
            results = await triton_client.infer(model_name="yolov8_detector", inputs=inputs)
            
            # Shape: (N, 84, 8400) - YOLOv8 standard output
            output_data = results.as_numpy("output0") 

            # 5. Push Raw Detections to the Output Stream & ACK
            pipe = redis_client.pipeline()
            for idx, meta in enumerate(metadata_list):
                # We would normally parse the bounding boxes here to find "cell phone" (Class 67).
                # For brevity, we pass the raw detection flag.
                
                # Check if "cell phone" confidence > 0.5 in this specific output matrix
                has_phone = bool(np.max(output_data[idx][67]) > 0.5) 

                result_payload = {
                    "student_id": meta["student_id"],
                    "timestamp": meta["timestamp"],
                    "yolo_phone_detected": str(has_phone)
                }
                
                # Push to the Logic Engine's queue
                pipe.xadd(STREAM_OUT, result_payload, maxlen=10000)
                # Acknowledge we processed this frame so Redis drops it
                pipe.xack(STREAM_IN, GROUP_NAME, message_ids[idx])
            
            await pipe.execute()
            logger.info(f"{WORKER_NAME} processed batch of {len(batch_images)} frames.")

        except Exception as e:
            logger.error(f"Batch Processing Error: {e}")
            await asyncio.sleep(1)

async def main():
    await setup_redis_group()
    logger.info(f"{WORKER_NAME} is online and waiting for frames...")
    await process_batch()

if __name__ == "__main__":
    asyncio.run(main())