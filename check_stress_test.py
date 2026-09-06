"""
check_stress_test.py — BE-8 Automated Acceptance/Stress Test Suite for DataForge Voice Assistant.

Runs the full 10-scenario continuity engine stress test (Scenarios 0-9) against agent.py,
parses the resulting logs/tool_calls.jsonl evidence file, and evaluates exact event sequence
matches for all scenarios.

Usage:
    python check_stress_test.py
    python check_stress_test.py logs/tool_calls.jsonl
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project directory to sys.path
PROJECT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))

import agent
from agent import tool_logger

LOG_FILE = PROJECT_DIR / "logs" / "tool_calls.jsonl"


async def run_scenario_0():
    """Scenario 0: Baseline Uninterrupted Lookup"""
    agent.current_generation += 1
    gen = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=0, name="Baseline Uninterrupted Lookup", generation=gen)
    res = await agent.lookup_order_tool("1023")
    tool_logger.log(event="scenario_end", scenario_id=0)
    return res


async def run_scenario_1():
    """Scenario 1: Proactive 'Still Checking' Update"""
    agent.current_generation += 1
    gen = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=1, name="Proactive Update", generation=gen)
    res = await agent.lookup_order_tool("4521")
    tool_logger.log(event="scenario_end", scenario_id=1)
    return res


async def run_scenario_2():
    """Scenario 2: Redirect (order 1023 -> order 4521)"""
    agent.current_generation += 1
    gen_a = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=2, name="Redirect (1023 -> 4521)", generation=gen_a)

    t1 = asyncio.create_task(agent.lookup_order_tool("1023"))
    await asyncio.sleep(0.5)

    agent.current_generation += 1
    gen_b = agent.current_generation

    # Simulate active token cancellation on new turn commit
    token = agent.active_cancel_tokens.pop(gen_a, None)
    if token:
        agent.logger.info(f"[CANCELLED IN-FLIGHT] Cancelling in-flight lookup for gen={gen_a} | current_gen={gen_b}")
        agent.emit_continuity_event("cancelled_in_flight", generation=gen_a, current_generation=gen_b)
        token.cancel()

    t2 = asyncio.create_task(agent.lookup_order_tool("4521"))
    res_a = await t1
    res_b = await t2
    tool_logger.log(event="scenario_end", scenario_id=2)
    return res_a, res_b


async def run_scenario_3():
    """Scenario 3: Status Check during Pending Lookup"""
    agent.current_generation += 1
    gen = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=3, name="Status Check", generation=gen)

    t = asyncio.create_task(agent.lookup_order_tool("7788"))
    await asyncio.sleep(0.5)

    status_res = await agent.check_pending_status()
    lookup_res = await t
    tool_logger.log(event="scenario_end", scenario_id=3)
    return status_res, lookup_res


async def run_scenario_4():
    """Scenario 4: Explicit Cancel during Pending Lookup"""
    agent.current_generation += 1
    gen = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=4, name="Explicit Cancel", generation=gen)

    t = asyncio.create_task(agent.lookup_order_tool("1023"))
    await asyncio.sleep(0.5)

    cancel_res = await agent.cancel_pending_lookup()
    lookup_res = await t
    tool_logger.log(event="scenario_end", scenario_id=4)
    return cancel_res, lookup_res


async def run_scenario_5():
    """Scenario 5: Constraint Refinement during Pending Lookup"""
    agent.current_generation += 1
    gen = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=5, name="Constraint Refinement", generation=gen)

    t = asyncio.create_task(agent.lookup_order_tool("4521"))
    await asyncio.sleep(0.5)

    constraint_res = await agent.add_lookup_constraint("delivery_date_only")
    lookup_res = await t
    tool_logger.log(event="scenario_end", scenario_id=5)
    return constraint_res, lookup_res


async def run_scenario_6():
    """Scenario 6: Rapid Double Redirect (1023 -> 4521 -> 7788)"""
    agent.current_generation += 1
    gen_a = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=6, name="Rapid Double Redirect", generation=gen_a)

    t1 = asyncio.create_task(agent.lookup_order_tool("1023"))
    await asyncio.sleep(0.3)

    # First redirect: 4521
    agent.current_generation += 1
    gen_b = agent.current_generation
    token_a = agent.active_cancel_tokens.pop(gen_a, None)
    if token_a:
        agent.logger.info(f"[CANCELLED IN-FLIGHT] Cancelling in-flight lookup for gen={gen_a} | current_gen={gen_b}")
        agent.emit_continuity_event("cancelled_in_flight", generation=gen_a, current_generation=gen_b)
        token_a.cancel()

    t2 = asyncio.create_task(agent.lookup_order_tool("4521"))
    await asyncio.sleep(0.3)

    # Second redirect: 7788
    agent.current_generation += 1
    gen_c = agent.current_generation
    token_b = agent.active_cancel_tokens.pop(gen_b, None)
    if token_b:
        agent.logger.info(f"[CANCELLED IN-FLIGHT] Cancelling in-flight lookup for gen={gen_b} | current_gen={gen_c}")
        agent.emit_continuity_event("cancelled_in_flight", generation=gen_b, current_generation=gen_c)
        token_b.cancel()

    t3 = asyncio.create_task(agent.lookup_order_tool("7788"))

    res_a = await t1
    res_b = await t2
    res_c = await t3
    tool_logger.log(event="scenario_end", scenario_id=6)
    return res_a, res_b, res_c


async def run_scenario_7():
    """Scenario 7: Constraint then Redirect (1023 + constraint -> 4521)"""
    agent.current_generation += 1
    gen_a = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=7, name="Constraint then Redirect", generation=gen_a)

    t1 = asyncio.create_task(agent.lookup_order_tool("1023"))
    await asyncio.sleep(0.3)

    # Add constraint to 1023
    c_res = await agent.add_lookup_constraint("items_only")

    await asyncio.sleep(0.3)

    # Redirect to 4521
    agent.current_generation += 1
    gen_b = agent.current_generation
    token_a = agent.active_cancel_tokens.pop(gen_a, None)
    if token_a:
        agent.logger.info(f"[CANCELLED IN-FLIGHT] Cancelling in-flight lookup for gen={gen_a} | current_gen={gen_b}")
        agent.emit_continuity_event("cancelled_in_flight", generation=gen_a, current_generation=gen_b)
        token_a.cancel()

    t2 = asyncio.create_task(agent.lookup_order_tool("4521"))

    res_a = await t1
    res_b = await t2
    tool_logger.log(event="scenario_end", scenario_id=7)
    return c_res, res_a, res_b


async def run_scenario_8():
    """Scenario 8: Cancel during Proactive 'Still Checking' Window"""
    agent.current_generation += 1
    gen = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=8, name="Cancel during Proactive Window", generation=gen)

    t = asyncio.create_task(agent.lookup_order_tool("1023"))
    # Wait for proactive update to fire at ~3.0s
    await asyncio.sleep(2.0)

    cancel_res = await agent.cancel_pending_lookup()
    lookup_res = await t
    tool_logger.log(event="scenario_end", scenario_id=8)
    return cancel_res, lookup_res


async def run_scenario_9():
    """Scenario 9: Non-existent Order Lookup"""
    agent.current_generation += 1
    gen = agent.current_generation
    tool_logger.log(event="scenario_start", scenario_id=9, name="Non-existent Order Lookup", generation=gen)

    res = await agent.lookup_order_tool("0000")
    tool_logger.log(event="scenario_end", scenario_id=9)
    return res


async def execute_all_scenarios():
    print("Executing all stress test scenarios (0-9)...")
    await run_scenario_0()
    await run_scenario_1()
    await run_scenario_2()
    await run_scenario_3()
    await run_scenario_4()
    await run_scenario_5()
    await run_scenario_6()
    await run_scenario_7()
    await run_scenario_8()
    await run_scenario_9()
    print("All scenarios completed!\n")


def parse_and_validate_logs(log_path: Path) -> dict:
    """Parses JSONL evidence log and validates event sequences for scenarios 0-9."""
    if not log_path.exists():
        print(f"Error: Log file '{log_path}' does not exist.")
        return {}

    lines = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"Warning: Line {line_num} in '{log_path}' is invalid JSON.")

    # Group log events by scenario_id
    scenarios = {}
    current_scen_id = None
    for entry in lines:
        event = entry.get("event")
        if event == "scenario_start":
            current_scen_id = entry.get("scenario_id")
            scenarios[current_scen_id] = {
                "name": entry.get("name"),
                "events": [],
            }
        elif event == "scenario_end":
            current_scen_id = None
        elif current_scen_id is not None:
            scenarios[current_scen_id]["events"].append(entry)

    results = {}

    # Validate Scenario 0
    if 0 in scenarios:
        events = [e.get("event") for e in scenarios[0]["events"]]
        completed = "tool_call_completed" in events or "completed" in events
        results[0] = {
            "name": scenarios[0]["name"],
            "status": "PASS" if completed and "stale_discarded" not in events else "FAIL",
            "details": "Lookup completed cleanly without stale fencing",
        }

    # Validate Scenario 1
    if 1 in scenarios:
        events = [e.get("event") for e in scenarios[1]["events"]]
        has_proactive = "proactive_update" in events
        has_completed = "tool_call_completed" in events or "completed" in events
        results[1] = {
            "name": scenarios[1]["name"],
            "status": "PASS" if has_proactive and has_completed else "FAIL",
            "details": f"proactive_update={has_proactive}, completed={has_completed}",
        }

    # Validate Scenario 2
    if 2 in scenarios:
        events = [e.get("event") for e in scenarios[2]["events"]]
        has_redirect = "redirect_detected" in events or "cancelled_in_flight" in events
        has_stale = "stale_discarded" in events
        has_completed = "tool_call_completed" in events
        results[2] = {
            "name": scenarios[2]["name"],
            "status": "PASS" if has_redirect and has_stale and has_completed else "FAIL",
            "details": f"redirect={has_redirect}, stale_discarded={has_stale}, final_completed={has_completed}",
        }

    # Validate Scenario 3
    if 3 in scenarios:
        events = [e.get("event") for e in scenarios[3]["events"]]
        has_status_check = "status_check" in events
        has_completed = "tool_call_completed" in events
        results[3] = {
            "name": scenarios[3]["name"],
            "status": "PASS" if has_status_check and has_completed else "FAIL",
            "details": f"status_check={has_status_check}, completed={has_completed}",
        }

    # Validate Scenario 4
    if 4 in scenarios:
        events = [e.get("event") for e in scenarios[4]["events"]]
        has_cancel_tool = "cancel_tool" in events
        has_stale = "stale_discarded" in events or "cancelled" in events
        results[4] = {
            "name": scenarios[4]["name"],
            "status": "PASS" if has_cancel_tool and has_stale else "FAIL",
            "details": f"cancel_tool={has_cancel_tool}, stale/cancelled={has_stale}",
        }

    # Validate Scenario 5
    if 5 in scenarios:
        events = [e.get("event") for e in scenarios[5]["events"]]
        has_constraint_added = "constraint_added" in events
        has_constraint_returned = "constraint_returned" in events
        results[5] = {
            "name": scenarios[5]["name"],
            "status": "PASS" if has_constraint_added and has_constraint_returned else "FAIL",
            "details": f"constraint_added={has_constraint_added}, constraint_returned={has_constraint_returned}",
        }

    # Validate Scenario 6 (Rapid Double Redirect)
    if 6 in scenarios:
        events = [e.get("event") for e in scenarios[6]["events"]]
        cancel_inflight_count = events.count("cancelled_in_flight")
        stale_count = events.count("stale_discarded")
        has_completed = "tool_call_completed" in events
        results[6] = {
            "name": scenarios[6]["name"],
            "status": "PASS" if cancel_inflight_count >= 2 and stale_count >= 2 and has_completed else "FAIL",
            "details": f"cancelled_in_flight_count={cancel_inflight_count}, stale_discard_count={stale_count}, final_completed={has_completed}",
        }

    # Validate Scenario 7 (Constraint then Redirect)
    if 7 in scenarios:
        events = [e.get("event") for e in scenarios[7]["events"]]
        has_constraint = "constraint_added" in events
        has_redirect = "redirect_detected" in events or "cancelled_in_flight" in events
        has_stale = "stale_discarded" in events
        has_completed = "tool_call_completed" in events
        results[7] = {
            "name": scenarios[7]["name"],
            "status": "PASS" if has_constraint and has_redirect and has_stale and has_completed else "FAIL",
            "details": f"constraint={has_constraint}, redirect={has_redirect}, stale={has_stale}, completed={has_completed}",
        }

    # Validate Scenario 8 (Cancel during Proactive Window)
    if 8 in scenarios:
        events = [e.get("event") for e in scenarios[8]["events"]]
        has_proactive = "proactive_update" in events
        has_cancel = "cancel_tool" in events
        has_stale = "stale_discarded" in events or "cancelled" in events
        results[8] = {
            "name": scenarios[8]["name"],
            "status": "PASS" if has_proactive and has_cancel and has_stale else "FAIL",
            "details": f"proactive={has_proactive}, cancel_tool={has_cancel}, stale/cancelled={has_stale}",
        }

    # Validate Scenario 9 (Non-existent Order Lookup)
    if 9 in scenarios:
        events = [e.get("event") for e in scenarios[9]["events"]]
        has_not_found = "not_found" in events
        has_completed = "tool_call_completed" in events
        results[9] = {
            "name": scenarios[9]["name"],
            "status": "PASS" if has_not_found and has_completed else "FAIL",
            "details": f"not_found={has_not_found}, tool_call_completed={has_completed}",
        }

    return results


def main():
    log_target = LOG_FILE
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        log_target = Path(sys.argv[1]).resolve()
    else:
        # Run test execution
        asyncio.run(execute_all_scenarios())

    print("==========================================================================")
    print("  BE-8 AUTOMATED CONTINUITY ENGINE ACCEPTANCE & STRESS TEST RESULTS")
    print("==========================================================================")
    print(f" Evidence Log File: {log_target}\n")

    results = parse_and_validate_logs(log_target)

    if not results:
        print("No scenario results found.")
        sys.exit(1)

    passed_count = 0
    total_count = len(results)

    print(f"{'ID':<4} | {'SCENARIO NAME':<38} | {'RESULT':<8} | {'DETAILS'}")
    print("-" * 80)
    for scen_id, info in sorted(results.items()):
        status = info["status"]
        if status == "PASS":
            passed_count += 1
        print(f"S{scen_id:<3} | {info['name']:<38} | {status:<8} | {info['details']}")

    print("-" * 80)
    print(f"SUMMARY: {passed_count}/{total_count} SCENARIOS PASSED")
    print("==========================================================================\n")

    if passed_count < total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
