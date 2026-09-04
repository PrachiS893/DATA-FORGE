import asyncio
import logging
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    UserInputTranscribedEvent,
    WorkerOptions,
    cli,
    llm,
    stt,
)
from livekit.plugins import deepgram, google
from tool import CancelToken, ToolCallLogger, lookup_order

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("backend-agent")

# Shared logger instance for backend tool calls
tool_logger = ToolCallLogger()


@llm.function_tool(
    description="Look up order details (status, ETA, items, total, shipping address) by numeric order ID (e.g. '1023', '4521')."
)
async def lookup_order_tool(order_id: str) -> dict:
    """Async wrapper around the blocking lookup_order function from tool.py."""
    logger.info(f"[TOOL CALL] Triggered lookup_order_tool for order_id: '{order_id}'")
    cancel_token = CancelToken()
    generation_id = 0

    # Run blocking synchronous lookup_order in background thread to avoid freezing event loop
    result = await asyncio.to_thread(
        lookup_order,
        order_id=order_id,
        generation_id=generation_id,
        cancel_token=cancel_token,
        logger=tool_logger,
    )

    logger.info(f"[TOOL RESULT] order_id={order_id} | status={result.status} | data={result.data}")
    print(f"[TOOL RESULT] order_id={order_id} | status={result.status} | data={result.data}", flush=True)

    return {
        "status": result.status,
        "order_id": result.order_id,
        "data": result.data,
    }


async def entrypoint(ctx: JobContext):
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

    # Initialize Agent with Deepgram STT, Google Gemini LLM, and lookup_order_tool
    agent = Agent(
        instructions=(
            "You are an order tracking assistant for DataForge. "
            "When a user asks about an order or provides an order ID, call the tool lookup_order_tool with the order ID. "
            "Provide concise order status information based on the tool result."
        ),
        stt=deepgram.STT(),
        llm=google.LLM(model="gemini-3.6-flash"),
        tools=[lookup_order_tool],
    )

    session = AgentSession()

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev: UserInputTranscribedEvent):
        if ev.is_final and ev.transcript:
            speaker = ev.speaker_id or "user"
            logger.info(f"[FINAL Transcript - {speaker}]: {ev.transcript}")
            print(f"[{speaker}]: {ev.transcript}", flush=True)

    logger.info("BE-3 Agent initialized with Deepgram STT + Gemini LLM + lookup_order_tool. Starting session...")
    await session.start(agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
