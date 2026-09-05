import asyncio
import logging
import json

from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    ErrorEvent,
    JobContext,
    UserInputTranscribedEvent,
    WorkerOptions,
    cli,
    llm,
    stt,
)
from livekit.plugins import deepgram, groq, rime
from tool import CancelToken, ToolCallLogger, lookup_order



load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("backend-agent")

import time

# Shared logger instance for backend tool calls
tool_logger = ToolCallLogger()

# Global generation counter, bumped on every committed user instruction
current_generation: int = 0

# Mapping from generation ID to its active CancelToken
active_cancel_tokens: dict[int, CancelToken] = {}

# Active call tracker storing status of pending lookups per generation
call_tracker: dict[int, dict] = {}

# Reference to active LiveKit Room instance for live data channel events
current_room: rtc.Room | None = None


def emit_continuity_event(event_type: str, **kwargs):
    """
    Emits a continuity event:
    1. Appends structured JSON event to logs/tool_calls.jsonl via tool_logger.
    2. Publishes JSON event payload over room data channel (topic: 'continuity-events') if room is active.
    """
    # Write to persistent JSONL log file
    tool_logger.log(event=event_type, **kwargs)

    # Publish to live LiveKit room data channel if room active
    if current_room and current_room.local_participant:
        payload = {
            "type": event_type,
            "ts": time.time(),
            **kwargs,
        }
        try:
            asyncio.create_task(
                current_room.local_participant.publish_data(
                    payload=json.dumps(payload).encode("utf-8"),
                    topic="continuity-events",
                    reliable=True,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to publish data channel event '{event_type}': {e}")


@llm.function_tool(
    description="Look up order details (status, ETA, items, total, shipping address) by numeric order ID (e.g. '1023', '4521')."
)
async def lookup_order_tool(order_id: str) -> dict:
    """Async wrapper around the blocking lookup_order function from tool.py."""
    global current_generation
    captured_gen = current_generation

    # Detect if this tool call represents a redirect from an in-flight lookup
    if any(g < captured_gen for g in active_cancel_tokens):
        logger.info(f"[REDIRECT DETECTED] Redirecting to new order_id='{order_id}' | new_gen={captured_gen}")
        emit_continuity_event("redirect_detected", order_id=order_id, new_generation=captured_gen)

    logger.info(f"[TOOL START] order_id='{order_id}' | gen={captured_gen}")
    emit_continuity_event("tool_call_start", order_id=order_id, generation=captured_gen)

    cancel_token = CancelToken()
    active_cancel_tokens[captured_gen] = cancel_token
    call_tracker[captured_gen] = {
        "order_id": order_id,
        "status": "pending",
        "cancel_token": cancel_token,
        "constraint": None,
    }

    # Proactive "still checking" status update background task
    async def _proactive_update_worker():
        try:
            await asyncio.sleep(3.0)
            if captured_gen == current_generation and not cancel_token.is_cancelled():
                logger.info(f"[PROACTIVE UPDATE] Still checking status for order_id='{order_id}' | gen={captured_gen}")
                emit_continuity_event("proactive_update", order_id=order_id, generation=captured_gen)
        except asyncio.CancelledError:
            logger.info(f"[PROACTIVE SUPPRESSED] Proactive update suppressed for order_id='{order_id}' | gen={captured_gen}")
            emit_continuity_event("proactive_suppressed", order_id=order_id, generation=captured_gen)

    proactive_task = asyncio.create_task(_proactive_update_worker())

    try:
        # Run blocking synchronous lookup_order in background thread to avoid freezing event loop
        result = await asyncio.to_thread(
            lookup_order,
            order_id=order_id,
            generation_id=captured_gen,
            cancel_token=cancel_token,
            logger=tool_logger,
        )
    finally:
        # Cancel proactive task once lookup returns or bails out
        if not proactive_task.done():
            proactive_task.cancel()
        # Clean up mapping entry once call completes or bails out
        active_cancel_tokens.pop(captured_gen, None)
        if captured_gen in call_tracker:
            call_tracker[captured_gen]["status"] = result.status if 'result' in locals() else "completed"

    # Stale-result fencing check: compare captured generation against current generation or check cancellation status
    if captured_gen != current_generation or result.status == "cancelled":
        logger.info(
            f"[STALE DISCARDED] order_id='{order_id}' | captured_gen={captured_gen} | current_gen={current_generation} | status={result.status}"
        )
        emit_continuity_event(
            "stale_discarded",
            order_id=order_id,
            captured_generation=captured_gen,
            current_generation=current_generation,
            status=result.status,
        )
        return {"stale": True, "order_id": order_id}

    logger.info(f"[TOOL COMPLETED] order_id='{order_id}' | gen={captured_gen} | status={result.status} | data={result.data}")
    emit_continuity_event("tool_call_completed", order_id=order_id, generation=captured_gen, status=result.status, data=result.data)

    response = {
        "status": result.status,
        "order_id": result.order_id,
        "data": result.data,
    }

    # Include recorded constraint if present for this generation
    recorded_constraint = call_tracker.get(captured_gen, {}).get("constraint")
    if recorded_constraint:
        logger.info(
            f"[CONSTRAINT RETURNED] Returning lookup result with constraint='{recorded_constraint}' for order_id='{order_id}' | gen={captured_gen}"
        )
        emit_continuity_event("constraint_returned", order_id=order_id, generation=captured_gen, constraint=recorded_constraint)
        response["constraint"] = recorded_constraint

    return response


@llm.function_tool(
    description="Check the progress or status of a currently pending order lookup (e.g. when the user asks 'is it done yet?', 'did you find it?', or 'how much longer?')."
)
async def check_pending_status() -> dict:
    """Check the status of the current pending order lookup without issuing a new search."""
    global current_generation
    entry = call_tracker.get(current_generation)
    if not entry or entry.get("status") in ("completed", "cancelled"):
        logger.info(f"[STATUS CHECK] No pending lookup in progress | gen={current_generation}")
        emit_continuity_event("status_check", generation=current_generation, pending=False)
        return {"pending": False, "message": "No order lookup is currently in progress."}

    order_id = entry.get("order_id", "unknown")
    logger.info(f"[STATUS CHECK] Pending lookup for order_id='{order_id}' in progress | gen={current_generation}")
    emit_continuity_event("status_check", order_id=order_id, generation=current_generation, pending=True)
    return {"pending": True, "order_id": order_id, "message": f"Order lookup for {order_id} is still in progress."}


@llm.function_tool(
    description="Cancel or abort the currently in-flight order lookup when the user says 'cancel', 'never mind', 'stop', or 'forget it'."
)
async def cancel_pending_lookup() -> dict:
    """Cancel the currently pending order lookup."""
    global current_generation
    entry = call_tracker.get(current_generation)
    captured_token = active_cancel_tokens.pop(current_generation, None)

    order_id = entry.get("order_id", "unknown") if entry else "unknown"

    if captured_token and not captured_token.is_cancelled():
        captured_token.cancel()

    if entry:
        entry["status"] = "cancelled"

    logger.info(f"[CANCEL TOOL] Cancelled pending lookup for order_id='{order_id}' | gen={current_generation}")
    emit_continuity_event("cancel_tool", order_id=order_id, generation=current_generation, cancelled=True)

    return {"cancelled": True, "order_id": order_id, "message": f"Lookup for order {order_id} has been cancelled."}


@llm.function_tool(
    description="Add a constraint or filter to the currently pending order lookup (e.g. when the user asks to narrow the request for the SAME order, such as 'just tell me the delivery date', 'only check if it shipped', or 'just the items'). Do NOT use for a different order ID, checking status, or cancelling."
)
async def add_lookup_constraint(constraint: str) -> dict:
    """Record a constraint or field filter for the currently pending order lookup."""
    global current_generation
    entry = call_tracker.get(current_generation)
    if not entry or entry.get("status") != "pending":
        for gen, tracker_entry in sorted(call_tracker.items(), reverse=True):
            if tracker_entry.get("status") == "pending":
                entry = tracker_entry
                break

    if not entry or entry.get("status") != "pending":
        logger.info(f"[CONSTRAINT ADDED] No pending lookup in progress to constrain | gen={current_generation}")
        emit_continuity_event("constraint_added", generation=current_generation, constraint_recorded=False)
        return {"constraint_recorded": False, "message": "No active order lookup is currently in progress."}

    entry["constraint"] = constraint
    order_id = entry.get("order_id", "unknown")
    logger.info(f"[CONSTRAINT ADDED] Recorded constraint='{constraint}' for order_id='{order_id}' | gen={current_generation}")
    emit_continuity_event("constraint_added", order_id=order_id, generation=current_generation, constraint=constraint)
    return {"constraint_recorded": True, "constraint": constraint, "order_id": order_id}





async def entrypoint(ctx: JobContext):
    global current_room
    current_room = ctx.room
    logger.info(f"Connecting to room: '{ctx.room.name}'...")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room: '{ctx.room.name}'")

    # Room participant and track event handlers
    @ctx.room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logger.info(f"Participant connected: {participant.identity} (SID: {participant.sid})")

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(f"Participant disconnected: {participant.identity} (SID: {participant.sid})")

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(
                f"Subscribed to audio track '{track.sid}' from participant '{participant.identity}'"
            )
        else:
            logger.info(
                f"Subscribed to track '{track.sid}' ({track.kind}) from participant '{participant.identity}'"
            )

    @ctx.room.on("track_unsubscribed")
    def on_track_unsubscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        logger.info(
            f"Unsubscribed from track '{track.sid}' from participant '{participant.identity}'"
        )

    # Initialize Agent with Deepgram STT, Groq LLM (openai/gpt-oss-120b), Rime TTS, and intent routing tools
    agent = Agent(
        instructions=(
            "You are an order tracking assistant for DataForge. "
            "When a user asks about an order or provides an order ID, call the tool lookup_order_tool with the order ID. "
            "Provide concise order status information based on the tool result. "
            "If a tool result contains \"stale\": true, do not read it aloud or mention it — remain silent about that specific result and wait for further input. "
            "When an order lookup is pending: "
            "(a) If the user asks about a DIFFERENT order ID, call lookup_order_tool with the new order ID as normal. "
            "(b) If the user asks whether the current lookup is done or how long it will take, call check_pending_status instead of calling lookup_order_tool again. "
            "(c) If the user indicates they want to cancel, stop, or say 'never mind', call cancel_pending_lookup instead of calling lookup_order_tool. "
            "(d) If the user asks to narrow, filter, or refine what specific details they want to hear about the CURRENT order being looked up (e.g. 'just the delivery date', 'only tell me if it shipped', 'just the total'), call add_lookup_constraint with a short description of what they want, and continue waiting — do not call lookup_order_tool again. "
            "Once a tool result includes a 'constraint' field, answer using ONLY the information relevant to that constraint, not the full order details."
        ),
        stt=deepgram.STT(),
        llm=llm.FallbackAdapter(
            [
                groq.LLM(model="openai/gpt-oss-120b"),
                groq.LLM(model="openai/gpt-oss-20b"),   # see note below
            ],
            attempt_timeout=10.0,
            max_retry_per_llm=1,
            retry_interval=2,
        ),
        tts=rime.TTS(
            model="mistv3",
            speaker="peak",
            sample_rate=16000,
            speed_alpha=1.0,
            use_websocket=True,
            segment="bySentence",
        ),
        tools=[lookup_order_tool, check_pending_status, cancel_pending_lookup, add_lookup_constraint],
    )



    from livekit.agents import TurnHandlingOptions

    session = AgentSession(
        turn_handling=TurnHandlingOptions(
            turn_detection="stt",
            endpointing={
               "mode": "fixed",
                "min_delay": 1.0,   # up from the 0.5s default — cuts down on transcript-arrives-late double commits
                "max_delay": 3.0,
            },
        ),
    )


    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev: UserInputTranscribedEvent):
        global current_generation
        if ev.is_final and ev.transcript:
            current_generation += 1
            speaker = ev.speaker_id or "user"

            # Actively cancel any in-flight lookups from older generations
            stale_gens = [g for g in active_cancel_tokens if g < current_generation]
            for gen in stale_gens:
                token = active_cancel_tokens.pop(gen, None)
                if token and not token.is_cancelled():
                    logger.info(f"[CANCELLED IN-FLIGHT] Cancelling in-flight lookup for gen={gen} | current_gen={current_generation}")
                    emit_continuity_event("cancelled_in_flight", generation=gen, current_generation=current_generation)
                    token.cancel()

            logger.info(f"[FINAL Transcript - {speaker}] (gen={current_generation}): {ev.transcript}")
            print(f"[{speaker}]: {ev.transcript}", flush=True)
            # Cap history to avoid unbounded token growth across the session
            agent.update_chat_ctx(agent.chat_ctx.truncate(max_items=20))

    @session.on("error")
    def on_session_error(ev: ErrorEvent):
        logger.error(f"[SESSION ERROR] recoverable={ev.recoverable} | {ev.error}")
        emit_continuity_event("session_error", recoverable=ev.recoverable, error=str(ev.error))

        if not ev.recoverable:
            # Both FallbackAdapter LLMs (and retries) have been exhausted — speak
            # a graceful message instead of letting the session close silently.
            asyncio.create_task(
                session.say("Sorry, I'm having trouble right now — could you try again in a moment?")
            )



    logger.info("Agent initialized with Deepgram STT + Groq LLM (openai/gpt-oss-120b) + Rime TTS + lookup_order_tool. Starting session...")

    await session.start(agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
