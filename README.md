# DataForge Backend Agent

This repository contains the LiveKit Python Agent for DataForge voice assistant.

## Features
- **BE-1 Scaffold**: LiveKit agent worker joining rooms and subscribing to audio tracks (`AutoSubscribe.AUDIO_ONLY`).
- **BE-2 STT Integration**: Streaming Deepgram STT plugin (`livekit-plugins-deepgram`). Receives raw audio frames from participant tracks and prints live final transcripts formatted as `[<participant_identity>]: <text>`.

## Setup Instructions

1. **Environment Setup**
   ```bash
   # Create virtual environment
   python -m venv .venv

   # Activate virtual environment (Windows PowerShell)
   .\.venv\Scripts\Activate.ps1

   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   Ensure `.env` contains your LiveKit credentials and Deepgram API key:
   ```bash
   LIVEKIT_URL=wss://<your-livekit-server-domain>.livekit.cloud
   LIVEKIT_API_KEY=<your_api_key>
   LIVEKIT_API_SECRET=<your_api_secret>
   DEEPGRAM_API_KEY=<your_deepgram_api_key>
   ```

3. **Run Agent Worker**
   Run the agent in development mode:
   ```bash
   python agent.py dev
   ```
