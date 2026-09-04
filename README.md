# DataForge Backend Agent

This repository contains the LiveKit Python Agent for DataForge voice assistant.

## Features
- **BE-1 Scaffold**: LiveKit agent worker joining rooms and subscribing to audio tracks (`AutoSubscribe.AUDIO_ONLY`).
- **BE-2 STT Integration**: Streaming Deepgram STT plugin (`livekit-plugins-deepgram`).
- **BE-3 LLM + Tool Calling**: Google Gemini LLM (`livekit-plugins-google`) with function calling (`@llm.function_tool`).
  - Registers `lookup_order_tool` async wrapper around blocking `lookup_order` from `tool.py` via `asyncio.to_thread`.
  - Generates evidence logs in `logs/tool_calls.jsonl` via `ToolCallLogger`.

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
   Ensure `.env` contains your LiveKit credentials, Deepgram API key, and Google API key:
   ```bash
   LIVEKIT_URL=wss://<your-livekit-server-domain>.livekit.cloud
   LIVEKIT_API_KEY=<your_api_key>
   LIVEKIT_API_SECRET=<your_api_secret>
   DEEPGRAM_API_KEY=<your_deepgram_api_key>
   GOOGLE_API_KEY=<your_google_api_key>
   ```

3. **Run Agent Worker**
   Run the agent in development mode:
   ```bash
   python agent.py dev
   ```
