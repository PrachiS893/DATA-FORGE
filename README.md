# DataForge Backend Agent

This repository contains the LiveKit Python Agent for DataForge voice assistant.

## Catalog Specifications & Features
- **BE-1 Scaffold**: LiveKit agent worker joining rooms and subscribing to audio tracks (`AutoSubscribe.AUDIO_ONLY`).
- **BE-2 STT Integration**: Streaming Deepgram STT plugin (`livekit-plugins-deepgram`).
- **BE-3 LLM + Tool Calling**: Groq LLM plugin (`livekit-plugins-groq`) with model `llama-3.3-70b-versatile` and function calling (`@llm.function_tool`) wrapping `lookup_order` from `tool.py`.
- **BE-4 Rime TTS Integration**: Official Rime TTS plugin (`livekit-plugins-rime`).
  - **Model**: `"mistv3"`
  - **Speaker**: `"peak"`
  - **Audio Format**: `"pcm"`
  - **Sample Rate**: `16000`
  - **Speed Alpha**: `1.0`
  - **Use WebSocket**: `True`
  - **Segment**: `"bySentence"`

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
   Ensure `.env` contains your LiveKit credentials, Deepgram API key, Groq API key, and Rime API key:
   ```bash
   LIVEKIT_URL=wss://<your-livekit-server-domain>.livekit.cloud
   LIVEKIT_API_KEY=<your_api_key>
   LIVEKIT_API_SECRET=<your_api_secret>
   DEEPGRAM_API_KEY=<your_deepgram_api_key>
   GROQ_API_KEY=<your_groq_api_key>
   RIME_API_KEY=<your_rime_api_key>
   ```

3. **Run Agent Worker**
   Run the agent in development mode:
   ```bash
   python agent.py dev
   ```
