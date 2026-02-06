"""Pool-Based Dynamic Benchmark Query Generation

Templates define pools of values per domain. Questions are generated on the fly
by sampling from pools, so you can produce any number of unique questions.
Expected answers are always derived from the sampled values.

Usage:
    from benchmark_queries import generate_questions
    questions = generate_questions(num=500, seed=42)
    questions = generate_questions(num=100, seed=42, tier=3)
"""

import random

# =============================================================================
# TEMPLATES — 17 templates across 5 domains
# Each template has pools of current/previous/reason values.
# =============================================================================

TEMPLATES = [
    # -------------------------------------------------------------------------
    # OLIST E-COMMERCE (4 templates)
    # -------------------------------------------------------------------------
    {
        "domain": "olist",
        "id": "olist_delivery",
        "name": "Delivery Date Change",
        "entity": "order",
        "field": "delivery_date",
        "current_pool": ["2024-03-20", "2024-04-05", "2024-02-28", "2024-05-12", "2024-06-01", "2024-01-15"],
        "previous_pool": ["2024-03-15", "2024-03-25", "2024-02-20", "2024-04-30", "2024-05-20", "2024-01-10"],
        "reason_pool": [
            "truck_breakdown", "weather_delay", "customs_hold", "warehouse_backlog",
            "carrier_strike", "address_correction", "routing_error", "peak_season_congestion",
        ],
        "events": ["order.placed", "order.shipped", "delivery.delayed"],
        "questions": {
            1: {"template": "What is the current estimated delivery date for order {id}?", "answer_key": "current"},
            2: {"template": "What was the ORIGINAL delivery date for order {id} before it was changed?", "answer_key": "previous", "cdc_limitation": "CRUD only stores current state"},
            3: {"template": "Why was the delivery date changed for order {id}?", "answer_key": "reason", "cdc_limitation": "CDC shows date changed, not the reason"},
        },
    },
    {
        "domain": "olist",
        "id": "olist_cancel",
        "name": "Order Cancellation",
        "entity": "order",
        "field": "status",
        "current_pool": ["cancelled"],
        "previous_pool": ["processing", "confirmed", "shipped", "awaiting_payment"],
        "reason_pool": [
            "customer_found_cheaper", "customer_changed_mind", "item_out_of_stock",
            "fraud_detected", "payment_failed", "delivery_too_slow",
            "wrong_item_ordered", "duplicate_order", "seller_cancelled",
        ],
        "events": ["order.placed", "order.cancelled_by_customer"],
        "questions": {
            1: {"template": "What is the current status of order {id}?", "answer_key": "current"},
            2: {"template": "What was the status of order {id} before it was cancelled?", "answer_key": "previous", "cdc_limitation": "CRUD only has final status"},
            3: {"template": "Why was order {id} cancelled? Was it by customer, system, or fraud?", "answer_key": "reason", "cdc_limitation": "CDC shows status=cancelled, not who initiated or why"},
        },
    },
    {
        "domain": "olist",
        "id": "olist_price",
        "name": "Price Change",
        "entity": "product",
        "field": "price",
        "current_pool": ["149.99", "79.50", "299.00", "34.99", "199.95", "59.00", "449.99"],
        "previous_pool": ["199.99", "129.00", "399.00", "49.99", "249.95", "89.00", "599.99"],
        "reason_pool": [
            "black_friday_sale", "competitor_price_match", "clearance_sale",
            "seasonal_promotion", "bulk_discount_added", "supplier_cost_increase",
            "demand_surge_pricing", "loyalty_program_discount",
        ],
        "events": ["product.created", "product.price_reduced"],
        "questions": {
            1: {"template": "What is the current price of product {id}?", "answer_key": "current"},
            2: {"template": "What was the previous price of product {id}?", "answer_key": "previous", "cdc_limitation": "CRUD only has current price"},
            3: {"template": "Why was the price of product {id} reduced?", "answer_key": "reason", "cdc_limitation": "CDC shows price changed, not business reason"},
        },
    },
    {
        "domain": "olist",
        "id": "olist_review",
        "name": "Review Update",
        "entity": "review",
        "field": "score",
        "current_pool": ["5", "4", "4.5", "3", "1"],
        "previous_pool": ["2", "1", "1.5", "3", "5"],
        "reason_pool": [
            "seller_replaced_item", "refund_received", "issue_resolved_by_support",
            "product_broke_after_use", "updated_after_reuse", "shipping_experience_improved",
            "seller_apologized", "wrong_product_initially",
        ],
        "events": ["review.created", "review.updated_after_resolution"],
        "questions": {
            1: {"template": "What is the current review score for order {id}?", "answer_key": "current"},
            2: {"template": "What was the original review score before it was updated?", "answer_key": "previous", "cdc_limitation": "CRUD only has latest score"},
            3: {"template": "Why did the customer change their review score?", "answer_key": "reason", "cdc_limitation": "CDC shows score changed, not why"},
        },
    },

    # -------------------------------------------------------------------------
    # BERKA BANKING (4 templates)
    # -------------------------------------------------------------------------
    {
        "domain": "berka",
        "id": "berka_balance",
        "name": "Balance Change",
        "entity": "account",
        "field": "balance",
        "current_pool": ["15420.50", "8750.00", "320.75", "45000.00", "1200.30", "92100.00"],
        "previous_pool": ["20420.50", "12500.00", "5320.75", "50000.00", "6200.30", "97100.00"],
        "reason_pool": [
            "transfer_sent_rent", "atm_withdrawal", "wire_transfer_international",
            "loan_payment_deducted", "subscription_charge", "tax_payment",
            "investment_purchase", "utility_bill_autopay", "insurance_premium",
        ],
        "events": ["account.opened", "transfer.sent"],
        "questions": {
            1: {"template": "What is the current balance of account {id}?", "answer_key": "current"},
            2: {"template": "What was the balance of account {id} before the last transaction?", "answer_key": "previous", "cdc_limitation": "CRUD only has current balance"},
            3: {"template": "What type of transaction caused the balance drop on account {id}?", "answer_key": "reason", "cdc_limitation": "CDC shows balance changed, not transaction type"},
        },
    },
    {
        "domain": "berka",
        "id": "berka_loan",
        "name": "Loan Status",
        "entity": "loan",
        "field": "status",
        "current_pool": ["approved", "rejected", "disbursed", "closed"],
        "previous_pool": ["under_review", "pending_documents", "pre_approved", "applied"],
        "reason_pool": [
            "home_purchase", "auto_loan", "education_expenses", "debt_consolidation",
            "business_expansion", "medical_emergency", "home_renovation",
            "insufficient_credit_score", "income_verification_failed",
        ],
        "events": ["loan.applied", "loan.approved"],
        "questions": {
            1: {"template": "What is the current status of loan {id}?", "answer_key": "current"},
            2: {"template": "What was the previous status of loan {id} before the last change?", "answer_key": "previous", "cdc_limitation": "CRUD only has final status"},
            3: {"template": "What was the stated purpose for loan {id}?", "answer_key": "reason", "cdc_limitation": "CDC tracks state changes, not application details"},
        },
    },
    {
        "domain": "berka",
        "id": "berka_card",
        "name": "Card Blocked",
        "entity": "card",
        "field": "status",
        "current_pool": ["blocked", "suspended", "revoked"],
        "previous_pool": ["active", "new", "recently_activated"],
        "reason_pool": [
            "fraud_suspected", "reported_lost", "reported_stolen",
            "suspicious_foreign_transaction", "multiple_failed_pins",
            "account_overdue", "customer_requested_block", "compliance_hold",
        ],
        "events": ["card.issued", "card.blocked_fraud"],
        "questions": {
            1: {"template": "What is the current status of card {id}?", "answer_key": "current"},
            2: {"template": "What was the status of card {id} before it was blocked?", "answer_key": "previous", "cdc_limitation": "CRUD only has current status"},
            3: {"template": "Why was card {id} blocked?", "answer_key": "reason", "cdc_limitation": "CDC shows status=blocked, not the reason"},
        },
    },
    {
        "domain": "berka",
        "id": "berka_overdraft",
        "name": "Overdraft",
        "entity": "account",
        "field": "balance",
        "current_pool": ["-450.00", "-120.50", "-1500.00", "-75.30", "-2200.00"],
        "previous_pool": ["2100.00", "500.00", "3200.00", "150.00", "4500.00"],
        "reason_pool": [
            "auto_payment_mortgage", "unexpected_charge", "direct_debit_insurance",
            "failed_deposit_timing", "double_charge_error", "annual_fee_deducted",
            "standing_order_rent", "margin_call",
        ],
        "events": ["account.opened", "auto_payment.processed"],
        "questions": {
            1: {"template": "Is account {id} currently in overdraft?", "answer_key": "current_bool", "transform": lambda v: "yes"},
            2: {"template": "What was the balance before account {id} went into overdraft?", "answer_key": "previous", "cdc_limitation": "CRUD only has current balance"},
            3: {"template": "What transaction caused account {id} to go into overdraft?", "answer_key": "reason", "cdc_limitation": "CDC shows balance went negative, not the transaction"},
        },
    },

    # -------------------------------------------------------------------------
    # GITHUB (3 templates)
    # -------------------------------------------------------------------------
    {
        "domain": "github",
        "id": "github_pr_closed",
        "name": "PR Closed",
        "entity": "pull_request",
        "field": "state",
        "current_pool": ["closed, not merged"],
        "previous_pool": ["open", "draft", "review_requested"],
        "reason_pool": [
            "superseded_by_pr_456", "approach_abandoned", "duplicate_of_pr_123",
            "requirements_changed", "author_left_project", "stale_no_activity",
            "refactored_differently", "merged_manually",
        ],
        "events": ["pr.opened", "pr.closed_superseded"],
        "questions": {
            1: {"template": "What is the current state of PR {id}?", "answer_key": "current"},
            2: {"template": "What was the state of PR {id} before it was closed?", "answer_key": "previous", "cdc_limitation": "CRUD only has final state"},
            3: {"template": "Why was PR {id} closed without merging?", "answer_key": "reason", "cdc_limitation": "CDC shows state=closed, not the reason"},
        },
    },
    {
        "domain": "github",
        "id": "github_pr_review",
        "name": "PR Review Process",
        "entity": "pull_request",
        "field": "review_state",
        "current_pool": ["approved", "changes_requested", "commented"],
        "previous_pool": ["changes_requested", "pending", "commented", "dismissed"],
        "reason_pool": [
            "3_rounds_of_feedback", "security_concern_resolved", "performance_fix_added",
            "test_coverage_improved", "documentation_updated", "breaking_change_addressed",
            "code_style_fixed", "race_condition_fixed",
        ],
        "events": ["pr.opened", "review.changes_requested", "review.changes_requested", "review.approved"],
        "questions": {
            1: {"template": "What is the current review state of PR {id}?", "answer_key": "current"},
            2: {"template": "What was the previous review state of PR {id}?", "answer_key": "previous", "cdc_limitation": "CRUD only has final review state"},
            3: {"template": "What feedback did reviewers give on PR {id}?", "answer_key": "reason", "cdc_limitation": "CDC shows state changes, not review comments"},
        },
    },
    {
        "domain": "github",
        "id": "github_issue",
        "name": "Issue Resolved",
        "entity": "issue",
        "field": "state",
        "current_pool": ["closed"],
        "previous_pool": ["open", "triaged", "in_progress", "blocked"],
        "reason_pool": [
            "fixed_in_pr_789", "wont_fix_by_design", "duplicate_of_issue_321",
            "resolved_by_upgrade", "cannot_reproduce", "fixed_in_release_v2",
            "workaround_documented", "upstream_bug_fixed",
        ],
        "events": ["issue.opened", "issue.resolved_by_pr"],
        "questions": {
            1: {"template": "What is the current state of issue {id}?", "answer_key": "current"},
            2: {"template": "What was the state of issue {id} before it was closed?", "answer_key": "previous", "cdc_limitation": "CRUD only has final state"},
            3: {"template": "How was issue {id} resolved?", "answer_key": "reason", "cdc_limitation": "CDC shows state=closed, not how resolved"},
        },
    },

    # -------------------------------------------------------------------------
    # BTS AVIATION (3 templates)
    # -------------------------------------------------------------------------
    {
        "domain": "bts",
        "id": "bts_cancelled",
        "name": "Flight Cancelled",
        "entity": "flight",
        "field": "cancelled",
        "current_pool": ["yes"],
        "previous_pool": ["no"],
        "reason_pool": [
            "mechanical_engine_sensor", "weather_thunderstorm", "crew_shortage",
            "air_traffic_control", "bird_strike_inspection", "fuel_system_alert",
            "low_passenger_demand", "security_threat", "volcanic_ash",
        ],
        "events": ["flight.scheduled", "flight.cancelled_mechanical"],
        "questions": {
            1: {"template": "Was flight {id} cancelled?", "answer_key": "current"},
            2: {"template": "When was the cancellation of flight {id} decided relative to departure?", "answer_key": "previous", "cdc_limitation": "CRUD only has cancelled=true"},
            3: {"template": "Why was flight {id} cancelled?", "answer_key": "reason", "cdc_limitation": "CDC shows cancelled=true, not the reason"},
        },
    },
    {
        "domain": "bts",
        "id": "bts_delayed",
        "name": "Flight Delayed",
        "entity": "flight",
        "field": "delay_minutes",
        "current_pool": ["127", "45", "210", "68", "95", "180", "33", "155"],
        "previous_pool": ["0"],
        "reason_pool": [
            "cascading_delays", "late_arriving_aircraft", "gate_congestion",
            "deicing_required", "crew_duty_timeout", "baggage_handling_delay",
            "passenger_medical_emergency", "ramp_equipment_failure",
        ],
        "events": ["flight.scheduled", "flight.delayed_aircraft", "flight.delayed_crew", "flight.delayed_atc"],
        "questions": {
            1: {"template": "How many minutes was flight {id} delayed?", "answer_key": "current"},
            2: {"template": "What was the original delay status of flight {id} before delays accumulated?", "answer_key": "previous", "cdc_limitation": "CRUD only has final delay"},
            3: {"template": "What caused the delays for flight {id}?", "answer_key": "reason", "cdc_limitation": "CDC shows delay changed, not the causes"},
        },
    },
    {
        "domain": "bts",
        "id": "bts_diverted",
        "name": "Flight Diverted",
        "entity": "flight",
        "field": "diverted",
        "current_pool": ["yes, ORD", "yes, DFW", "yes, ATL", "yes, DEN", "yes, LAX", "yes, JFK"],
        "previous_pool": ["no"],
        "reason_pool": [
            "medical_emergency", "severe_weather_destination", "fuel_emergency",
            "hydraulic_failure", "unruly_passenger", "bomb_threat",
            "runway_closure_destination", "wind_shear_warning",
        ],
        "events": ["flight.departed", "flight.diverted_medical"],
        "questions": {
            1: {"template": "Was flight {id} diverted? To where?", "answer_key": "current"},
            2: {"template": "What was the diversion status of flight {id} before diversion?", "answer_key": "previous", "cdc_limitation": "CRUD only has diverted=true"},
            3: {"template": "Why was flight {id} diverted?", "answer_key": "reason", "cdc_limitation": "CDC shows diverted=true, not the reason"},
        },
    },

    # -------------------------------------------------------------------------
    # MOVIELENS (3 templates)
    # -------------------------------------------------------------------------
    {
        "domain": "movielens",
        "id": "movielens_rating",
        "name": "Rating Changed",
        "entity": "rating",
        "field": "rating",
        "current_pool": ["4.5", "5.0", "4.0", "3.5", "1.0", "3.0"],
        "previous_pool": ["2.0", "1.0", "1.5", "2.5", "5.0", "4.0"],
        "reason_pool": [
            "appreciated_on_rewatch", "director_cut_superior", "nostalgia_factor",
            "changed_taste_over_time", "saw_sequel_reappraised", "discussed_in_film_club",
            "product_broke_after_use", "initially_overhyped",
        ],
        "events": ["rating.created", "rating.updated_rewatch"],
        "questions": {
            1: {"template": "What rating did user give to movie {id}?", "answer_key": "current"},
            2: {"template": "What was the original rating for movie {id}?", "answer_key": "previous", "cdc_limitation": "CRUD only has latest rating"},
            3: {"template": "Why did user change their rating for movie {id}?", "answer_key": "reason", "cdc_limitation": "CDC shows rating changed, not why"},
        },
    },
    {
        "domain": "movielens",
        "id": "movielens_tags",
        "name": "Tags Added",
        "entity": "movie",
        "field": "tags",
        "current_pool": [
            "mind-bending, must-see, Nolan",
            "dark comedy, underrated, indie",
            "visually stunning, Villeneuve, sci-fi",
            "feel-good, family, animated",
            "thriller, twist ending, Fincher",
            "classic, Kubrick, masterpiece",
        ],
        "previous_pool": ["(none)"],
        "reason_pool": [
            "recommending_to_friend", "building_watchlist", "organizing_collection",
            "participating_in_challenge", "writing_review", "curating_genre_list",
            "inspired_by_discussion", "creating_top_10_list",
        ],
        "events": ["tag.added", "tag.added", "tag.added_for_recommendation"],
        "questions": {
            1: {"template": "What tags does movie {id} have?", "answer_key": "current"},
            2: {"template": "Were there any tags on movie {id} before the current ones were added?", "answer_key": "previous", "cdc_limitation": "CRUD doesn't track order"},
            3: {"template": "What prompted user to add tags to movie {id}?", "answer_key": "reason", "cdc_limitation": "CDC shows tag added, not context"},
        },
    },
    {
        "domain": "movielens",
        "id": "movielens_watchlist",
        "name": "Watchlist Change",
        "entity": "watchlist",
        "field": "on_watchlist",
        "current_pool": ["no"],
        "previous_pool": ["yes, was added then removed"],
        "reason_pool": [
            "watched_and_rated", "no_longer_interested", "already_seen_elsewhere",
            "removed_after_bad_reviews", "list_cleanup", "switched_to_different_list",
            "movie_unavailable_on_platform", "friend_spoiled_ending",
        ],
        "events": ["watchlist.added", "watchlist.removed_watched"],
        "questions": {
            1: {"template": "Is movie {id} on user's watchlist?", "answer_key": "current"},
            2: {"template": "Was movie {id} ever on user's watchlist?", "answer_key": "previous", "cdc_limitation": "CRUD only has current state"},
            3: {"template": "Why was movie {id} removed from watchlist?", "answer_key": "reason", "cdc_limitation": "CDC shows deleted, not why"},
        },
    },
]


