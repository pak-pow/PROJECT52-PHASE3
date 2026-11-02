"""Mathematical proration engine for mid-cycle SaaS plan adjustments."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.schemas import BillingInterval, Plan, Subscription


@dataclass
class ProrationResult:
    """Detailed financial breakdown of a mid-cycle subscription change."""

    current_plan_id: str
    new_plan_id: str
    current_plan_name: str
    new_plan_name: str
    current_price_cents: int
    new_price_cents: int
    billing_interval: str
    period_start: str
    period_end: str
    effective_timestamp: str
    total_period_seconds: float
    remaining_seconds: float
    remaining_ratio: float
    unused_credit_cents: int
    new_plan_charge_cents: int
    net_amount_due_cents: int
    credit_remaining_cents: int
    is_upgrade: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert calculation results to serializable dictionary."""
        return asdict(self)

    def to_line_items(self) -> List[Dict[str, Any]]:
        """Generate structured invoice line items detailing the prorated adjustment."""
        items: List[Dict[str, Any]] = []

        # 1. Credit for unused time on previous plan
        if self.unused_credit_cents > 0:
            items.append(
                {
                    "description": (
                        f"Unused time on {self.current_plan_name} "
                        f"({int(self.remaining_ratio * 100)}% remaining)"
                    ),
                    "unit_amount_cents": -self.unused_credit_cents,
                    "quantity": 1,
                    "proration": True,
                }
            )

        # 2. Charge for remaining time on upgraded/new plan
        if self.new_plan_charge_cents > 0:
            items.append(
                {
                    "description": (
                        f"Remaining time on {self.new_plan_name} "
                        f"({int(self.remaining_ratio * 100)}% remaining)"
                    ),
                    "unit_amount_cents": self.new_plan_charge_cents,
                    "quantity": 1,
                    "proration": True,
                }
            )

        # 3. If net due is zero and no charges/credits (e.g. Free to Free)
        if not items:
            items.append(
                {
                    "description": (
                        f"Tier transition: {self.current_plan_name} to "
                        f"{self.new_plan_name}"
                    ),
                    "unit_amount_cents": 0,
                    "quantity": 1,
                    "proration": True,
                }
            )

        return items


def calculate_proration(
    current_plan: Plan,
    new_plan: Plan,
    subscription: Subscription,
    effective_at: Optional[datetime] = None,
    target_interval: Optional[BillingInterval] = None,
) -> ProrationResult:
    """Calculate exact linear second-rate proration for mid-cycle tier changes.

    Formula:
        total_seconds = period_end - period_start
        remaining_seconds = period_end - effective_at
        remaining_ratio = clamp(0.0, 1.0, remaining_seconds / total_seconds)
        unused_credit = round(current_price * remaining_ratio)
        new_plan_charge = round(new_price * remaining_ratio)
        net_due = max(0, new_plan_charge - unused_credit)
        credit_remaining = max(0, unused_credit - new_plan_charge)
    """
    now = effective_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Parse period start and end
    fmt = "%Y-%m-%d %H:%M:%S"
    start_dt = datetime.strptime(subscription.current_period_start, fmt).replace(
        tzinfo=timezone.utc
    )
    end_dt = datetime.strptime(subscription.current_period_end, fmt).replace(
        tzinfo=timezone.utc
    )

    total_seconds = max(1.0, (end_dt - start_dt).total_seconds())
    diff_remaining = (end_dt - now).total_seconds()
    remaining_seconds = max(0.0, min(total_seconds, diff_remaining))
    remaining_ratio = remaining_seconds / total_seconds

    # Resolve pricing according to billing interval
    interval = (
        target_interval.value
        if target_interval is not None
        else subscription.billing_interval
    )

    if subscription.billing_interval == BillingInterval.ANNUAL.value:
        current_price = current_plan.price_annual_cents
    else:
        current_price = current_plan.price_monthly_cents

    if interval == BillingInterval.ANNUAL.value:
        new_price = new_plan.price_annual_cents
    else:
        new_price = new_plan.price_monthly_cents

    unused_credit_cents = int(round(current_price * remaining_ratio))
    new_plan_charge_cents = int(round(new_price * remaining_ratio))

    if new_plan_charge_cents >= unused_credit_cents:
        net_amount_due_cents = new_plan_charge_cents - unused_credit_cents
        credit_remaining_cents = 0
    else:
        net_amount_due_cents = 0
        credit_remaining_cents = unused_credit_cents - new_plan_charge_cents

    is_upgrade = new_price >= current_price

    return ProrationResult(
        current_plan_id=current_plan.id,
        new_plan_id=new_plan.id,
        current_plan_name=current_plan.name,
        new_plan_name=new_plan.name,
        current_price_cents=current_price,
        new_price_cents=new_price,
        billing_interval=interval,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        effective_timestamp=now.strftime(fmt),
        total_period_seconds=total_seconds,
        remaining_seconds=remaining_seconds,
        remaining_ratio=remaining_ratio,
        unused_credit_cents=unused_credit_cents,
        new_plan_charge_cents=new_plan_charge_cents,
        net_amount_due_cents=net_amount_due_cents,
        credit_remaining_cents=credit_remaining_cents,
        is_upgrade=is_upgrade,
    )
