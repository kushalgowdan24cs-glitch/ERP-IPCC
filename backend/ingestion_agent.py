import os
import asyncio
import logging
import time
import cv2
import numpy as np
from redis.asyncio import Redis

from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, WorkerType

# ─── CONFIGURATION ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IngestionAgent")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
# We use a Redis Stream named 'video_frames_queue'
STREAM_NAME = "video_frames_queue" 

# Initialize Redis connection
redis_client = Redis.from_url(REDIS_URL)

async def process_video_track(track: rtc.RemoteVideoTrack, participant: rtc.RemoteParticipant, room: rtc.Room):
    """
    Subscribes to a specific student's video track, extracts 1 frame per second,
    compresses it, and pushes it to Redis Streams for the AI Swarm.
    """
    video_stream = rtc.VideoStream(track)
    student_id = participant.identity
    room_name = room.name
    
    logger.info(f"Started frame extraction for Student: {student_id} in Room: {room_name}")
    
    # We only want 1 Frame Per Second.
    # LiveKit sends 30 FPS. We will throttle this loop.
    last_processed_time = 0.0
    
    async for event in video_stream:
        current_time = time.time()
        
        # Throttle to 1 FPS to save GPU costs
        if current_time - last_processed_time < 1.0:
            continue
            
        last_processed_time = current_time
        
        # 1. Convert LiveKit VideoFrame to standard Numpy Array (OpenCV format)
        # The frame comes in as ARGB, we convert to BGR for AI models
        frame = event.frame
        argb_array = np.frombuffer(frame.data, dtype=np.uint8).reshape((frame.height, frame.width, 4))
        bgr_array = cv2.cvtColor(argb_array, cv2.COLOR_RGBA2BGR)
        
        # 2. Compress to JPEG to save RAM in Redis
        _, buffer = cv2.imencode('.jpg', bgr_array, [cv2.IMWRITE_JPEG_QUALITY, 80])
        jpg_bytes = buffer.tobytes()
        
        # 3. Push to Redis Streams
        # The AI Workers will be listening to this exact stream
        payload = {
            "student_id": student_id,
            "room_name": room_name,
            "timestamp": str(current_time),
            "track_source": str(track.source), # 'camera' or 'screen_share'
            "frame_data": jpg_bytes
        }
        
        try:
            # MAXLEN=10000 ensures we don't blow up Redis memory if AI workers fall behind
            await redis_client.xadd(STREAM_NAME, payload, maxlen=10000)
        except Exception as e:
            logger.error(f"Failed to push frame to Redis for {student_id}: {e}")

async def entrypoint(ctx: JobContext):
    """
    The entrypoint for the LiveKit Agent. It automatically connects to rooms
    and triggers when a student turns on their camera.
    """
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.VIDEO_ONLY)

    # Listen for new video tracks (when a student's camera connects)
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_VIDEO:
            # Spawn a background task to process this specific camera
            asyncio.create_task(process_video_track(track, participant, ctx.room))

if __name__ == "__main__":
    # Start the LiveKit Agent Worker
    # This automatically talks to your LiveKit server and listens for jobs
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        worker_type=WorkerType.ROOM, # 1 Agent Instance manages multiple rooms
    ))