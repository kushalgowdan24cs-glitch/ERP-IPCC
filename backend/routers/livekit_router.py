from fastapi import APIRouter, HTTPException
import jwt
import time
import os
from dotenv import load_dotenv

# Load the real cloud keys from backend/.env
load_dotenv()

router = APIRouter()


@router.get("/api/v1/livekit/token")
async def get_livekit_token(identity: str, room: str):
    try:
        room_name = room
        api_key = os.environ.get("LIVEKIT_API_KEY")
        api_secret = os.environ.get("LIVEKIT_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError("LiveKit Cloud credentials missing from .env")

        # Forge the exact payload LiveKit expects manually
        payload = {
            "iss": api_key,                   # Issuer (API Key)
            "sub": identity,                  # Subject (User Identity)
            "name": identity,                 # Display Name
            "exp": int(time.time()) + 7200,   # Token expires in 2 hours
            "video": {
                "room": room_name,
                "roomJoin": True,
                "canPublish": True,
                "canPublishData": True,
                "canSubscribe": False         # Students cannot watch other students
            }
        }

        # Sign it cryptographically with your real Cloud Secret
        token = jwt.encode(payload, api_secret, algorithm="HS256")

        return {"token": token, "room": room_name}
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))