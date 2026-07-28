import uuid
from typing import Dict, Any
from pydantic import BaseModel, Field, ValidationError

# Explicit JSON Schemas using Pydantic Models for LLM input validation

class ReceiptScanInput(BaseModel):
    raw_text: str = Field(
        ...,
        description="The raw unformatted text content extracted from the receipt or email statement. Must not be empty."
    )

class SubscriptionCancellationInput(BaseModel):
    subscription_id: str = Field(
        ...,
        description="The unique database UUID of the subscription to cancel."
    )
    user_email_associated: str = Field(
        ...,
        description="The user's registered email address associated with the subscription service."
    )
    reason: str = Field(
        "No longer needed",
        description="The cancellation reason provided to the service provider."
    )

class UnauthorizedChargeInput(BaseModel):
    subscription_name: str = Field(
        ...,
        description="The official brand name of the subscription service provider (e.g., Netflix, Adobe)."
    )
    amount_in_usd: float = Field(
        ...,
        description="The total charge amount in USD. Must be a positive decimal number."
    )
    transaction_date: str = Field(
        ...,
        description="The ISO 8601 formatted date of the transaction (YYYY-MM-DD)."
    )

# ----------------- Tool Implementations -----------------

# Tool implementations with specific naming and descriptive docstrings

def scan_receipt_for_subscription(raw_text: str) -> Dict[str, Any]:
    """Parses raw receipt or statement text to detect candidate recurring subscription details.
    
    Use this tool when the user uploads receipt text and wants to index recurring costs.
    
    Args:
        raw_text: The unformatted text content of the receipt or invoice.
        
    Returns:
        A dictionary containing the parsed transaction details (vendor, cost, date)
        or a detailed error payload with recovery instructions if parsing fails.
    """
    # Schema validation
    try:
        inputs = ReceiptScanInput(raw_text=raw_text)
    except ValidationError as err:
        # Guided Error Handling
        return {
            "status": "error",
            "error_type": "ValidationError",
            "message": str(err),
            "recovery_instruction": "The raw receipt text provided was empty or invalid. Please check the text source and re-run with valid text content."
        }

    # Simulate basic mock extraction logic
    text = inputs.raw_text.lower()
    if not text.strip():
        return {
            "status": "error",
            "error_type": "EmptyContentError",
            "message": "Raw text is empty or contains only whitespace.",
            "recovery_instruction": "Please ask the user to provide a valid invoice, billing description, or transaction text."
        }

    # Quick heuristic parser
    vendor = "Unknown Vendor"
    amount = 0.0
    date = "2026-07-28" # default
    
    # Vendors matching
    for possible_vendor in ["netflix", "spotify", "adobe", "chatgpt", "dropbox", "aws"]:
        if possible_vendor in text:
            vendor = possible_vendor.title()
            break
            
    # Simple regex-free parsing for cost
    words = text.split()
    for w in words:
        clean_w = w.strip(".,;:?!")
        if clean_w.startswith("$"):
            try:
                amount = float(clean_w.replace("$", ""))
                break
            except ValueError:
                continue
        elif "usd" in w:
            idx = words.index(w)
            if idx > 0:
                try:
                    amount = float(words[idx-1])
                    break
                except ValueError:
                    continue

    return {
        "status": "success",
        "vendor": vendor,
        "amount": amount if vendor != "Unknown Vendor" else 0.0,
        "date": date,
        "detected_subscription": amount > 0 and vendor != "Unknown Vendor"
    }


def flag_unauthorized_subscription_charge(
    subscription_name: str, 
    amount_in_usd: float, 
    transaction_date: str
) -> Dict[str, Any]:
    """Flags a specific subscription charge as unauthorized and creates a dispute ticket.
    
    Use this tool when the user states that a charge is unrecognized or was billed incorrectly.
    
    Args:
        subscription_name: The brand name of the subscription service.
        amount_in_usd: The charge amount in USD.
        transaction_date: The date of the charge (YYYY-MM-DD).
        
    Returns:
        A dictionary containing the generated dispute ticket details.
    """
    try:
        inputs = UnauthorizedChargeInput(
            subscription_name=subscription_name,
            amount_in_usd=amount_in_usd,
            transaction_date=transaction_date
        )
    except ValidationError as err:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "message": str(err),
            "recovery_instruction": "Ensure the amount is a valid number and the date format matches YYYY-MM-DD."
        }

    ticket_id = f"DISP-{uuid.uuid4().hex[:8].upper()}"
    return {
        "status": "success",
        "dispute_ticket_id": ticket_id,
        "vendor": inputs.subscription_name,
        "disputed_amount": inputs.amount_in_usd,
        "transaction_date": inputs.transaction_date,
        "workflow": "monitoring_charge_dispute"
    }


def request_subscription_cancellation(
    subscription_id: str, 
    user_email_associated: str, 
    reason: str = "No longer needed"
) -> Dict[str, Any]:
    """Requests the complete cancellation of a subscription from the provider.
    
    This is a high-stakes action. Large-value cancellations require human authorization.
    
    Args:
        subscription_id: The ID of the subscription record in the active database.
        user_email_associated: The email address registered with the subscription account.
        reason: The explanation to give to the provider for leaving.
        
    Returns:
        A success payload, or a 'pending_approval' hook if the action requires verification.
    """
    try:
        inputs = SubscriptionCancellationInput(
            subscription_id=subscription_id,
            user_email_associated=user_email_associated,
            reason=reason
        )
    except ValidationError as err:
        return {
            "status": "error",
            "error_type": "ValidationError",
            "message": str(err),
            "recovery_instruction": "Verify that subscription_id and user_email_associated are valid string values."
        }

    # Simulate database retrieval to check charge amount
    # (High-stakes threshold: any subscription costing more than $20/month triggers Human-In-The-Loop)
    # Mock lookup
    mock_subscriptions = {
        "sub-netflix": {"name": "Netflix Premium", "cost": 15.99},
        "sub-adobe": {"name": "Adobe Creative Cloud", "cost": 54.99},
        "sub-aws": {"name": "AWS Sandbox", "cost": 120.00}
    }
    
    sub = mock_subscriptions.get(inputs.subscription_id, {"name": "Unknown Service", "cost": 10.00})
    
    # Human-In-The-Loop Hook
    if sub["cost"] >= 20.00:
        approval_token = f"APP-TOK-{uuid.uuid4().hex[:12].upper()}"
        return {
            "status": "pending_approval",
            "action": "cancel_subscription",
            "subscription_id": inputs.subscription_id,
            "subscription_name": sub["name"],
            "cost": sub["cost"],
            "approval_token": approval_token,
            "reason": inputs.reason,
            "message": (
                f"ACTION REQUIRED: The cancellation of '{sub['name']}' costs ${sub['cost']:.2f}/month. "
                f"Because this exceeds the safety threshold ($20.00), it has been suspended. "
                f"Please run the approval hook with token '{approval_token}' to execute."
            )
        }

    # Low cost cancellations execute directly
    return {
        "status": "success",
        "subscription_id": inputs.subscription_id,
        "subscription_name": sub["name"],
        "cost": sub["cost"],
        "message": f"Successfully sent cancellation request for {sub['name']}."
    }
