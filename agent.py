import asyncio
import logging
from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    stt,
)
from livekit.plugins import deepgram

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("backend-agent")


async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room: '{ctx.room.name}'...")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room: '{ctx.room.name}'")

    # Initialize Deepgram STT plugin inside entrypoint using job HTTP context
    stt_provider = deepgram.STT()

    async def process_audio_stt(track: rtc.Track, participant: rtc.RemoteParticipant):
        logger.info(f"Starting Deepgram STT stream for participant '{participant.identity}' (track: {track.sid})")
        audio_stream = rtc.AudioStream(track)
        stt_stream = stt_provider.stream()

        async def _forward_audio():
            try:
                async for event in audio_stream:
                    stt_stream.push_frame(event.frame)
            except Exception as err:
                logger.error(f"Error forwarding audio frames: {err}")
            finally:
                stt_stream.end_input()

        async def _read_transcripts():
            try:
                async for event in stt_stream:
                    if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                        if event.alternatives and event.alternatives[0].text:
                            transcript_text = event.alternatives[0].text.strip()
                            if transcript_text:
                                logger.info(f"[FINAL Transcript - {participant.identity}]: {transcript_text}")
                                print(f"[{participant.identity}]: {transcript_text}", flush=True)
                    elif event.type == stt.SpeechEventType.INTERIM_TRANSCRIPT:
                        if event.alternatives and event.alternatives[0].text:
                            transcript_text = event.alternatives[0].text.strip()
                            if transcript_text:
                                logger.debug(f"[INTERIM Transcript - {participant.identity}]: {transcript_text}")
            except Exception as err:
                logger.error(f"Error reading STT events: {err}")

        try:
            await asyncio.gather(_forward_audio(), _read_transcripts())
        finally:
            await stt_stream.aclose()
            await audio_stream.aclose()
            logger.info(f"STT stream closed for participant '{participant.identity}'")

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
            asyncio.create_task(process_audio_stt(track, participant))
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

    logger.info("BE-2 Agent initialized with Deepgram STT. Listening for audio and printing live transcripts.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