# =============================================================================
# QUESTION GENERATION
# =============================================================================

def generate_questions(num: int = 51, seed: int = 42, tier: int = None) -> list[dict]:
    """Generate `num` benchmark questions by sampling from template pools.

    Args:
        num:  Number of questions to generate.
        seed: Random seed for reproducibility.
        tier: If set (1, 2, or 3), only generate questions of that tier.

    Returns:
        List of question dicts matching the existing interface:
        {domain, scenario_id, scenario_name, entity, tier, question,
         expected, cdc_limitation, setup}
    """
    rng = random.Random(seed)
    tiers = [tier] if tier else [1, 2, 3]
    questions = []

    for i in range(num):
        # Pick random template and tier
        tmpl = rng.choice(TEMPLATES)
        t = rng.choice(tiers)

        # Sample values from pools (ensure current != previous)
        current_val = rng.choice(tmpl["current_pool"])
        previous_val = rng.choice(tmpl["previous_pool"])
        # If pools overlap, resample previous until it differs (or exhaust attempts)
        for _ in range(10):
            if previous_val != current_val:
                break
            previous_val = rng.choice(tmpl["previous_pool"])
        reason_val = rng.choice(tmpl["reason_pool"])

        # Determine expected answer based on tier
        q_def = tmpl["questions"][t]
        answer_key = q_def["answer_key"]
        if answer_key == "current":
            expected = current_val
        elif answer_key == "previous":
            expected = previous_val
        elif answer_key == "reason":
            expected = reason_val
        elif answer_key == "current_bool":
            # Special case: overdraft "yes" regardless of current value
            expected = q_def["transform"](current_val)
        else:
            expected = current_val

        # Build setup dict (used by run_benchmark to populate databases)
        setup = {
            "current": {tmpl["field"]: current_val},
            "previous": {tmpl["field"]: previous_val},
            "reason": reason_val,
            "events": tmpl["events"],
        }

        questions.append({
            "domain": tmpl["domain"],
            "scenario_id": tmpl["id"],
            "scenario_name": tmpl["name"],
            "entity": tmpl["entity"],
            "tier": t,
            "question": q_def["template"],
            "expected": str(expected),
            "cdc_limitation": q_def.get("cdc_limitation"),
            "setup": setup,
        })

    return questions


