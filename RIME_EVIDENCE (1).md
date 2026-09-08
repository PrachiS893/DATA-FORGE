# RIME_EVIDENCE.md

## Hard Voice Problem
**Category:** Conversation continuity during tool work

**Claim:**
While DataForge's support agent is executing a backend tool call (order
lookup), the voice session stays responsive: the user can redirect to a
different order, add a constraint, ask for a status check, or cancel
outright — mid-lookup — without the agent ever speaking a stale/superseded
tool result, and without losing track of the user's latest intent.

---

## Acceptance Test

Defined before the demo. A run **passes** if, across all 10 scenarios in
`check_stress_test.py`:

1. Every in-flight lookup that is redirected (S2, S6, S7) is cancelled and
   its result is discarded (`cancelled_in_flight` + `stale_discarded`
   events fire) — the agent only ever speaks the result for the
   **latest** requested order.
2. Every explicit cancellation (S4, S8) results in the stale result being
   discarded (`cancel_tool` + `stale_discarded`) and nothing further is
   spoken about that lookup.
3. A status check during a pending lookup (S3) returns `pending=True`
   without starting a duplicate lookup.
4. A lookup exceeding **3.0s** (the proactive update threshold) emits a
   `proactive_update` event (S1), and this update is correctly suppressed
   if the lookup is cancelled before it fires (S8:
   `proactive_suppressed`).
5. Added constraints (S5, S7) are preserved and reflected in the final
   result (`constraint_added` → `constraint_returned`), never dropped.
6. Non-existent orders (S9) resolve cleanly to `status="not_found"` rather
   than hanging or crashing the continuity state machine.

**Threshold:** 0 violations across all 10 scenarios (10/10 pass), 0
instances of a stale/superseded result being spoken as current.

---

## Rime Integration Configuration

Verified directly from source (`agent.py`) and plugin defaults:

| Property | Value | Source |
|---|---|---|
| Model ID | `mistv3` | `agent.py` L305 |
| Speaker | `peak` | `agent.py` L306 |
| Language | `en` | `livekit-plugins-rime` default |
| Endpoint | `https://users.rime.ai/v1/rime-tts` | `livekit-plugins-rime` default |
| Audio format | `pcm` | Default Rime TTS streaming format |
| Transport | WebSocket (`use_websocket=True`) | `agent.py` L309 |
| Sample rate | 16000 Hz | `agent.py` L307 |
| Segmentation | `bySentence` | `agent.py` L310 |
| Speed alpha | 1.0 | `agent.py` L308 |

---

## Continuity Engine Constants

Verified directly from source (`tool.py`, `agent.py`):

| Parameter | Value | Source | Role |
|---|---|---|---|
| Mock tool delay | 3.5s | `tool.py` L34 | Simulated backend order-lookup latency, used to create a reliable interruption window |
| Cancellation poll interval | 0.25s | `tool.py` L39 | How often `lookup_order` checks `cancel_token.is_cancelled()` |
| Proactive update delay | 3.0s | `agent.py` L107 | Threshold before agent tells user it's still checking |
| Endpointing min delay | 1.0s | `agent.py` L324 | Min delay before committing a user turn |
| Endpointing max delay | 3.0s | `agent.py` L325 | Max delay before committing a user turn |
| LLM attempt timeout | 10.0s | `agent.py` L300 | Per-model timeout in `llm.FallbackAdapter` |
| LLM retry interval | 2.0s | `agent.py` L302 | Delay between fallback attempts |
| Max retries per LLM | 1 | `agent.py` L301 | Retry cap per model |
| Chat context truncation | 20 items | `agent.py` L351 | History limit enforced on transcription |

---

## Procedure

**Test harness:** `check_stress_test.py` (project root), fully automated,
runs all 10 scenarios sequentially in a single execution.

**Scenarios (N=10, one trial each per run):**

| ID | Scenario | Verification criteria |
|---|---|---|
| S0 | Baseline uninterrupted lookup | Completes with no stale fencing or cancellation |
| S1 | Proactive "still checking" update | `proactive_update` fires after 3s, lookup then completes normally |
| S2 | Redirect (Order A → B) | `cancelled_in_flight`, `redirect_detected`, `stale_discarded` for A; `tool_call_completed` for B |
| S3 | Status check during pending lookup | `status_check` (`pending=True`), no duplicate lookup started |
| S4 | Explicit cancel during pending lookup | `cancel_tool` (`cancelled=True`), tool bails, stale result discarded |
| S5 | Constraint refinement | `constraint_added` → lookup completes → `constraint_returned` |
| S6 | Rapid double redirect (A → B → C) | 2× `cancelled_in_flight`, 2× `redirect_detected`, 2× `stale_discarded`, 1× final `tool_call_completed` |
| S7 | Constraint then redirect (A+C → B) | `constraint_added`, `cancelled_in_flight`, `redirect_detected`, `stale_discarded` for A, `tool_call_completed` for B |
| S8 | Cancel during proactive window | `proactive_update`, `cancel_tool`, `stale_discarded`, `proactive_suppressed` |
| S9 | Non-existent order lookup | `not_found` event, `tool_call_completed` with `status="not_found"` |

