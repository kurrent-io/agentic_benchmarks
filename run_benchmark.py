"""Three-Database Benchmark: PostgreSQL vs PostgreSQL+CDC vs KurrentDB

Compares what each database approach can and cannot answer:
- PostgreSQL (CRUD): Current state only
- PostgreSQL+CDC: Change history (before/after values)
- KurrentDB: Full event stream with intent/reason

Usage:
    python run_benchmark.py                    # Run 10 questions (default)
    python run_benchmark.py --num 10           # Run specific number
    python run_benchmark.py --tier 1           # Run only tier 1
    python run_benchmark.py --quick            # Shorter delays
"""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from benchmark_queries import generate_questions

# =============================================================================
# CONFIGURATION
# =============================================================================

MCP_SERVERS = {
    "postgres": "http://localhost:3000",
    "postgres_cdc": "http://localhost:3000",
    "kurrentdb": "http://localhost:3003",
}

DB_NAMES = {
    "postgres": "PostgreSQL",
    "postgres_cdc": "PostgreSQL+CDC",
    "kurrentdb": "KurrentDB",
}

ALL_DBS = ["postgres", "postgres_cdc", "kurrentdb"]

# Cost per token (Claude 3.5 Haiku)
COST_PER_1K_INPUT = 0.001
COST_PER_1K_OUTPUT = 0.005


def log(msg: str):
    msg_str = str(msg).encode('ascii', 'replace').decode('ascii')
    sys.stdout.write(msg_str + "\n")
    sys.stdout.flush()


# =============================================================================
# TEST DATA SETUP
# =============================================================================

