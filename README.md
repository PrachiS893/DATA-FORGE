# DataForge Backend Agent

This repository contains the LiveKit Python Agent for the DataForge voice assistant.

## Architecture

```
User Voice Input
       │
       ▼
Deepgram STT (livekit-plugins-deepgram)
       │
       ▼
Groq LLM FallbackAdapter (livekit-plugins-groq)
   ├── Primary:  openai/gpt-oss-120b
   └── Fallback: openai/gpt-oss-20b
       │
       ├───────────────────────────────────────────────────┐
       ▼                                                   ▼
Tool Calling Pipeline                              Continuity Engine
   ├── lookup_order_tool                            ├── Generation Counter (current_generation)
   ├── check_pending_status                         ├── Active Cancel Tokens (active_cancel_tokens)
   ├── cancel_pending_lookup                        └── Call Tracker (call_tracker)
   └── add_lookup_constraint                               │
       │                                                   ▼
       │                                           emit_continuity_event()
       │                                              ├── JSONL File (logs/tool_calls.jsonl)
       │                                              └── Room Data Channel ("continuity-events")
       ▼
Rime TTS (livekit-plugins-rime)
       │
       ▼
User Voice Output
```

The agent processes real-time audio streams via LiveKit WebRTC transport. Deepgram streams user speech transcripts into Groq LLM via `llm.FallbackAdapter`. The LLM invokes registered function tools against the backend order system (`tool.py`). 

The **Continuity Engine** sits directly within the event loop and tool execution pipeline:
- Increments `current_generation` on every committed user utterance (`ev.is_final`).
- Manages `active_cancel_tokens` to actively abort in-flight lookups when a user interrupts or redirects.
- Tracks pending lookup states in `call_tracker`.
- Routes all pipeline events through `emit_continuity_event()`, which simultaneously appends structured JSON lines to `logs/tool_calls.jsonl` and broadcasts reliable data channel payloads over the LiveKit room (`topic="continuity-events"`).

---

## Third-Party Services

- **Deepgram**: Real-time streaming Speech-to-Text (`livekit-plugins-deepgram`) for transcribing incoming user audio streams.
- **Groq**: High-speed LLM inference (`livekit-plugins-groq`) using `openai/gpt-oss-120b` (primary) and `openai/gpt-oss-20b` (fallback) via `llm.FallbackAdapter` for intent recognition, tool invocation, and spoken response synthesis.
- **Rime**: Neural Text-to-Speech synthesis (`livekit-plugins-rime`) with model `"mistv3"` and speaker `"peak"` over WebSocket for low-latency streaming voice output.
- **LiveKit**: Realtime WebRTC infrastructure, room orchestration, audio track transport, and room data channel pub/sub messaging (`livekit-agents`).

---

## Rime Configuration

The following table reflects the exact parameters configured in `agent.py`:

| Parameter | Current Value in `agent.py` | Source / Status |
|---|---|---|
| **Model** | `"mistv3"` | Explicitly set in `agent.py` |
| **Speaker** | `"peak"` | Explicitly set in `agent.py` |
| **Language** | `"en"` (English) | Plugin default (not explicitly passed in `agent.py`) |
| **Endpoint** | `https://users.rime.ai/v1/rime-tts` | Plugin default (no explicit override set in `agent.py`) |
| **Audio Format** | `"pcm"` | Plugin default (no explicit parameter passed in `agent.py`) |
| **Sample Rate** | `16000` | Explicitly set in `agent.py` |
| **Transport (`use_websocket`)** | `True` | Explicitly set in `agent.py` |
| **Segment** | `"bySentence"` | Explicitly set in `agent.py` |
| **Speed Alpha** | `1.0` | Explicitly set in `agent.py` |

---

## Catalog Specifications & Features

- **BE-1 Scaffold**: LiveKit agent worker joining rooms and subscribing to audio tracks (`AutoSubscribe.AUDIO_ONLY`).
- **BE-2 STT Integration**: Streaming Deepgram STT plugin (`livekit-plugins-deepgram`).
- **BE-3 LLM + Tool Calling**: Groq LLM plugin (`livekit-plugins-groq`) wrapped in `llm.FallbackAdapter` with `openai/gpt-oss-120b` (primary) and `openai/gpt-oss-20b` (fallback), with `attempt_timeout=10.0`, `max_retry_per_llm=1`, and `retry_interval=2`. Function calling (`@llm.function_tool`) wraps backend lookups from `tool.py`. *(Note: `llama-3.3-70b-versatile` was deprecated by Groq and is no longer used).*
- **BE-4 Rime TTS Integration**: Official Rime TTS plugin (`livekit-plugins-rime`) with `model="mistv3"`, `speaker="peak"`, `sample_rate=16000`, `speed_alpha=1.0`, `use_websocket=True`, and `segment="bySentence"`.
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
- **BE-6d Continuity Engine (Proactive Status Update)**:
  - Added background task `_proactive_update_worker()` in `lookup_order_tool`. Emits `[PROACTIVE UPDATE]` / `proactive_update` event when lookup execution exceeds 3 seconds.
  - Emits `[PROACTIVE SUPPRESSED]` / `proactive_suppressed` when lookup finishes early or is cancelled before the timer fires.
