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
- **BE-6a Continuity Engine (Generation Counter & Stale Fencing)**:
  - Global `current_generation` counter incremented on every committed user instruction (`ev.is_final`).
  - Stale-result fencing compares `captured_gen` against `current_generation` after lookup returns. Discards stale results with log `[STALE DISCARDED]` and returns `{"stale": True, "order_id": order_id}`.
- **BE-6b Continuity Engine (Active Cancellation Wiring)**:
  - Maintained `active_cancel_tokens: dict[int, CancelToken]` mapping in `agent.py`.
  - When a new turn is committed (`ev.is_final` in `on_user_input_transcribed`), iterates over older generation tokens (`gen < current_generation`) and triggers `.cancel()`.
  - In-flight lookups in `tool.py` detect `cancel_token.is_cancelled()` within 250ms and return early with `status="cancelled"`.
- **BE-6c Continuity Engine (Intent Routing)**:
  - Maintained `call_tracker: dict[int, dict]` mapping order IDs and status per generation.
  - Added `check_pending_status` tool to answer status-of-status queries without triggering a new lookup.
  - Added `cancel_pending_lookup` tool to abort in-flight lookups when requested by the user and return a clean cancellation response.
  - Configured Agent instructions for clear routing across REDIRECT, STATUS-OF-STATUS, and CANCEL intents.

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
