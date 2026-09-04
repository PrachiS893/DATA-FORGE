# DataForge Backend Agent — BE-1 Scaffold

This repository contains the LiveKit Python Agent for DataForge voice assistant.

## BE-1 Features
- Scaffolded LiveKit agent process using `livekit-agents` worker architecture.
- Joins LiveKit room dynamically on job context creation.
- Subscribes to user audio tracks (`AutoSubscribe.AUDIO_ONLY`).
- Listens to participant connection and track subscription events with structured logging.

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
   Copy `.env.example` to `.env` and set your LiveKit credentials:
   ```bash
   LIVEKIT_URL=wss://<your-livekit-server-domain>.livekit.cloud
   LIVEKIT_API_KEY=<your_api_key>
   LIVEKIT_API_SECRET=<your_api_secret>
   ```

3. **Run Agent Worker**
   Run the agent in development mode:
   ```bash
   python agent.py dev
   ```
