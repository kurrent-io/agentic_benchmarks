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
    # -------------------------------------------------------------------------
    # TIER 4 — TEMPORAL QUERIES (cross-event reasoning about time and order)
    # These questions require reading multiple events and reasoning about
    # their sequence, timing gaps, or causal ordering — not just a single fact.
    # -------------------------------------------------------------------------
    {
        "domain": "olist",
        "id": "olist_temporal_order",
        "name": "Order Lifecycle Timing",
        "entity": "order",
        "field": "status",
        "tier4_only": True,
        "current_pool": ["delivered"],
        "previous_pool": ["processing"],
        "reason_pool": ["standard_fulfillment"],
        "events": [
            {"type": "order.placed", "offset_hours": 0},
            {"type": "order.confirmed", "offset_hours": 2},
            {"type": "order.shipped", "offset_hours": 48},
            {"type": "delivery.delayed", "offset_hours": 96},
            {"type": "order.delivered", "offset_hours": 168},
        ],
        "temporal_pool": [
            {"question": "How long did it take from order placement to delivery for order {id}?", "answer_fn": "total_duration"},
            {"question": "What was the longest gap between consecutive events for order {id}?", "answer_fn": "longest_gap"},
            {"question": "How many status changes did order {id} go through before delivery?", "answer_fn": "num_events"},
            {"question": "Did any delay occur after shipping for order {id}? How long after shipping?", "answer_fn": "delay_after_ship"},
        ],
    },
    {
        "domain": "berka",
        "id": "berka_temporal_account",
        "name": "Account Activity Sequence",
        "entity": "account",
        "field": "balance",
        "tier4_only": True,
        "current_pool": ["15420.50"],
        "previous_pool": ["20000.00"],
        "reason_pool": ["mixed_transactions"],
        "events": [
            {"type": "account.opened", "offset_hours": 0},
            {"type": "deposit.received", "offset_hours": 24},
            {"type": "transfer.sent", "offset_hours": 72},
            {"type": "fee.charged", "offset_hours": 73},
            {"type": "deposit.received", "offset_hours": 168},
            {"type": "transfer.sent", "offset_hours": 240},
        ],
        "temporal_pool": [
            {"question": "How many transactions occurred on account {id} in the first 3 days?", "answer_fn": "events_in_first_n_hours", "param": 72},
            {"question": "What was the sequence of transaction types on account {id}?", "answer_fn": "event_sequence"},
            {"question": "Was there a fee charged within 24 hours of a transfer on account {id}?", "answer_fn": "fee_after_transfer"},
            {"question": "How many deposits vs withdrawals occurred on account {id}?", "answer_fn": "deposit_vs_withdrawal"},
        ],
    },
    {
        "domain": "github",
        "id": "github_temporal_pr",
        "name": "PR Review Timeline",
        "entity": "pull_request",
        "field": "state",
        "tier4_only": True,
        "current_pool": ["merged"],
        "previous_pool": ["open"],
        "reason_pool": ["review_process"],
        "events": [
            {"type": "pr.opened", "offset_hours": 0},
            {"type": "review.changes_requested", "offset_hours": 12},
            {"type": "pr.updated", "offset_hours": 36},
            {"type": "review.changes_requested", "offset_hours": 48},
            {"type": "pr.updated", "offset_hours": 72},
            {"type": "review.approved", "offset_hours": 84},
            {"type": "pr.merged", "offset_hours": 85},
        ],
        "temporal_pool": [
            {"question": "How many rounds of review did PR {id} go through before approval?", "answer_fn": "review_rounds"},
            {"question": "How long was PR {id} open before it was merged?", "answer_fn": "total_duration"},
            {"question": "What was the time between the last update and approval for PR {id}?", "answer_fn": "last_update_to_approval"},
            {"question": "How many times were changes requested on PR {id}?", "answer_fn": "changes_requested_count"},
        ],
    },
    {
        "domain": "bts",
        "id": "bts_temporal_flight",
        "name": "Flight Delay Accumulation",
        "entity": "flight",
        "field": "delay_minutes",
        "tier4_only": True,
        "current_pool": ["180"],
        "previous_pool": ["0"],
        "reason_pool": ["cascading_delays"],
        "events": [
            {"type": "flight.scheduled", "offset_hours": 0},
            {"type": "flight.delayed_weather", "offset_hours": -2, "delay_added": 45},
            {"type": "flight.delayed_crew", "offset_hours": -1, "delay_added": 60},
            {"type": "flight.delayed_atc", "offset_hours": 0, "delay_added": 75},
            {"type": "flight.departed", "offset_hours": 3},
        ],
        "temporal_pool": [
            {"question": "How many separate delays did flight {id} accumulate before departure?", "answer_fn": "num_delays"},
            {"question": "What was the first cause of delay for flight {id}?", "answer_fn": "first_delay_cause"},
            {"question": "Did the delays for flight {id} get worse over time or were they resolved?", "answer_fn": "delay_trend"},
            {"question": "How much total delay accumulated for flight {id} across all causes?", "answer_fn": "total_delay"},
        ],
    },
    # -------------------------------------------------------------------------
    # TIER 5 — ADVERSARIAL QUESTIONS (False Premise Detection)
    # These questions contain a false assumption. The correct answer requires
    # the agent to detect and correct the false premise rather than blindly
    # answering.
    # -------------------------------------------------------------------------
    {
        "domain": "olist",
        "id": "olist_adversarial_cancel",
        "name": "False Premise: Order Cancellation",
        "entity": "order",
        "field": "status",
        "tier5_only": True,
        "current_pool": ["cancelled"],
        "previous_pool": ["processing", "confirmed", "shipped"],
        "reason_pool": [
            "customer_found_cheaper", "customer_changed_mind", "wrong_item_ordered",
            "duplicate_order", "delivery_too_slow",
        ],
        "events": ["order.placed", "order.cancelled_by_customer"],
        "adversarial_pool": [
            {
                "question": "Order {id} was cancelled by the system due to fraud detection. What fraud indicators were found?",
                "false_premise": "cancelled by the system due to fraud detection",
                "reality": "The order was cancelled by the customer, not the system. Reason: {reason}",
            },
            {
                "question": "After the system automatically cancelled order {id}, was the customer notified?",
                "false_premise": "system automatically cancelled",
                "reality": "The order was cancelled by the customer, not automatically by the system. Reason: {reason}",
            },
            {
                "question": "Order {id} was cancelled because the item was out of stock. When will it be restocked?",
                "false_premise": "cancelled because item was out of stock",
                "reality": "The order was cancelled by the customer, not due to stock issues. Reason: {reason}",
            },
        ],
    },
    {
        "domain": "berka",
        "id": "berka_adversarial_overdraft",
        "name": "False Premise: Overdraft Cause",
        "entity": "account",
        "field": "balance",
        "tier5_only": True,
        "current_pool": ["-450.00", "-120.50", "-1500.00", "-75.30"],
        "previous_pool": ["2100.00", "500.00", "3200.00", "150.00"],
        "reason_pool": [
            "transfer_sent_rent", "wire_transfer_international",
            "standing_order_rent", "auto_payment_mortgage",
        ],
        "events": ["account.opened", "deposit.received", "transfer.sent"],
        "adversarial_pool": [
            {
                "question": "A deposit into account {id} caused it to go into overdraft. How much was the deposit?",
                "false_premise": "a deposit caused the overdraft",
                "reality": "A deposit cannot cause an overdraft. The overdraft was caused by a transfer/payment: {reason}. Balance went from {previous} to {current}",
            },
            {
                "question": "Account {id} went into overdraft after receiving a large incoming transfer. Who sent the transfer?",
                "false_premise": "overdraft after receiving incoming transfer",
                "reality": "An incoming transfer cannot cause an overdraft. The overdraft was caused by an outgoing transaction: {reason}. Balance went from {previous} to {current}",
            },
            {
                "question": "The interest payment on account {id} caused it to go negative. What was the interest rate?",
                "false_premise": "interest payment caused overdraft",
                "reality": "The overdraft was not caused by an interest payment. It was caused by: {reason}. Balance went from {previous} to {current}",
            },
        ],
    },
    {
        "domain": "github",
        "id": "github_adversarial_pr",
        "name": "False Premise: PR Merged",
        "entity": "pull_request",
        "field": "state",
        "tier5_only": True,
        "current_pool": ["closed, not merged"],
        "previous_pool": ["open", "draft", "review_requested"],
        "reason_pool": [
            "superseded_by_pr_456", "approach_abandoned", "duplicate_of_pr_123",
            "requirements_changed", "stale_no_activity",
        ],
        "events": ["pr.opened", "pr.closed_superseded"],
        "adversarial_pool": [
            {
                "question": "When was PR {id} merged into the main branch?",
                "false_premise": "PR was merged",
                "reality": "The PR was NOT merged. It was closed without merging. Reason: {reason}",
            },
            {
                "question": "After PR {id} was merged, did the CI pipeline pass on main?",
                "false_premise": "PR was merged",
                "reality": "The PR was never merged. It was closed without merging. Reason: {reason}",
            },
            {
                "question": "Which commit from PR {id} caused the regression after it was merged?",
                "false_premise": "PR was merged and caused regression",
                "reality": "The PR was not merged — it was closed without merging. Reason: {reason}. It could not have caused any regression.",
            },
        ],
    },
    {
        "domain": "bts",
        "id": "bts_adversarial_delay",
        "name": "False Premise: Flight Delayed",
        "entity": "flight",
        "field": "cancelled",
        "tier5_only": True,
        "current_pool": ["yes"],
        "previous_pool": ["no"],
        "reason_pool": [
            "mechanical_engine_sensor", "weather_thunderstorm", "crew_shortage",
            "air_traffic_control", "fuel_system_alert",
        ],
        "events": ["flight.scheduled", "flight.cancelled_mechanical"],
        "adversarial_pool": [
            {
                "question": "How many minutes was flight {id} delayed before it finally departed?",
                "false_premise": "flight was delayed before departure",
                "reality": "The flight was not delayed — it was cancelled entirely. It never departed. Cancellation reason: {reason}",
            },
            {
                "question": "Flight {id} departed 2 hours late. What caused the delay?",
                "false_premise": "flight departed late",
                "reality": "The flight never departed. It was cancelled, not delayed. Cancellation reason: {reason}",
            },
            {
                "question": "After the delay, did flight {id} make up time en route?",
                "false_premise": "flight was delayed but eventually flew",
                "reality": "The flight was cancelled and never flew. There was no delay or en-route time. Cancellation reason: {reason}",
            },
        ],
    },
    {
        "domain": "movielens",
        "id": "movielens_adversarial_rating",
        "name": "False Premise: Rating Lowered",
        "entity": "rating",
        "field": "rating",
        "tier5_only": True,
        "current_pool": ["4.5", "5.0", "4.0"],
        "previous_pool": ["2.0", "1.0", "1.5"],
        "reason_pool": [
            "appreciated_on_rewatch", "director_cut_superior", "nostalgia_factor",
            "discussed_in_film_club", "saw_sequel_reappraised",
        ],
        "events": ["rating.created", "rating.updated_rewatch"],
        "adversarial_pool": [
            {
                "question": "The user lowered their rating for movie {id}. What disappointed them?",
                "false_premise": "user lowered their rating",
                "reality": "The user actually INCREASED their rating from {previous} to {current}, not lowered it. Reason for increase: {reason}",
            },
            {
                "question": "After the user gave movie {id} a negative review, did they remove it from their watchlist?",
                "false_premise": "user gave a negative review",
                "reality": "The user's rating is {current} (up from {previous}), which is a positive rating, not a negative review. Reason: {reason}",
            },
            {
                "question": "Why did the user rate movie {id} only 1 star?",
                "false_premise": "user rated 1 star",
                "reality": "The user did not rate the movie as 1 star. Current rating is {current} (changed from {previous}). Reason for change: {reason}",
            },
        ],
    },

    {
        "domain": "movielens",
        "id": "movielens_temporal_rating",
        "name": "Rating Evolution",
        "entity": "rating",
        "field": "rating",
        "tier4_only": True,
        "current_pool": ["4.5"],
        "previous_pool": ["3.0"],
        "reason_pool": ["taste_evolution"],
        "events": [
            {"type": "rating.created", "offset_hours": 0, "value": "3.0"},
            {"type": "rating.updated", "offset_hours": 720, "value": "2.0", "reason": "disappointing_on_reflection"},
            {"type": "rating.updated", "offset_hours": 2160, "value": "4.0", "reason": "appreciated_after_sequel"},
            {"type": "rating.updated", "offset_hours": 4320, "value": "4.5", "reason": "discussed_in_film_club"},
        ],
        "temporal_pool": [
            {"question": "How many times did user change their rating for movie {id}?", "answer_fn": "num_changes"},
            {"question": "Did the rating for movie {id} trend upward or downward over time?", "answer_fn": "rating_trend"},
            {"question": "What was the lowest rating movie {id} ever received from this user?", "answer_fn": "min_rating"},
            {"question": "How long between the first and last rating change for movie {id}?", "answer_fn": "time_span"},
        ],
    },
]


