"""
tool.py — the mock "backend" tool call the voice agent will use in Step 4.

This is deliberately built as a standalone module (no LiveKit / STT / LLM
dependencies) so you can unit-test the continuity logic — cancellation,
generation tagging, stale-result fencing — completely independently of the
voice pipeline. Wire this into your LiveKit agent in Step 4 unchanged.

Core ideas:
  - Every lookup is issued under a `generation_id` (an int that increments
    every time the user starts a fresh instruction / redirect / cancel).
  - Every lookup gets a `CancelToken`. If the generation moves on before the
    lookup finishes, the token gets cancelled and the lookup bails out early
    instead of returning a result nobody asked for anymore.
  - Every event (issued / completed / cancelled / not_found) is appended to
    a JSONL log file. That log is your evidence artifact for
    RIME_EVIDENCE.md and for the automated stress test in Step 5/6.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

ORDERS_PATH = Path(__file__).parent / "orders.json"
LOG_PATH = Path(__file__).parent / "logs" / "tool_calls.jsonl"

# How long the mock backend takes to "look something up".
# Override with an env var so you can dial this up/down for the stress test
# without touching code — the PS explicitly asks for a fixed, controllable delay.
TOOL_DELAY_MS = int(os.environ.get("TOOL_DELAY_MS", "3500"))

# How often (in ms) the lookup checks whether it's been cancelled while
# "working". Smaller = faster interrupt reaction, at the cost of more
# polling. 250ms is a reasonable default for a demo.
POLL_INTERVAL_MS = 250


def _load_orders() -> dict:
    with open(ORDERS_PATH, "r") as f:
        return json.load(f)


class CancelToken:
    """A simple cancellation flag shared between the caller and the lookup."""

    def __init__(self):
        self._event = Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class ToolCallLogger:
    """Appends structured JSONL events. This file is your evidence trail."""

    def __init__(self, log_path: Path = LOG_PATH):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, **event):
        event["ts"] = time.time()
        with open(self.log_path, "a") as f:
            f.write(json.dumps(event) + "\n")


@dataclass
class LookupResult:
    call_id: str
    generation_id: int
    order_id: str
    status: str  # "completed" | "cancelled" | "not_found"
    data: dict = field(default_factory=dict)


def lookup_order(
    order_id: str,
    generation_id: int,
    cancel_token: CancelToken,
    logger: ToolCallLogger,
    delay_ms: int = None,
) -> LookupResult:
    """
    Simulates a real backend order-status lookup.

    This function is BLOCKING and meant to be run in a background thread /
    asyncio task by the caller, so the voice pipeline can keep listening
    while this runs. It polls `cancel_token` throughout the artificial delay
    and bails out the moment it's cancelled — it does NOT wait for the full
    delay before checking.

    Returns a LookupResult tagged with the generation_id it was issued
    under. The CALLER is responsible for checking that generation_id still
    matches the current generation before speaking or applying the result —
    that fencing logic lives in the agent (Step 4), not here.
    """
    call_id = str(uuid.uuid4())[:8]
    delay_ms = TOOL_DELAY_MS if delay_ms is None else delay_ms

    logger.log(
        event="issued",
        call_id=call_id,
        generation_id=generation_id,
        order_id=order_id,
        delay_ms=delay_ms,
    )

    elapsed_ms = 0
    while elapsed_ms < delay_ms:
        if cancel_token.is_cancelled():
            logger.log(
                event="cancelled",
                call_id=call_id,
                generation_id=generation_id,
                order_id=order_id,
                elapsed_ms=elapsed_ms,
            )
            return LookupResult(
                call_id=call_id,
                generation_id=generation_id,
                order_id=order_id,
                status="cancelled",
            )
        time.sleep(POLL_INTERVAL_MS / 1000)
        elapsed_ms += POLL_INTERVAL_MS

    orders = _load_orders()
    record = orders.get(order_id)

    if record is None:
        logger.log(
            event="not_found",
            call_id=call_id,
            generation_id=generation_id,
            order_id=order_id,
        )
        return LookupResult(
            call_id=call_id,
            generation_id=generation_id,
            order_id=order_id,
            status="not_found",
        )

    logger.log(
        event="completed",
        call_id=call_id,
        generation_id=generation_id,
        order_id=order_id,
    )
    return LookupResult(
        call_id=call_id,
        generation_id=generation_id,
        order_id=order_id,
        status="completed",
        data=record,
    )
