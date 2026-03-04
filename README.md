# Agentic Retrieval Benchmark

**Writing Events Is All You Need**

This benchmark demonstrates that storing data as events rather than current state dramatically improves an AI agent's ability to answer questions about your data. When you write events, you preserve the *intent* and *reason* behind every change, information that the usual current state only or CDC CRUD databases usually lose forever. You can read the complete motivation at: https://www.kurrent.io/blog/writing-events-is-all-you-need/

## The Problem

When data changes, the previous value is overwritten. This creates an information gap:

| Question Type | Current State + CDC | Event Store |
|---------------|---------------|-------------|
| "What is the current status?" | Can answer | Can answer |
| "What was the previous status?" | Cannot answer | Can answer |
| "Why did the status change?" | Cannot answer | Can answer |

## Our Approach: Semi-Synthetic Datasets

We use **semi-synthetic data** based on real-world dataset schemas:

1. **Real schemas**: Entity structures from actual datasets (Olist, Berka, GitHub, BTS, MovieLens)
2. **Synthetic events**: Generated events with realistic reasons and intents
3. **Controlled ground truth**: We know the exact expected answers

This approach lets us:
- Test questions that real datasets can't answer (because they lack event history)
- Control the difficulty and coverage of test scenarios
- Ensure reproducibility with seeded generation

### The 5 Domains

| Domain | Based On | Entities | Example Tier 3 Question |
|--------|----------|----------|------------------------|
| **E-commerce** | Olist | Orders, Products, Reviews | "Why was the order cancelled?" |
| **Banking** | Berka | Accounts, Loans, Cards | "What caused the overdraft?" |
| **Software** | GitHub | PRs, Issues, Reviews | "Why was the PR closed?" |
| **Aviation** | BTS | Flights, Delays, Diversions | "Why was the flight cancelled?" |
| **Ratings** | MovieLens | Ratings, Tags, Watchlists | "Why did the user change their rating?" |

### Synthetic Conversion: Both Directions

A natural objection is: "Of course events win — you designed the data with events in mind." But the benchmark converts in both directions.

Note: When we refer to CRUD we refer to the usual way of overwriting the state to only keep the current state.

Some domains are **naturally CRUD-shaped**. Olist stores orders as rows with a status field. Berka stores account balances as current values. These systems were never designed to emit events. We synthetically *enriched* them — imagining what the event stream would have looked like if intent had been captured from the start. An order with `status = 'cancelled'` becomes `OrderCancelledByCustomer(reason="found_cheaper")`.

Other domains are **naturally event-shaped**. GitHub's API is inherently event-based — a PR has a timeline of actions: opened, review requested, changes requested, approved, merged. We synthetically *flattened* this into CRUD tables, deliberately destroying the action semantics. The full timeline collapses into a single row: `state = 'closed, not merged'`.

The result is the same regardless of direction:
- **Flattening events into CRUD** destroys information — the agent can no longer explain why a PR was closed
- **Enriching CRUD into events** adds information — the agent can now explain why an order was cancelled

This symmetry confirms that events are the maximal representation. Every CRUD table is a lossy projection of an event stream. The projection is one-way: you can always go from events to state, but you cannot go from state back to events.

## Five-Tier Benchmark

Questions are organized by difficulty:

