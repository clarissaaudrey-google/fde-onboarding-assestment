import json
import logging
import re
import sys
from typing import Any, Dict, Optional
import structlog
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

# Initialize OpenTelemetry Distributed Tracing (Rubric 4.3)
# To avoid crashing when running without a collector, we configure a console span exporter
provider = TracerProvider()
processor = SimpleSpanProcessor(ConsoleSpanExporter(out=sys.stderr))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("finsentry")

# PII Scrubbing Rules (Rubric 4.4)
CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")

def redact_value(value: Any) -> Any:
    """Scrubs sensitive PII patterns from text data recursively."""
    if isinstance(value, str):
        # Redact credit card numbers
        value = CREDIT_CARD_REGEX.sub("[REDACTED_CREDIT_CARD]", value)
        # Redact SSNs
        value = SSN_REGEX.sub("[REDACTED_SSN]", value)
        # Redact Emails
        value = EMAIL_REGEX.sub("[REDACTED_EMAIL]", value)
        return value
    elif isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [redact_value(item) for item in value]
    return value

def pii_redaction_processor(logger, method_name, event_dict):
    """structlog processor to scrub PII from all log event payloads before writing."""
    return redact_value(event_dict)

# Configure Structured JSON Logging (Rubric 4.1)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        pii_redaction_processor,  # Active PII scrubbing
        structlog.processors.JSONRenderer(serializer=json.dumps)
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Intent vs Outcome Capture helper (Rubric 4.2)
class IntentOutcomeSpan:
    """A context manager to automatically log an agent's intent before execution

    and its outcome (success, failure, or human-intervention-needed) after execution.
    It links the action to an OpenTelemetry span for tracing.
    """
    def __init__(self, action_name: str, metadata: Optional[Dict[str, Any]] = None):
        self.action_name = action_name
        self.metadata = metadata or {}
        self.otel_span = None

    def __enter__(self):
        # Start OpenTelemetry tracing span
        self.otel_span = tracer.start_span(self.action_name)
        ctx = self.otel_span.get_span_context()
        self.trace_id = format(ctx.trace_id, "032x")
        
        # Log Intent before execution (Rubric 4.2)
        logger.info(
            "agent_intent_captured",
            action=self.action_name,
            phase="intent",
            trace_id=self.trace_id,
            status="pending",
            details=self.metadata
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Log failure outcome
            logger.error(
                "agent_outcome_captured",
                action=self.action_name,
                phase="outcome",
                trace_id=self.trace_id,
                status="failure",
                error_type=exc_type.__name__,
                error_message=str(exc_val)
            )
            self.otel_span.set_attribute("status", "error")
            self.otel_span.record_exception(exc_val)
        else:
            # Log successful outcome (Rubric 4.2)
            logger.info(
                "agent_outcome_captured",
                action=self.action_name,
                phase="outcome",
                trace_id=self.trace_id,
                status="success",
                details=self.metadata
            )
            self.otel_span.set_attribute("status", "success")
            
        self.otel_span.end()
        return False  # Do not suppress exception
        
    def log_hitl_action(self, message: str):
        """Helper to log that human intervention is required during this span."""
        logger.warn(
            "agent_outcome_captured",
            action=self.action_name,
            phase="outcome",
            trace_id=self.trace_id,
            status="hitl_approval_required",
            message=message,
            details=self.metadata
        )
        self.otel_span.set_attribute("status", "hitl_required")