- **BE-6e Continuity Engine (Constraint Refinement)**:
  - Added `add_lookup_constraint` tool allowing users to narrow or filter requested fields for the CURRENT pending order lookup (e.g. "just the delivery date") without cancelling or restarting the lookup or bumping generation.
  - Attaches `"constraint"` field to the returned tool result dictionary so the LLM tailors its spoken reply to only the requested fields.
- **BE-6f Continuity Engine (Unified In-Process Event Logging)**:
  - Standardized event logging format (`[TAG NAME] order_id='...' | gen=...`) across all 11 continuity event types.
- **BE-7 Evidence Logging & Live Data Channel Events**:
  - `emit_continuity_event()` records every continuity event to `logs/tool_calls.jsonl` as structured JSON lines and publishes live JSON payloads to the LiveKit room data channel under topic `"continuity-events"` with `reliable=True`.

---

## Frontend Token Generation (`generate_token.py`)

A utility script `generate_token.py` is included for generating LiveKit WebRTC access tokens for testing and frontend development.
- **Interface**: Standalone CLI script (executed via `python generate_token.py`), not an HTTP service.
- **Behavior**: Reads `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `LIVEKIT_URL` from `.env`, creates a LiveKit `AccessToken` with identity `"test-user"` and room grant `room_join=True` for room `"test-room"`, and prints formatted JSON with `token` (JWT) and `url` to stdout.

---

## Known Issues & Fixed Bugs

1. **`on_session_error` Fallback Handling Bug (Fixed)**:
   - *Issue*: `session.say()` was previously wrapped in `asyncio.create_task()`, which caused runtime errors because `session.say()` in LiveKit Agents Python SDK is a synchronous method that returns a handle, not a coroutine.
   - *Fix*: Called `session.say(...)` directly inside `on_session_error` handler when `recoverable` is `False`.

2. **Rime TTS Transport Investigation (Verified)**:
   - *Investigation*: `use_websocket` mode was analyzed during debugging for streaming latency and stability.
   - *Current Shipped Code*: `use_websocket=True` is explicitly set and active in `agent.py`.

---

## Known Limitations

- **Dual-Model Fallback Stress Testing**: `llm.FallbackAdapter` dual-model behavior (`gpt-oss-120b` -> `gpt-oss-20b`) has not been stress-tested under forced artificial LLM timeouts for duplicate tool invocation side effects.
- **Upstream Audio Playback Failure on Rapid Interruptions**: Documented upstream LiveKit Agents issue where, after multiple rapid interruptions in a single session, synthesized TTS audio can occasionally fail to play on the client even though `conversation_item_added` fires.
- **BE-8 Automated Acceptance Test**: BE-8 automated acceptance testing framework is not marked as completed in core specification; current coverage relies on manual testing and scripted verification (`check_stress_test.py`).

---

## Failure Behavior

| Trigger / Failure Case | Actual System Behavior |
|---|---|
| **STT / LLM / TTS Critical Error** | `@session.on("error")` catches `ErrorEvent`. If `recoverable` is `False` (e.g. both LLMs in `FallbackAdapter` fail), agent logs `[SESSION ERROR]`, emits `session_error` event, and speaks `"Sorry, I'm having trouble right now — could you try again in a moment?"` via `session.say(...)`. |
| **Primary LLM Rate-Limit / Timeout** | `llm.FallbackAdapter` catches primary timeout (`attempt_timeout=10.0`) or rate limit errors on `openai/gpt-oss-120b`, waits `retry_interval=2`, and automatically falls back to `openai/gpt-oss-20b`. |
| **Lookup Cancelled Mid-Flight** | `lookup_order` in `tool.py` polls `cancel_token.is_cancelled()` every 250ms, bails out early, and returns `status="cancelled"`. `lookup_order_tool` in `agent.py` detects stale generation or cancelled status, logs `[STALE DISCARDED]`, emits `stale_discarded` event, and returns `{"stale": True, "order_id": order_id}` without speaking stale data. |
| **Non-Existent Order ID** | `lookup_order` in `tool.py` returns `status="not_found"`. `lookup_order_tool` passes `{"status": "not_found", "data": {}}` to LLM, which informs the user that no matching order was found. |

---

## Setup & Execution

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
   Ensure `.env` contains your credentials:
   ```bash
   LIVEKIT_URL=wss://<your-livekit-server-domain>.livekit.cloud
   LIVEKIT_API_KEY=<your_api_key>
   LIVEKIT_API_SECRET=<your_api_secret>
   DEEPGRAM_API_KEY=<your_deepgram_api_key>
   GROQ_API_KEY=<your_groq_api_key>
   RIME_API_KEY=<your_rime_api_key>
   ```

3. **Run Agent Worker**
   ```bash
   python agent.py dev
   ```