| Tier | Difficulty | Question Type | Example |
|------|------------|---------------|---------|
| **Tier 1** | Easy | Current state | "What is the order status?" |
| **Tier 2** | Medium | Change history | "What was the previous status?" |
| **Tier 3** | Hard | Intent/reason | "Why was the status changed?" |
| **Tier 4** | Temporal | Cross-event ordering | "How many review rounds before approval?" |
| **Tier 5** | Adversarial | False premise detection | "Why was the order cancelled by the system?" (it wasn't) |

Temporal queries (Tier 4) are questions that depend on time and order across a long sequence of events, not just on recalling a single fact. They require the agent to read multiple events, understand their chronological order, and reason about gaps, durations, sequences, and trends.

Adversarial queries (Tier 5) contain a **false premise** — a wrong assumption baked into the question. The correct answer requires the agent to detect and correct the false assumption rather than blindly answering. For example, asking "Why was the order cancelled by the system?" when in fact the customer cancelled it.

### How Temporal Questions Work

Each domain has a temporal template with a **fixed multi-event sequence** and a pool of question variants:

```python
# Example: GitHub PR Review Timeline
"events": [
    {"type": "pr.opened",                "offset_hours": 0},
    {"type": "review.changes_requested", "offset_hours": 12},
    {"type": "pr.updated",               "offset_hours": 36},
    {"type": "review.changes_requested", "offset_hours": 48},
    {"type": "pr.updated",               "offset_hours": 72},
    {"type": "review.approved",          "offset_hours": 84},
    {"type": "pr.merged",                "offset_hours": 85},
]

# 4 question variants per template:
"How many rounds of review did PR {id} go through?"        # answer: 2
"How long was PR {id} open before merge?"                  # answer: 85 hours
"Time between last update and approval for PR {id}?"       # answer: 12 hours
"How many times were changes requested on PR {id}?"        # answer: 2
```

Unlike Tiers 1-3 (which sample random values from pools), Tier 4 uses a fixed event sequence and varies which *question* is asked about that sequence. The expected answer is computed by running the answer function against the event list. The complexity comes from requiring the agent to read multiple events and reason about their order — not from randomizing values.

At setup time, events are written to each database differently:
- **PostgreSQL**: One row with current state only — no event history available
- **PostgreSQL+CDC**: Multiple CDC records with `ts_ms` timestamps and `event_type` in after_state
- **KurrentDB**: Full event stream with each event as a separate entry including timestamps

## Databases Compared

| Database | Model | What It Stores |
|----------|-------|----------------|
| **PostgreSQL** | CRUD | Current state only |
| **PostgreSQL+CDC** | Change Data Capture | Before/after values |
| **KurrentDB** | Event Sourcing | Full event stream with intent |

## Pool-Based Dynamic Question Generation

Questions are generated on the fly from **27 templates** across 5 domains (17 standard + 5 temporal + 5 adversarial). Each standard template defines pools of possible values:

- **current_pool**: 4-8 possible current state values
- **previous_pool**: 4-8 possible previous state values
- **reason_pool**: 6-10 possible intent/reason values

At generation time, `generate_questions(num, seed)` samples from these pools for each question. The expected answer is always derived from the sampled value, so correctness is guaranteed.

```python
from benchmark_queries import generate_questions

# Generate 10 questions with default seed
questions = generate_questions(10)

# Generate 500 questions with a specific seed
questions = generate_questions(500, seed=99)

# Generate only Tier 3 (Hard) questions
questions = generate_questions(100, tier=3)
```

This means `--num 500` generates 500 unique questions without changing any template code. The `--seed` flag controls reproducibility — same seed always produces the same questions.

## Running the Benchmark

### Configure API Key

The benchmark requires an **Anthropic API key** to run. Provide it in one of these ways (checked in this order):

**Option 1: Environment Variable (Recommended for CI/automation)**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python run_benchmark.py
```

**Option 2: `.env` File (Recommended for local development)**
```bash
# Copy the template
cp .env.example .env

# Edit .env and add your API key
ANTHROPIC_API_KEY=sk-ant-...

# Run benchmark (key is loaded automatically)
python run_benchmark.py
```

**Option 3: `benchmark.key` File**
```bash
echo "sk-ant-..." > benchmark.key
python run_benchmark.py
```

### Prerequisites

```bash
# Start databases
docker compose up -d

# Verify services are healthy
docker compose ps
```

### Run Benchmark

```bash
# Run with 10 questions (default)
python run_benchmark.py

# Run with more questions
python run_benchmark.py --num 50

# Run specific tier only
python run_benchmark.py --tier 3

# Quick mode (shorter delays)
python run_benchmark.py --num 20 --quick
```

### Output

Results are saved to `.benchmark/runs/` with:
- JSON data file
- HTML report with filtering by tier and domain

### Clearing Data Between Runs

The benchmark does **not** automatically clear data between runs — it accumulates in the databases. Each question generates a unique entity ID, so multiple runs won't interfere with each other. However, if you want a completely clean slate:

```bash
# Stop containers and remove volumes
docker compose down -v

# Restart with fresh databases
docker compose up -d
```

The `-v` flag removes the named volumes (`postgres_data`, `kurrentdb_data`), giving you completely fresh databases.

### Viewing the Dataset

After running the benchmark, you can inspect the data that was inserted into each database:

**PostgreSQL - Current State Tables**
```bash
# Connect to PostgreSQL via Docker
docker compose exec postgres psql -U bench -d benchmark

# View all schemas and tables
\dn
\dt olist.*
\dt berka.*

# Query current state (example: Olist orders)
SELECT * FROM olist.orders;

# Query CDC events (change history)
SELECT entity_type, entity_id, op, before_state, after_state, ts_ms 
FROM cdc.cdc_events 
ORDER BY ts_ms DESC 
LIMIT 10;
```

**KurrentDB - Event Streams**
```bash
# List all streams (via HTTP API)
curl http://localhost:2113/streams

# Read a specific stream (example: order-bench-abc123)
curl http://localhost:2113/streams/order-bench-abc123

# Or use browser
# Open: http://localhost:2113/web/index.html#/streams
```

Each test question creates:
- **PostgreSQL**: 1 row in `{domain}.{entity_type}s` with current state in JSONB `data` column
- **PostgreSQL CDC**: 1+ rows in `cdc.cdc_events` with `before_state` and `after_state`
- **KurrentDB**: 1+ events in stream `{entity_type}-{entity_id}` with full event data including `reason` field

## Results

From a 300-question benchmark run (5 domains, 5 tiers, 27 templates):

| Database | Score | Accuracy |
|----------|-------|----------|
| PostgreSQL | 84/300 | 28% |
| PostgreSQL+CDC | 177/300 | 59% |
| KurrentDB | 255/300 | 85% |

**Key Finding**: Event stores excel at Tier 3 (intent), Tier 4 (temporal), and Tier 5 (adversarial) questions because they preserve the *reason* behind each change and the full ordered sequence of events. CRUD databases cannot answer "why", "in what order", or detect false premises — that information is never stored. Adversarial questions with false premises are particularly revealing: only an event store provides enough context for the agent to detect and correct wrong assumptions.

## How It Works

### 1. Semi-Synthetic Data Generation

For each test question, we generate:
- **Current state**: Stored in PostgreSQL
- **Before/after change**: Stored in CDC table
- **Event stream**: Stored in KurrentDB with reason field

```python
# Example: Order cancellation scenario
setup = {
    "current": {"status": "cancelled"},
    "previous": {"status": "processing"},
    "reason": "customer_found_cheaper",  # Only in events!
    "events": ["order.placed", "order.cancelled_by_customer"]
}
```

### 2. Agent Queries Each Database

An AI agent (Claude) queries each database using MCP tools:
- PostgreSQL: SQL queries via `mcp-postgres`
- KurrentDB: Event stream reads via `mcp-kurrentdb`

### 3. Judge Evaluates Answers

A judge compares agent answers against expected values and scores accuracy.

## Project Structure

```
agentic_benchmark/
├── run_benchmark.py      # Main benchmark runner
├── benchmark_queries.py  # Pool-based question generator (22 templates, 5 domains)
├── docker-compose.yml    # Database containers + MCP servers
├── framework/
│   └── agents/           # Claude client, MCP retrieval, Judge
└── datasets/             # Download scripts
```

## Conclusion

When an order status changes from "processing" to "cancelled":
- Current State Only knows: `status = 'cancelled'`
- Change Data Capture knows: `status: 'processing' → 'cancelled'`
- Event Sourcing knows: `OrderCancelledByCustomer(reason="found_cheaper")`

For agentic retrieval, understanding *why* is often more valuable than knowing *what*.
