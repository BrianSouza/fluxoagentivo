"""Cost budgets (docs/spec/12_OBSERVABILITY_COST.md §3).

When a budget is exceeded the system stops optional enrichment and keeps
deterministic processing running — losing AI enrichment is acceptable,
losing ingestion is not.
"""

from dataclasses import dataclass, field


class BudgetExceededError(Exception):
    """Raised when an optional model call would exceed a configured budget."""


@dataclass(slots=True)
class BudgetLimits:
    per_job_usd: float | None = None
    daily_usd: float | None = None

    def __post_init__(self) -> None:
        for name in ("per_job_usd", "daily_usd"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative, got {value!r}")


@dataclass(slots=True)
class BudgetTracker:
    """Tracks spend against limits. Callers decide what is optional."""

    limits: BudgetLimits = field(default_factory=BudgetLimits)
    job_spend_usd: float = 0.0
    daily_spend_usd: float = 0.0

    def would_exceed(self, cost: float) -> bool:
        if (
            self.limits.per_job_usd is not None
            and self.job_spend_usd + cost > self.limits.per_job_usd
        ):
            return True
        return (
            self.limits.daily_usd is not None
            and self.daily_spend_usd + cost > self.limits.daily_usd
        )

    def charge(self, cost: float) -> None:
        if cost < 0:
            raise ValueError(f"cost must not be negative, got {cost!r}")
        self.job_spend_usd += cost
        self.daily_spend_usd += cost

    def reset_job(self) -> None:
        self.job_spend_usd = 0.0