**Instrumentation:** All continuity events are logged as structured JSONL
to `logs/tool_calls.jsonl` and simultaneously broadcast over the LiveKit
room data channel on topic `"continuity-events"` (`reliable=True`), so
both offline log inspection and live session inspection are possible.

---

## Result

Actual output from running `python check_stress_test.py`:

| ID | Scenario | Result | Details |
|---|---|---|---|
| S0 | Baseline Uninterrupted Lookup | PASS | Lookup completed cleanly without stale fencing |
| S1 | Proactive Update | PASS | `proactive_update=True`, `completed=True` |
| S2 | Redirect (1023 → 4521) | PASS | `redirect=True`, `stale_discarded=True`, `final_completed=True` |
| S3 | Status Check | PASS | `status_check=True`, `completed=True` |
| S4 | Explicit Cancel | PASS | `cancel_tool=True`, `stale/cancelled=True` |
| S5 | Constraint Refinement | PASS | `constraint_added=True`, `constraint_returned=True` |
| S6 | Rapid Double Redirect | PASS | `cancelled_in_flight_count=2`, `stale_discard_count=2`, `final_completed=True` |
| S7 | Constraint then Redirect | PASS | `constraint=True`, `redirect=True`, `stale=True`, `completed=True` |
| S8 | Cancel during Proactive Window | PASS | `proactive=True`, `cancel_tool=True`, `stale/cancelled=True` |
| S9 | Non-existent Order Lookup | PASS | `not_found=True`, `tool_call_completed=True` |

**Summary:** 10/10 scenarios passed. 0 instances of a stale/superseded
tool result being spoken as current across all trials, matching the
acceptance threshold defined above.

Raw run output (for reproducibility reference):

```
ID   | SCENARIO NAME                          | RESULT   | DETAILS
--------------------------------------------------------------------------------
S0   | Baseline Uninterrupted Lookup          | PASS     | Lookup completed cleanly without stale fencing
S1   | Proactive Update                       | PASS     | proactive_update=True, completed=True
S2   | Redirect (1023 -> 4521)                | PASS     | redirect=True, stale_discarded=True, final_completed=True
S3   | Status Check                           | PASS     | status_check=True, completed=True
S4   | Explicit Cancel                        | PASS     | cancel_tool=True, stale/cancelled=True
S5   | Constraint Refinement                  | PASS     | constraint_added=True, constraint_returned=True
S6   | Rapid Double Redirect                  | PASS     | cancelled_in_flight_count=2, stale_discard_count=2, final_completed=True
S7   | Constraint then Redirect               | PASS     | constraint=True, redirect=True, stale=True, completed=True
S8   | Cancel during Proactive Window         | PASS     | proactive=True, cancel_tool=True, stale/cancelled=True
S9   | Non-existent Order Lookup              | PASS     | not_found=True, tool_call_completed=True
--------------------------------------------------------------------------------
SUMMARY: 10/10 SCENARIOS PASSED
==========================================================================
```

---

## Limitations

[FILL IN — be specific to what you know isn't covered. Starting points
based on the test design above:]
- Tool delay (3.5s) and poll interval (0.25s) are fixed/simulated values,
  not validated against variable real-world backend latency.
- Scenarios run one trial each per script execution — not yet run across
  multiple repeated executions to check for flakiness/race conditions.
- [Note if rapid-fire interruptions beyond S6's double-redirect (e.g.,
  triple redirects) are untested.]
- [Note any STT/VAD constraint — e.g., does this rely on clean turn
  boundaries, or has it been tested with overlapping/barge-in speech?]
- [Any tool other than order lookup not yet covered by continuity logic?]

---

## Reproduce It

```bash
# Run full automated stress test suite (all 10 scenarios)
python check_stress_test.py

# Validate against an existing evidence log
python check_stress_test.py logs/tool_calls.jsonl
```

Evidence log location: `logs/tool_calls.jsonl`
Live event stream: LiveKit room data channel, topic `continuity-events`
(`reliable=True`)