# =============================================================================
# TEMPORAL ANSWER COMPUTATION
# =============================================================================

def _compute_temporal_answer(answer_fn: str, events: list[dict], param=None) -> str:
    """Compute the expected answer for a temporal question based on event sequence."""
    if answer_fn == "total_duration":
        first = events[0]["offset_hours"]
        last = events[-1]["offset_hours"]
        hours = last - first
        if hours >= 24:
            return f"{hours // 24} days ({hours} hours)"
        return f"{hours} hours"

    elif answer_fn == "longest_gap":
        max_gap = 0
        max_pair = ("", "")
        for i in range(1, len(events)):
            gap = events[i]["offset_hours"] - events[i-1]["offset_hours"]
            if gap > max_gap:
                max_gap = gap
                max_pair = (events[i-1]["type"], events[i]["type"])
        if max_gap >= 24:
            return f"{max_gap // 24} days ({max_gap} hours) between {max_pair[0]} and {max_pair[1]}"
        return f"{max_gap} hours between {max_pair[0]} and {max_pair[1]}"

    elif answer_fn == "num_events":
        return str(len(events))

    elif answer_fn == "delay_after_ship":
        ship_idx = next((i for i, e in enumerate(events) if "shipped" in e["type"]), None)
        delay_idx = next((i for i, e in enumerate(events) if "delay" in e["type"] and i > (ship_idx or -1)), None)
        if ship_idx is not None and delay_idx is not None:
            gap = events[delay_idx]["offset_hours"] - events[ship_idx]["offset_hours"]
            return f"Yes, {gap} hours after shipping"
        return "No delay after shipping"

    elif answer_fn == "events_in_first_n_hours":
        count = sum(1 for e in events if e["offset_hours"] <= (param or 72))
        return str(count)

    elif answer_fn == "event_sequence":
        return " -> ".join(e["type"] for e in events)

    elif answer_fn == "fee_after_transfer":
        for i in range(1, len(events)):
            if "fee" in events[i]["type"]:
                prev = events[i-1]
                if "transfer" in prev["type"]:
                    gap = events[i]["offset_hours"] - prev["offset_hours"]
                    return f"Yes, fee charged {gap} hours after transfer"
        return "No"

    elif answer_fn == "deposit_vs_withdrawal":
        deposits = sum(1 for e in events if "deposit" in e["type"])
        withdrawals = sum(1 for e in events if "transfer" in e["type"] or "fee" in e["type"])
        return f"{deposits} deposits, {withdrawals} withdrawals/fees"

    elif answer_fn == "review_rounds":
        return str(sum(1 for e in events if "changes_requested" in e["type"]))

    elif answer_fn == "last_update_to_approval":
        updates = [e for e in events if "updated" in e["type"]]
        approvals = [e for e in events if "approved" in e["type"]]
        if updates and approvals:
            gap = approvals[-1]["offset_hours"] - updates[-1]["offset_hours"]
            return f"{gap} hours"
        return "unknown"

    elif answer_fn == "changes_requested_count":
        return str(sum(1 for e in events if "changes_requested" in e["type"]))

    elif answer_fn == "num_delays":
        return str(sum(1 for e in events if "delayed" in e["type"]))

    elif answer_fn == "first_delay_cause":
        for e in events:
            if "delayed" in e["type"]:
                cause = e["type"].split("delayed_")[-1] if "delayed_" in e["type"] else "unknown"
                return cause
        return "no delays"

    elif answer_fn == "delay_trend":
        delays = [e for e in events if "delayed" in e["type"]]
        if len(delays) >= 2:
            added = [e.get("delay_added", 0) for e in delays]
            if added[-1] > added[0]:
                return "Delays got worse over time"
            elif added[-1] < added[0]:
                return "Delays improved over time"
        return "Single delay event"

    elif answer_fn == "total_delay":
        total = sum(e.get("delay_added", 0) for e in events if "delayed" in e["type"])
        return f"{total} minutes"

    elif answer_fn == "num_changes":
        return str(sum(1 for e in events if "updated" in e["type"]))

    elif answer_fn == "rating_trend":
        values = [float(e["value"]) for e in events if "value" in e]
        if len(values) >= 2:
            if values[-1] > values[0]:
                return f"Upward trend: {' -> '.join(str(v) for v in values)}"
            elif values[-1] < values[0]:
                return f"Downward trend: {' -> '.join(str(v) for v in values)}"
        return "Flat"

    elif answer_fn == "min_rating":
        values = [float(e["value"]) for e in events if "value" in e]
        return str(min(values)) if values else "unknown"

    elif answer_fn == "time_span":
        updates = [e for e in events if "value" in e]
        if len(updates) >= 2:
            hours = updates[-1]["offset_hours"] - updates[0]["offset_hours"]
            days = hours // 24
            return f"{days} days ({hours} hours)"
        return "no changes"

    return "unknown"