def get_all_questions() -> list[dict]:
    """Backward-compatible: returns 51 questions (seed=42), same as before."""
    return generate_questions(51, seed=42)


def get_questions_by_tier(tier: int) -> list[dict]:
    """Get questions for a specific tier."""
    return generate_questions(51, seed=42, tier=tier)


# =============================================================================
# SUMMARY
# =============================================================================

def print_summary():
    """Print summary of templates and pool sizes."""
    print("=" * 70)
    print("POOL-BASED BENCHMARK QUERY TEMPLATES")
    print("=" * 70)
    print()
    print("Tier 1 (Easy):   Current state queries")
    print("Tier 2 (Medium): Change history queries")
    print("Tier 3 (Hard):   Intent/reason queries")
    print()

    domains = {}
    for tmpl in TEMPLATES:
        domains.setdefault(tmpl["domain"], []).append(tmpl)

    total_templates = 0
    total_pool_combos = 0
    for domain, tmpls in domains.items():
        print(f"\n{domain.upper()} ({len(tmpls)} templates)")
        print("-" * 40)
        for tmpl in tmpls:
            c = len(tmpl["current_pool"])
            p = len(tmpl["previous_pool"])
            r = len(tmpl["reason_pool"])
            combos = c * p * r * 3  # 3 tiers
            total_pool_combos += combos
            total_templates += 1
            print(f"  {tmpl['name']}")
            print(f"    Pools: {c} current x {p} previous x {r} reasons = {combos} combos (x3 tiers)")

    print()
    print("=" * 70)
    print(f"Total: {total_templates} templates, ~{total_pool_combos} unique question variants")
    print()
    print("Usage:")
    print("  generate_questions(10)           # 10 random questions")
    print("  generate_questions(500, seed=99)  # 500 questions, different seed")
    print("  generate_questions(100, tier=3)   # 100 Tier 3 (Hard) only")


if __name__ == "__main__":
    print_summary()
    print()
    print("Sample (10 questions, seed=42):")
    print("-" * 70)
    for q in generate_questions(10, seed=42):
        print(f"  T{q['tier']} {q['domain']:10} {q['question'][:55]:55}  -> {q['expected']}")
