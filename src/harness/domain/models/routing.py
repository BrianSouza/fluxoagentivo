"""Model profiles and routing policy (spec §4, §5, §6, §7).

Routing is policy, not code: profiles and routes come from configuration.
A task names a profile; the profile names a provider and model. Domain
code therefore never mentions a vendor.
"""

from dataclasses import dataclass, field

from harness.domain.models.contracts import ModelTask
from harness.domain.models.telemetry import ModelPricing


@dataclass(frozen=True, slots=True)
class ModelProfile:
    name: str
    provider: str
    model: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    pricing: ModelPricing = ModelPricing()
    # Escalation target for this profile (spec §6). None means the profile
    # is terminal — a failure here is a failure, not a retry at higher cost.
    escalates_to: str | None = None
    # Data-sensitivity guard (spec §7): profiles marked local-only must
    # never be swapped for a remote provider by escalation.
    local_only: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("profile name must not be empty")
        if not self.provider:
            raise ValueError(f"profile {self.name!r} must name a provider")
        if not self.model:
            raise ValueError(f"profile {self.name!r} must name a model")
        if self.escalates_to == self.name:
            raise ValueError(f"profile {self.name!r} cannot escalate to itself")


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    profiles: dict[str, ModelProfile]
    routes: dict[ModelTask, str] = field(default_factory=dict)
    default_profile: str | None = None

    def __post_init__(self) -> None:
        for task, profile_name in self.routes.items():
            if profile_name not in self.profiles:
                raise ValueError(
                    f"route for {task.value!r} points at unknown profile {profile_name!r}"
                )
        if self.default_profile is not None and self.default_profile not in self.profiles:
            raise ValueError(f"unknown default profile {self.default_profile!r}")
        for profile in self.profiles.values():
            if profile.escalates_to is not None and profile.escalates_to not in self.profiles:
                raise ValueError(
                    f"profile {profile.name!r} escalates to unknown profile "
                    f"{profile.escalates_to!r}"
                )

    def profile_for(self, task: ModelTask) -> ModelProfile:
        name = self.routes.get(task) or self.default_profile
        if name is None:
            raise LookupError(f"no route configured for task {task.value!r}")
        return self.profiles[name]

    def escalation_for(self, profile: ModelProfile) -> ModelProfile | None:
        """Next profile to try, honouring the local-only guard."""
        if profile.escalates_to is None:
            return None
        target = self.profiles[profile.escalates_to]
        if profile.local_only and not target.local_only:
            # Escalating sensitive work off-box would leak it; refuse.
            return None
        return target