def setup_scenario_data(scenario: dict, entity_id: str):
    """Set up test data for a single scenario in all three databases."""
    import psycopg
    import httpx

    setup = scenario["setup"]
    domain = scenario.get("domain", "test")
    entity_type = scenario["entity"]

    # PostgreSQL - current state + CDC
    conn = psycopg.connect("postgresql://bench:bench@localhost:5432/benchmark", connect_timeout=10)
    try:
        with conn.cursor() as cur:
            # Create schemas
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {domain}")
            cur.execute("CREATE SCHEMA IF NOT EXISTS cdc")

            # Create generic entity table for this scenario
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {domain}.{entity_type}s (
                    id VARCHAR(100) PRIMARY KEY,
                    data JSONB DEFAULT '{{}}'::jsonb
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cdc.cdc_events (
                    id SERIAL PRIMARY KEY, entity_type VARCHAR(50), entity_id VARCHAR(100),
                    op CHAR(1), before_state JSONB, after_state JSONB, ts_ms BIGINT, source JSONB
                )
            """)

            # Insert current state
            cur.execute(f"""
                INSERT INTO {domain}.{entity_type}s (id, data)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
            """, (entity_id, json.dumps(setup["current"])))

            # Insert CDC event (before -> after change)
            cur.execute("""
                INSERT INTO cdc.cdc_events (entity_type, entity_id, op, before_state, after_state, ts_ms, source)
                VALUES (%s, %s, 'u', %s, %s, %s, '{"connector": "benchmark"}')
            """, (entity_type, entity_id, json.dumps(setup["previous"]), json.dumps(setup["current"]), int(time.time() * 1000)))
            conn.commit()
    finally:
        conn.close()

    # KurrentDB - events with reason
    stream_name = f"{entity_type}-{entity_id}"
    events = []
    is_temporal = setup.get("temporal", False)

    if is_temporal:
        # Temporal: events are dicts with type, offset_hours, and optional extra fields
        from datetime import datetime, timedelta
        base_time = datetime(2024, 1, 15, 10, 0, 0)
        for evt in setup.get("events", []):
            ts = base_time + timedelta(hours=evt["offset_hours"])
            event_data = {
                "entity_id": entity_id,
                "timestamp": ts.isoformat(),
                "offset_hours": evt["offset_hours"],
            }
            # Include any extra fields from the event definition
            for k, v in evt.items():
                if k not in ("type", "offset_hours"):
                    event_data[k] = v
            event_data["previous"] = setup["previous"]
            event_data["current"] = setup["current"]
            event_data["reason"] = setup.get("reason")
            events.append({"eventType": evt["type"], "data": event_data})
    else:
        # Standard: events are plain strings
        for event_type in setup.get("events", []):
            event_data = {
                "entity_id": entity_id,
                "previous": setup["previous"],
                "current": setup["current"],
                "reason": setup.get("reason"),
            }
            events.append({"eventType": event_type, "data": event_data})

    # Also write temporal CDC events (multiple before/after records)
    if is_temporal:
        try:
            conn2 = psycopg.connect("postgresql://bench:bench@localhost:5432/benchmark", connect_timeout=10)
            with conn2.cursor() as cur:
                base_ms = 1705312800000  # 2024-01-15 10:00 UTC in ms
                for evt in setup.get("events", []):
                    ts_ms = base_ms + int(evt["offset_hours"] * 3600 * 1000)
                    evt_data = {}
                    for k, v in evt.items():
                        if k not in ("type", "offset_hours"):
                            evt_data[k] = v
                    cur.execute("""
                        INSERT INTO cdc.cdc_events (entity_type, entity_id, op, before_state, after_state, ts_ms, source)
                        VALUES (%s, %s, 'u', %s, %s, %s, '{"connector": "benchmark"}')
                    """, (entity_type, entity_id, json.dumps(setup["previous"]), json.dumps({**setup["current"], **evt_data, "event_type": evt["type"]}), ts_ms))
                conn2.commit()
            conn2.close()
        except Exception as e:
            log(f"  Warning writing temporal CDC: {e}")

    with httpx.Client(timeout=15.0) as client:
        for event in events:
            try:
                client.post(f"http://localhost:2113/streams/{stream_name}",
                    headers={"Content-Type": "application/vnd.eventstore.events+json"},
                    json=[{"eventId": str(uuid.uuid4()), "eventType": event["eventType"], "data": event["data"]}])
            except Exception as e:
                log(f"  Warning writing event: {e}")
            time.sleep(0.2)

    return entity_id


# =============================================================================
# BENCHMARK QUESTIONS
# =============================================================================

def select_questions(num_questions: int, tier: int = None, seed: int = 42) -> list[dict]:
    """Generate questions from pool-based templates and set up test data."""
    all_questions = generate_questions(num_questions, seed=seed, tier=tier)

    prepared = []
    for q in all_questions:
        entity_id = f"bench-{uuid.uuid4().hex[:8]}"

        # Build scenario dict for setup
        scenario = {
            "domain": q["domain"],
            "entity": q["entity"],
            "setup": q["setup"],
        }

        # Set up test data in databases
        log(f"Setting up: {q['domain']}/{q['scenario_name']} ({entity_id})")
        setup_scenario_data(scenario, entity_id)
        time.sleep(0.5)  # Small delay between setups

        # Build the prompts for each database
        question_text = q["question"].replace("{id}", entity_id)
        entity_type = q["entity"]
        domain = q["domain"]

        # Generate database-specific prompts
        prompts = {
            "postgres": f"Query {domain}.{entity_type}s to find the answer for entity '{entity_id}'. The data is in JSONB format in the 'data' column. Question: {question_text}",
            "postgres_cdc": f"Query cdc.cdc_events where entity_id='{entity_id}' and entity_type='{entity_type}'. Use before_state for previous values, after_state for current. Question: {question_text}",
            "kurrentdb": f"Read stream '{entity_type}-{entity_id}' to find the answer. Events have 'previous', 'current', and 'reason' fields. Question: {question_text}",
        }

        prepared.append({
            "tier": q["tier"],
            "id": f"{q['scenario_id']}_t{q['tier']}",
            "name": f"{q['scenario_name']} (T{q['tier']})",
            "domain": q["domain"],
            "question": question_text,
            "expected": str(q["expected"]),
            "cdc_limitation": q.get("cdc_limitation"),
            "prompts": prompts,
            "entity_id": entity_id,
        })

    return prepared


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================

def run_benchmark(questions: list, delay: int = 3):
    """Run benchmark - all DBs attempt all questions."""
    from framework.agents.claude import ClaudeClient, ClaudeConfig
    from framework.agents.judge import JudgeAgent
    from framework.agents.mcp_retrieval import MCPRetrievalAgent

    with open("benchmark.key") as f:
        api_key = f.read().strip()

    config = ClaudeConfig(api_key=api_key, model="claude-3-5-haiku-20241022", max_tokens=1024)
    client = ClaudeClient(config)
    judge = JudgeAgent(llm_client=client)

    results = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "model": config.model,
            "num_questions": len(questions),
            "num_databases": len(ALL_DBS),
        },
        "totals": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_time_s": 0,
            "cost_usd": 0,
        },
        "by_database": {db: {"correct": 0, "wrong": 0, "total": 0, "tokens": 0, "time_s": 0} for db in ALL_DBS},
        "by_tier": {1: {"correct": 0, "total": 0}, 2: {"correct": 0, "total": 0}, 3: {"correct": 0, "total": 0}, 4: {"correct": 0, "total": 0}},
        "questions": [],
    }

    total = len(questions) * len(ALL_DBS)
    test_num = 0
    benchmark_start = time.time()

    for q in questions:
        log(f"\n{'='*60}")
        log(f"TIER {q['tier']}: {q['name']}")
        log(f"{'='*60}")
        log(f"Q: {q['question']}")
        log(f"Expected: {q['expected']}")

        q_result = {
            "tier": q["tier"],
            "id": q["id"],
            "name": q["name"],
            "domain": q["domain"],
            "question": q["question"],
            "expected": q["expected"],
            "cdc_limitation": q.get("cdc_limitation"),
            "databases": {}
        }

        for db in ALL_DBS:
            test_num += 1
            log(f"\n  [{test_num}/{total}] {DB_NAMES[db]}:")

            agent = None
            try:
                agent = MCPRetrievalAgent(mcp_servers={db: MCP_SERVERS[db]}, llm_client=client)
                agent.__enter__()

                start = time.time()
                result = agent.answer(q["prompts"][db])
                elapsed = time.time() - start

                judgment = judge.judge(question=q["question"], expected_answer=q["expected"], given_answer=result.answer)

                status = "OK" if judgment.is_correct else "FAIL"
                log(f"    [{status}] {elapsed:.1f}s | {result.prompt_tokens}+{result.completion_tokens} tokens")
                log(f"    Answer: {result.answer[:100].replace(chr(10), ' ')}...")

                q_result["databases"][db] = {
                    "answer": result.answer,
                    "correct": judgment.is_correct,
                    "time_s": round(elapsed, 2),
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                }

                # Update totals
                results["totals"]["prompt_tokens"] += result.prompt_tokens
                results["totals"]["completion_tokens"] += result.completion_tokens
                results["totals"]["total_time_s"] += elapsed

                # Update by_database
                results["by_database"][db]["total"] += 1
                results["by_database"][db]["tokens"] += result.prompt_tokens + result.completion_tokens
                results["by_database"][db]["time_s"] += elapsed
                if judgment.is_correct:
                    results["by_database"][db]["correct"] += 1
                else:
                    results["by_database"][db]["wrong"] += 1

                # Update by_tier
                results["by_tier"][q["tier"]]["total"] += 1
                if judgment.is_correct:
                    results["by_tier"][q["tier"]]["correct"] += 1

            except Exception as e:
                log(f"    [ERROR] {str(e)[:60]}")
                q_result["databases"][db] = {"error": str(e), "correct": False}
                results["by_database"][db]["total"] += 1
                results["by_database"][db]["wrong"] += 1
                results["by_tier"][q["tier"]]["total"] += 1

            finally:
                if agent:
                    try:
                        agent.__exit__(None, None, None)
                    except:
                        pass
                time.sleep(delay)

        results["questions"].append(q_result)

    # Calculate cost
    results["totals"]["cost_usd"] = (
        results["totals"]["prompt_tokens"] * COST_PER_1K_INPUT / 1000 +
        results["totals"]["completion_tokens"] * COST_PER_1K_OUTPUT / 1000
    )
    results["totals"]["total_time_s"] = round(time.time() - benchmark_start, 1)

    return results


# =============================================================================
# HTML REPORT TEMPLATE
# =============================================================================

def generate_html_report(results: dict, output_path: Path):
    """Generate comprehensive HTML report."""
    import html as h

    # Calculate stats
    total_tokens = results["totals"]["prompt_tokens"] + results["totals"]["completion_tokens"]
    total_tests = sum(results["by_database"][db]["total"] for db in ALL_DBS)
    total_correct = sum(results["by_database"][db]["correct"] for db in ALL_DBS)

    # Database summary rows
    db_rows = ""
    for db in ALL_DBS:
        s = results["by_database"][db]
        accuracy = (s["correct"] / s["total"] * 100) if s["total"] > 0 else 0
        avg_time = (s["time_s"] / s["total"]) if s["total"] > 0 else 0
        db_rows += f'''<tr>
            <td><strong>{DB_NAMES[db]}</strong></td>
            <td class="num">{s["correct"]}</td>
            <td class="num">{s["wrong"]}</td>
            <td class="num">{s["total"]}</td>
            <td class="num {'good' if accuracy >= 80 else 'bad' if accuracy < 50 else ''}">{accuracy:.0f}%</td>
            <td class="num">{s["tokens"]:,}</td>
            <td class="num">{avg_time:.1f}s</td>
        </tr>'''

    # Tier summary rows
    tier_rows = ""
    tier_names = {1: "Easy", 2: "Medium", 3: "Hard", 4: "Temporal"}
    for tier in [1, 2, 3, 4]:
        s = results["by_tier"][tier]
        accuracy = (s["correct"] / s["total"] * 100) if s["total"] > 0 else 0
        tier_rows += f'''<tr>
            <td><span class="badge tier{tier}">Tier {tier}</span> {tier_names[tier]}</td>
            <td class="num">{s["correct"]}/{s["total"]}</td>
            <td class="num {'good' if accuracy >= 80 else 'bad' if accuracy < 50 else ''}">{accuracy:.0f}%</td>
        </tr>'''

    # Collect unique domains for filters
    domains = sorted(set(q.get("domain", "unknown") for q in results["questions"]))

    # Question cards
    question_cards = ""
    for q in results["questions"]:
        db_results_html = ""
        for db in ALL_DBS:
            data = q["databases"].get(db, {})
            is_correct = data.get("correct", False)
            answer = h.escape(str(data.get("answer", data.get("error", "N/A"))))
            tokens = data.get("prompt_tokens", 0) + data.get("completion_tokens", 0)
            time_s = data.get("time_s", 0)

            badge_class = "badge-pass" if is_correct else "badge-fail"
            badge_text = "PASS" if is_correct else "FAIL"

            db_results_html += f'''
            <div class="db-result {'correct' if is_correct else 'wrong'}">
                <div class="db-header">
                    <span class="db-name">{DB_NAMES[db]}</span>
                    <span class="badge {badge_class}">{badge_text}</span>
                </div>
                <div class="answer">{answer[:500]}{"..." if len(answer) > 500 else ""}</div>
                <div class="meta">
                    <span>{tokens:,} tokens</span>
                    <span>{time_s:.1f}s</span>
                </div>
            </div>'''

        domain = q.get("domain", "unknown")
        question_cards += f'''
        <div class="question-card" data-tier="{q['tier']}" data-domain="{domain}">
            <div class="q-header" onclick="this.parentElement.classList.toggle('open')">
                <div class="q-title">
                    <span class="badge tier{q['tier']}">Tier {q['tier']}</span>
                    <span class="badge domain">{domain}</span>
                    <span class="q-name">{q['name']}</span>
                </div>
                <span class="arrow">&#9662;</span>
            </div>
            <div class="q-body">
                <div class="question-text">{h.escape(q['question'])}</div>
                <div class="expected"><strong>Expected Answer:</strong> {h.escape(str(q['expected']))}</div>
                <div class="db-results">{db_results_html}</div>
            </div>
        </div>'''

    # Build domain filter buttons
    domain_buttons = "".join(f'<button class="filter-btn" data-domain="{d}">{d}</button>' for d in domains)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Writing Events Is All You Need</title>
    <style>
        :root {{
            --bg: #0a0a0a; --card: #141414; --card2: #1a1a1a; --border: #2a2a2a;
            --text: #ffffff; --muted: #888888;
            --green: #22c55e; --red: #ef4444; --yellow: #eab308; --blue: #3b82f6; --purple: #8b5cf6;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 40px 24px; }}

        header {{ text-align: center; padding: 40px 0; border-bottom: 1px solid var(--border); margin-bottom: 40px; }}
        h1 {{ font-size: 2.2rem; margin-bottom: 8px; }}
        .subtitle {{ color: var(--muted); margin-bottom: 4px; }}

        .stats-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-bottom: 40px; }}
        .stat {{ background: var(--card); padding: 24px; text-align: center; }}
        .stat .value {{ font-size: 2rem; font-weight: 700; }}
        .stat .label {{ font-size: 0.75rem; text-transform: uppercase; color: var(--muted); margin-top: 4px; }}

        .section {{ margin-bottom: 40px; }}
        .section h2 {{ font-size: 1.2rem; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
        .tier-explanation {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 16px; }}

        table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }}
        th {{ text-align: left; padding: 14px 20px; font-size: 0.75rem; text-transform: uppercase; color: var(--muted); background: var(--card2); }}
        td {{ padding: 14px 20px; border-bottom: 1px solid var(--border); }}
        tr:last-child td {{ border-bottom: none; }}
        .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        .good {{ color: var(--green); }}
        .bad {{ color: var(--red); }}

        .badge {{ display: inline-flex; padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
        .badge-pass {{ background: rgba(34, 197, 94, 0.15); color: var(--green); }}
        .badge-fail {{ background: rgba(239, 68, 68, 0.15); color: var(--red); }}
        .tier1 {{ background: rgba(34, 197, 94, 0.15); color: var(--green); }}
        .tier2 {{ background: rgba(234, 179, 8, 0.15); color: var(--yellow); }}
        .tier3 {{ background: rgba(239, 68, 68, 0.15); color: var(--red); }}
        .tier4 {{ background: rgba(139, 92, 246, 0.15); color: var(--purple); }}

        .filters {{ display: flex; gap: 24px; margin-bottom: 20px; flex-wrap: wrap; align-items: center; }}
        .filter-group {{ display: flex; align-items: center; gap: 8px; }}
        .filter-label {{ font-size: 0.75rem; text-transform: uppercase; color: var(--muted); }}
        .filter-btn {{ background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; transition: all 0.2s; }}
        .filter-btn:hover {{ background: var(--card2); }}
        .filter-btn.active {{ background: var(--blue); border-color: var(--blue); }}
        .question-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 12px; overflow: hidden; }}
        .question-card.hidden {{ display: none; }}
        .q-header {{ padding: 16px 20px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }}
        .q-header:hover {{ background: var(--card2); }}
        .q-title {{ display: flex; align-items: center; gap: 12px; }}
        .q-name {{ font-weight: 600; }}
        .q-id {{ color: var(--muted); font-size: 0.85rem; }}
        .arrow {{ color: var(--muted); transition: transform 0.2s; }}
        .question-card.open .arrow {{ transform: rotate(180deg); }}
        .q-body {{ display: none; padding: 20px; border-top: 1px solid var(--border); background: var(--card2); }}
        .question-card.open .q-body {{ display: block; }}
        .question-text {{ background: var(--bg); padding: 16px; border-radius: 8px; margin-bottom: 12px; font-size: 1.05rem; }}
        .expected {{ margin-bottom: 12px; color: var(--muted); }}
        .badge.domain {{ background: rgba(59, 130, 246, 0.15); color: var(--blue); }}

        .db-results {{ display: flex; flex-direction: column; gap: 12px; }}
        .db-result {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
        .db-result.correct {{ border-color: rgba(34, 197, 94, 0.3); }}
        .db-result.wrong {{ border-color: rgba(239, 68, 68, 0.3); }}
        .db-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .db-name {{ font-weight: 600; }}
        .answer {{ background: var(--card); padding: 12px; border-radius: 6px; font-size: 0.85rem; color: var(--muted); max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }}
        .meta {{ display: flex; gap: 20px; margin-top: 10px; font-size: 0.75rem; color: var(--muted); }}

        footer {{ text-align: center; padding: 40px 0; border-top: 1px solid var(--border); margin-top: 40px; color: var(--muted); font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Writing Events Is All You Need</h1>
            <p class="subtitle">PostgreSQL vs PostgreSQL+CDC vs KurrentDB</p>
            <p class="subtitle">{results['metadata']['model']} | {results['metadata']['timestamp'][:19]}</p>
        </header>

        <div class="stats-grid">
            <div class="stat">
                <div class="value">{total_correct}/{total_tests}</div>
                <div class="label">Total Correct</div>
            </div>
            <div class="stat">
                <div class="value">{results['metadata']['num_questions']}</div>
                <div class="label">Questions</div>
            </div>
            <div class="stat">
                <div class="value">{total_tokens // 1000}k</div>
                <div class="label">Tokens</div>
            </div>
            <div class="stat">
                <div class="value">{results['totals']['total_time_s']:.0f}s</div>
                <div class="label">Total Time</div>
            </div>
            <div class="stat">
                <div class="value">${results['totals']['cost_usd']:.3f}</div>
                <div class="label">Cost</div>
            </div>
        </div>

        <div class="section">
            <h2>Results by Database</h2>
            <table>
                <thead>
                    <tr><th>Database</th><th class="num">Correct</th><th class="num">Wrong</th><th class="num">Total</th><th class="num">Accuracy</th><th class="num">Tokens</th><th class="num">Avg Time</th></tr>
                </thead>
                <tbody>{db_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <h2>Results by Tier</h2>
            <p class="tier-explanation"><strong>Tier 1 - Easy:</strong> Current state queries. <strong>Tier 2 - Medium:</strong> Change history queries. <strong>Tier 3 - Hard:</strong> Intent queries. <strong>Tier 4 - Temporal:</strong> Cross-event time and order reasoning.</p>
            <table>
                <thead>
                    <tr><th>Tier</th><th class="num">Score</th><th class="num">Accuracy</th></tr>
                </thead>
                <tbody>{tier_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <h2>Question Details</h2>
            <div class="filters">
                <div class="filter-group">
                    <span class="filter-label">Tier:</span>
                    <button class="filter-btn active" data-tier="all">All</button>
                    <button class="filter-btn" data-tier="1">Tier 1</button>
                    <button class="filter-btn" data-tier="2">Tier 2</button>
                    <button class="filter-btn" data-tier="3">Tier 3</button>
                    <button class="filter-btn" data-tier="4">Tier 4</button>
                </div>
                <div class="filter-group">
                    <span class="filter-label">Domain:</span>
                    <button class="filter-btn active" data-domain="all">All</button>
                    {domain_buttons}
                </div>
                <div class="filter-group" style="flex-grow:1">
                    <span class="filter-label">Search:</span>
                    <input type="text" id="text-filter" placeholder="Filter questions..." style="flex-grow:1; background:var(--card); border:1px solid var(--border); color:var(--text); padding:6px 12px; border-radius:6px; font-size:0.85rem; min-width:200px;" />
                </div>
            </div>
            <div id="questions-container">
                {question_cards}
            </div>
        </div>

        <footer>
        </footer>
    </div>
    <script>
        (function() {{
            let activeTier = 'all';
            let activeDomain = 'all';
            let searchText = '';

            function applyFilters() {{
                document.querySelectorAll('.question-card').forEach(card => {{
                    const cardTier = card.dataset.tier;
                    const cardDomain = card.dataset.domain;
                    const tierMatch = activeTier === 'all' || cardTier === activeTier;
                    const domainMatch = activeDomain === 'all' || cardDomain === activeDomain;
                    const textMatch = !searchText || card.textContent.toLowerCase().includes(searchText);
                    card.classList.toggle('hidden', !(tierMatch && domainMatch && textMatch));
                }});
            }}

            document.querySelectorAll('.filter-btn[data-tier]').forEach(btn => {{
                btn.addEventListener('click', () => {{
                    document.querySelectorAll('.filter-btn[data-tier]').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    activeTier = btn.dataset.tier;
                    applyFilters();
                }});
            }});

            document.querySelectorAll('.filter-btn[data-domain]').forEach(btn => {{
                btn.addEventListener('click', () => {{
                    document.querySelectorAll('.filter-btn[data-domain]').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    activeDomain = btn.dataset.domain;
                    applyFilters();
                }});
            }});

            document.getElementById('text-filter').addEventListener('input', (e) => {{
                searchText = e.target.value.toLowerCase();
                applyFilters();
            }});
        }})();
    </script>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"Report saved: {output_path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Three-Database Benchmark")
    parser.add_argument("--num", type=int, default=10, help="Number of questions to run (default: 10)")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run only specific tier")
    parser.add_argument("--quick", action="store_true", help="Shorter delays (1s vs 3s)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for question selection")
    args = parser.parse_args()

    log("=" * 60)
    log("THREE-DATABASE BENCHMARK")
    log("PostgreSQL vs PostgreSQL+CDC vs KurrentDB")
    log("=" * 60)

    log(f"\nSelecting and setting up {args.num} questions...")
    questions = select_questions(args.num, tier=args.tier, seed=args.seed)

    log(f"\nRunning {len(questions)} questions x {len(ALL_DBS)} databases = {len(questions) * len(ALL_DBS)} tests\n")

    delay = 1 if args.quick else 3
    results = run_benchmark(questions, delay=delay)

    # Save results
    output_dir = Path(".benchmark/runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = output_dir / f"benchmark_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    html_path = output_dir / f"benchmark_{ts}.html"
    generate_html_report(results, html_path)

    # Summary
    log("\n" + "=" * 60)
    log("RESULTS")
    log("=" * 60)
    for db in ALL_DBS:
        s = results["by_database"][db]
        pct = (s["correct"] / s["total"] * 100) if s["total"] > 0 else 0
        log(f"  {DB_NAMES[db]:20} {s['correct']}/{s['total']} ({pct:.0f}%)")

    log(f"\nTokens: {results['totals']['prompt_tokens'] + results['totals']['completion_tokens']:,}")
    log(f"Cost: ${results['totals']['cost_usd']:.3f}")
    log(f"Time: {results['totals']['total_time_s']:.0f}s")
    log(f"\nReport: {html_path}")

    import os
    os.system(f'start "" "{html_path.absolute()}"')


if __name__ == "__main__":
    main()
