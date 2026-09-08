import os
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from livekit import api
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


# Create FastAPI app
app = FastAPI()


print(
    "LIVEKIT_URL =",
    os.getenv("LIVEKIT_URL")
)


# ------------------------------------------------
# CORS
# ------------------------------------------------

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ------------------------------------------------
# LIVEKIT TOKEN
# ------------------------------------------------

@app.get("/api/token")
def get_token():

    # Create a unique room for every call
    room_name = (
        f"test-room-"
        f"{uuid.uuid4().hex[:8]}"
    )

    # Create LiveKit access token
    token = (
        api.AccessToken(
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET"),
        )
        .with_identity("test-user")
        .with_name("test-user")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
            )
        )
    )

    return {
        "token": token.to_jwt(),
        "url": os.getenv("LIVEKIT_URL"),
    }