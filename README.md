# Agentic Retrieval Benchmark

**Thesis: Writing Events Is All You Need**

This benchmark demonstrates that storing data as events rather than current state dramatically improves an AI agent's ability to answer questions about your data. When you write events, you preserve the *intent* and *reason* behind every change—information that CRUD databases lose forever.

## The Problem

Traditional databases store current state. When data changes, the previous value is overwritten. This creates an information gap:

| Question Type | CRUD Database | Event Store |
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

## Three-Tier Benchmark

Questions are organized by difficulty:

| Tier | Difficulty | Question Type | Example |
|------|------------|---------------|---------|
| **Tier 1** | Easy | Current state | "What is the order status?" |
| **Tier 2** | Medium | Change history | "What was the previous status?" |
| **Tier 3** | Hard | Intent/reason | "Why was the status changed?" |

## Databases Compared

| Database | Model | What It Stores |
|----------|-------|----------------|
| **PostgreSQL** | CRUD | Current state only |
| **PostgreSQL+CDC** | Change Data Capture | Before/after values |
| **KurrentDB** | Event Sourcing | Full event stream with intent |

## Pool-Based Dynamic Question Generation

Questions are generated on the fly from **17 templates** across 5 domains. Each template defines pools of possible values:

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

## Results

From a 300-question benchmark run (5 domains, 3 tiers, 17 templates):

| Database | Score | Accuracy |
|----------|-------|----------|
| PostgreSQL | 103/300 | 34% |
| PostgreSQL+CDC | 196/300 | 65% |
| KurrentDB | 293/300 | 98% |

**Key Finding**: Event stores excel at Tier 3 (Hard) questions because they preserve the *reason* behind each change, not just the fact that it changed. CRUD databases cannot answer "why" — that information is never stored.

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
├── benchmark_queries.py  # Pool-based question generator (17 templates, 5 domains)
├── docker-compose.yml    # Database containers + MCP servers
├── framework/
│   └── agents/           # Claude client, MCP retrieval, Judge
├── adapters/             # Dataset adapters
└── datasets/             # Download scripts
```

## Key Insight

**CDC tracks WHAT changed. Events track WHY.**

When an order status changes from "processing" to "cancelled":
- CRUD knows: `status = 'cancelled'`
- CDC knows: `status: 'processing' → 'cancelled'`
- Events know: `OrderCancelledByCustomer(reason="found_cheaper")`

For agentic retrieval, understanding *why* is often more valuable than knowing *what*.