"""Domain models, enums, and dataclasses for PulseSub."""

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PlanTier(str, Enum):
    """Supported SaaS plan tiers in order of hierarchy."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class BillingInterval(str, Enum):
    """Subscription recurrence intervals."""

    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(str, Enum):
    """Lifecycle states of a subscription."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class InvoiceStatus(str, Enum):
    """Payment and settlement states of an invoice."""

    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    UNCOLLECTIBLE = "uncollectible"
    VOID = "void"


class WebhookStatus(str, Enum):
    """Processing states of inbound webhook events."""

    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


def _to_str_timestamp(val: Any) -> str:
    """Safely normalize timestamp values from database rows into strings."""
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    return str(val)


@dataclass
class Plan:
    """Pricing plan definition with limits and feature toggles."""

    id: str
    name: str
    tier: str
    price_monthly_cents: int
    price_annual_cents: int
    limits: Dict[str, int] = field(default_factory=dict)
    features: List[str] = field(default_factory=list)
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Plan":
        """Instantiate Plan from database row."""
        limits = {}
        if row["limits_json"]:
            try:
                limits = json.loads(row["limits_json"])
            except (ValueError, TypeError):
                limits = {}

        features = []
        if row["features_json"]:
            try:
                features = json.loads(row["features_json"])
            except (ValueError, TypeError):
                features = []

        return cls(
            id=row["id"],
            name=row["name"],
            tier=row["tier"],
            price_monthly_cents=row["price_monthly_cents"],
            price_annual_cents=row["price_annual_cents"],
            limits=limits,
            features=features,
            is_active=bool(row["is_active"]),
        )


@dataclass
class Subscription:
    """Active or historical user subscription record."""

    id: str
    user_id: str
    plan_id: str
    billing_interval: str
    status: str
    current_period_start: str
    current_period_end: str
    cancel_at_period_end: bool = False
    canceled_at: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert subscription to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Subscription":
        """Instantiate Subscription from database row."""
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            plan_id=row["plan_id"],
            billing_interval=row["billing_interval"],
            status=row["status"],
            current_period_start=_to_str_timestamp(row["current_period_start"]),
            current_period_end=_to_str_timestamp(row["current_period_end"]),
            cancel_at_period_end=bool(row["cancel_at_period_end"]),
            canceled_at=(
                _to_str_timestamp(row["canceled_at"]) if row["canceled_at"] else None
            ),
            created_at=(
                _to_str_timestamp(row["created_at"])
                if "created_at" in row.keys()
                else ""
            ),
            updated_at=(
                _to_str_timestamp(row["updated_at"])
                if "updated_at" in row.keys()
                else ""
            ),
        )


@dataclass
class Invoice:
    """Billing statement with line items and settlement record."""

    id: str
    user_id: str
    subscription_id: Optional[str]
    invoice_number: str
    amount_due_cents: int
    amount_paid_cents: int
    currency: str = "usd"
    status: str = "draft"
    line_items: List[Dict[str, Any]] = field(default_factory=list)
    payment_attempt_count: int = 0
    due_date: str = ""
    paid_at: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert invoice to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Invoice":
        """Instantiate Invoice from database row."""
        line_items = []
        if row["line_items_json"]:
            try:
                line_items = json.loads(row["line_items_json"])
            except (ValueError, TypeError):
                line_items = []

        return cls(
            id=row["id"],
            user_id=row["user_id"],
            subscription_id=row["subscription_id"],
            invoice_number=row["invoice_number"],
            amount_due_cents=row["amount_due_cents"],
            amount_paid_cents=row["amount_paid_cents"],
            currency=row["currency"],
            status=row["status"],
            line_items=line_items,
            payment_attempt_count=row["payment_attempt_count"],
            due_date=_to_str_timestamp(row["due_date"]),
            paid_at=_to_str_timestamp(row["paid_at"]) if row["paid_at"] else None,
            created_at=(
                _to_str_timestamp(row["created_at"])
                if "created_at" in row.keys()
                else ""
            ),
        )


@dataclass
class UsageRecord:
    """Individual metered resource consumption entry."""

    id: str
    user_id: str
    metric_key: str
    quantity: int = 1
    subscription_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    recorded_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert usage record to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "UsageRecord":
        """Instantiate UsageRecord from database row."""
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            metric_key=row["metric_key"],
            quantity=row["quantity"],
            subscription_id=row["subscription_id"],
            idempotency_key=row["idempotency_key"],
            recorded_at=_to_str_timestamp(row["recorded_at"]),
        )


@dataclass
class WebhookEventRecord:
    """Logged webhook event payload and resolution status."""

    id: str
    event_id: str
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    error_message: Optional[str] = None
    received_at: str = ""
    processed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert webhook record to serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "WebhookEventRecord":
        """Instantiate WebhookEventRecord from database row."""
        payload = {}
        if row["payload_json"]:
            try:
                payload = json.loads(row["payload_json"])
            except (ValueError, TypeError):
                payload = {}

        return cls(
            id=row["id"],
            event_id=row["event_id"],
            event_type=row["event_type"],
            payload=payload,
            status=row["status"],
            error_message=row["error_message"],
            received_at=_to_str_timestamp(row["received_at"]),
            processed_at=(
                _to_str_timestamp(row["processed_at"]) if row["processed_at"] else None
            ),
        )
