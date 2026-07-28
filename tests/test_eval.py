import pytest
import asyncio
from typing import Dict, Any

from finsentry.tools import (
    scan_receipt_for_subscription,
    request_subscription_cancellation,
    flag_unauthorized_subscription_charge
)
from finsentry.logger import redact_value
from finsentry.memory import compact_history_async
from finsentry.agent import CoordinatorAgent

# ==================== GOLDEN DATASET (Rubric 5.1) ====================
GOLDEN_DATASET_RECEIPTS = [
    {
        "input": "Thank you for choosing Spotify Premium. Monthly charge: $14.99. Billing date: 2026-07-25.",
        "expected_vendor": "Spotify",
        "expected_amount": 14.99,
        "is_subscription": True
    },
    {
        "input": "Adobe Systems Invoice: Adobe Creative Cloud Suite. Total: $54.99. Paid via VISA.",
        "expected_vendor": "Adobe",
        "expected_amount": 54.99,
        "is_subscription": True
    },
    {
        "input": "Grocery Mart Receipt. Bread $3.50, Milk $4.20. Total: $7.70. Thank you!",
        "expected_vendor": "Unknown Vendor",
        "expected_amount": 0.0,
        "is_subscription": False
    }
]

# 1. Test Receipt Parsing against Golden Dataset
@pytest.mark.parametrize("test_case", GOLDEN_DATASET_RECEIPTS)
def test_receipt_parsing_golden_dataset(test_case: Dict[str, Any]):
    result = scan_receipt_for_subscription(test_case["input"])
    assert result["status"] == "success"
    assert result["vendor"] == test_case["expected_vendor"]
    assert result["amount"] == test_case["expected_amount"]
    assert result["detected_subscription"] == test_case["is_subscription"]


# 2. Test Human-in-the-Loop Hooks (Rubric 3.4)
def test_human_in_the_loop_cancellation_threshold():
    # Low-cost cancellation should execute directly without HITL
    low_cost_res = request_subscription_cancellation("sub-netflix", "user@example.com")
    assert low_cost_res["status"] == "success"
    assert "Successfully sent cancellation" in low_cost_res["message"]
    assert "approval_token" not in low_cost_res

    # High-cost cancellation (Adobe is $54.99 >= $20 threshold) should suspend and request HITL approval
    high_cost_res = request_subscription_cancellation("sub-adobe", "user@example.com")
    assert high_cost_res["status"] == "pending_approval"
    assert "approval_token" in high_cost_res
    assert "ACTION REQUIRED" in high_cost_res["message"]


# 3. Test PII Redaction Guardrail (Rubric 4.4)
def test_pii_redaction_scrubbing():
    raw_sensitive_log = {
        "user_email": "clarissa.audrey@google.com",
        "billing_message": "User checked out using card 4111-2222-3333-4444. SSN: 000-12-3456."
    }
    
    redacted_log = redact_value(raw_sensitive_log)
    
    # Assert email is scrubbed
    assert redacted_log["user_email"] == "[REDACTED_EMAIL]"
    
    # Assert credit card and SSN are scrubbed
    message = redacted_log["billing_message"]
    assert "4111-2222-3333-4444" not in message
    assert "000-12-3456" not in message
    assert "[REDACTED_CREDIT_CARD]" in message
    assert "[REDACTED_SSN]" in message


# 4. Test History Compaction (Rubric 2.2)
@pytest.mark.asyncio
async def test_history_compaction():
    # Build bloated chat history (9 turns total)
    bloated_history = [
        {"role": "system", "content": "You are a helpful concierge."},
        {"role": "user", "content": "Hi"},
        {"role": "model", "content": "Hello! How can I assist you with your subscriptions today?"},
        {"role": "user", "content": "I have Netflix"},
        {"role": "model", "content": "I have tracked Netflix subscription."},
        {"role": "user", "content": "And Spotify"},
        {"role": "model", "content": "Added Spotify as well."},
        {"role": "user", "content": "Can you check my balance?"},
        {"role": "model", "content": "Sure, looking that up."}
    ]

    compacted = await compact_history_async(bloated_history, None)
    
    # Assert history length has shrunk
    assert len(compacted) < len(bloated_history)
    # Check that compaction summary is injected
    assert any("[History Compaction Summary]" in turn["content"] for turn in compacted if turn["role"] == "system")
    # Verify last 4 turns were preserved
    assert compacted[-1]["content"] == "Sure, looking that up."
    assert compacted[-2]["content"] == "Can you check my balance?"


# 5. Test Integration Flow using Local Mock
@pytest.mark.asyncio
async def test_agent_integration_flow():
    agent = CoordinatorAgent(session_id="test-session-999")
    
    # Send a receipt analysis request
    receipt_prompt = "analyze receipt invoice: Spotify $14.99 monthly"
    response = await agent.run(receipt_prompt)
    
    assert "Spotify" in response
    assert "$14.99" in response
    
    # Send a cancellation request triggering HITL
    cancel_prompt = "cancel subscription Adobe"
    response_2 = await agent.run(cancel_prompt)
    assert "ACTION REQUIRED" in response_2
    assert "token" in response_2