# =============================================================================
# QUESTION GENERATION
# =============================================================================

def generate_questions(num: int = 51, seed: int = 42, tier: int = None) -> list[dict]:
    """Generate `num` benchmark questions by sampling from template pools.

    Args:
        num:  Number of questions to generate.
        seed: Random seed for reproducibility.
        tier: If set (1, 2, 3, 4, or 5), only generate questions of that tier.

    Returns:
        List of question dicts matching the existing interface:
        {domain, scenario_id, scenario_name, entity, tier, question,
         expected, cdc_limitation, setup}
    """
    rng = random.Random(seed)
    tiers = [tier] if tier else [1, 2, 3, 4, 5]

    # Split templates by type
    standard_templates = [t for t in TEMPLATES if not t.get("tier4_only") and not t.get("tier5_only")]
    temporal_templates = [t for t in TEMPLATES if t.get("tier4_only")]
    adversarial_templates = [t for t in TEMPLATES if t.get("tier5_only")]

    questions = []

    for i in range(num):
        t = rng.choice(tiers)

        if t == 5:
            # Tier 5: adversarial questions — pick from adversarial templates
            if not adversarial_templates:
                continue
            tmpl = rng.choice(adversarial_templates)
            adv_q = rng.choice(tmpl["adversarial_pool"])

            # Sample values from pools
            current_val = rng.choice(tmpl["current_pool"])
            previous_val = rng.choice(tmpl["previous_pool"])
            reason_val = rng.choice(tmpl["reason_pool"])

            # The expected answer is the correction of the false premise
            expected = adv_q["reality"].format(
                reason=reason_val,
                current=current_val,
                previous=previous_val,
            )

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
                "tier": 5,
                "question": adv_q["question"],
                "expected": expected,
                "false_premise": adv_q["false_premise"],
                "cdc_limitation": "CDC may show what changed but lacks context to detect false premises",
                "setup": setup,
            })
        elif t == 4:
            # Tier 4: temporal questions — pick from temporal templates
            if not temporal_templates:
                continue
            tmpl = rng.choice(temporal_templates)
            temporal_q = rng.choice(tmpl["temporal_pool"])

            # Compute expected answer from event sequence
            expected = _compute_temporal_answer(
                temporal_q["answer_fn"],
                tmpl["events"],
                param=temporal_q.get("param"),
            )

            # Build setup with full event sequence for temporal
            setup = {
                "current": {tmpl["field"]: tmpl["current_pool"][0]},
                "previous": {tmpl["field"]: tmpl["previous_pool"][0]},
                "reason": tmpl["reason_pool"][0],
                "events": tmpl["events"],  # list of dicts with type + offset_hours
                "temporal": True,
            }

            questions.append({
                "domain": tmpl["domain"],
                "scenario_id": tmpl["id"],
                "scenario_name": tmpl["name"],
                "entity": tmpl["entity"],
                "tier": 4,
                "question": temporal_q["question"],
                "expected": str(expected),
                "cdc_limitation": "CDC only tracks individual field changes, not cross-event temporal reasoning",
                "setup": setup,
            })
        else:
            # Tiers 1-3: standard questions
            tmpl = rng.choice(standard_templates)

            # Sample values from pools (ensure current != previous)
            current_val = rng.choice(tmpl["current_pool"])
            previous_val = rng.choice(tmpl["previous_pool"])
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
                expected = q_def["transform"](current_val)
            else:
                expected = current_val

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
    print("Tier 1 (Easy):        Current state queries")
    print("Tier 2 (Medium):      Change history queries")
    print("Tier 3 (Hard):        Intent/reason queries")
    print("Tier 4 (Temporal):    Cross-event time and order reasoning")
    print("Tier 5 (Adversarial): False premise detection")
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
