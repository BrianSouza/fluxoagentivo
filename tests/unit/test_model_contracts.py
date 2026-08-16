"""Gateway contracts, routing policy, budgets and pricing (TASK-019, TASK-023)."""

import pytest

from harness.domain.models.budget import BudgetLimits, BudgetTracker
from harness.domain.models.contracts import (
    EmbeddingRequest,
    ImageInput,
    ModelTask,
    MultimodalRequest,
    RerankRequest,
    TextGenerationRequest,
    Usage,
)
from harness.domain.models.routing import ModelProfile, RoutingPolicy
from harness.domain.models.telemetry import ModelPricing


class TestRequestInvariants:
    def test_empty_prompt_rejected(self) -> None:
        with pytest.raises(ValueError, match="prompt"):
            TextGenerationRequest(prompt="")

    def test_multimodal_requires_an_image(self) -> None:
        with pytest.raises(ValueError, match="at least one image"):
            MultimodalRequest(prompt="describe", images=[])

    def test_embedding_requires_input(self) -> None:
        with pytest.raises(ValueError, match="at least one input"):
            EmbeddingRequest(inputs=[])

    def test_rerank_requires_query_and_documents(self) -> None:
        with pytest.raises(ValueError, match="query"):
            RerankRequest(query="", documents=["a"])
        with pytest.raises(ValueError, match="at least one document"):
            RerankRequest(query="q", documents=[])

    def test_usage_rejects_negative_counts(self) -> None:
        with pytest.raises(ValueError, match="input_tokens"):
            Usage(input_tokens=-1)

    def test_usage_totals(self) -> None:
        assert Usage(input_tokens=10, output_tokens=5).total_tokens == 15


class TestPricing:
    def test_estimates_cost_per_million_tokens(self) -> None:
        pricing = ModelPricing(input_per_million=3.0, output_per_million=15.0)
        cost = pricing.estimate(Usage(input_tokens=1_000_000, output_tokens=1_000_000))
        assert cost == pytest.approx(18.0)

    def test_cached_input_is_discounted(self) -> None:
        pricing = ModelPricing(
            input_per_million=3.0, output_per_million=0.0, cached_input_per_million=0.3
        )
        cost = pricing.estimate(Usage(input_tokens=1_000_000, cached_input_tokens=1_000_000))
        assert cost == pytest.approx(0.3)

    def test_free_by_default(self) -> None:
        assert ModelPricing().estimate(Usage(input_tokens=999)) == 0.0


class TestModelProfile:
    def test_requires_provider_and_model(self) -> None:
        with pytest.raises(ValueError, match="provider"):
            ModelProfile(name="p", provider="", model="m")
        with pytest.raises(ValueError, match="model"):
            ModelProfile(name="p", provider="prov", model="")

    def test_cannot_escalate_to_itself(self) -> None:
        with pytest.raises(ValueError, match="escalate to itself"):
            ModelProfile(name="p", provider="prov", model="m", escalates_to="p")


class TestRoutingPolicy:
    def policy(self) -> RoutingPolicy:
        return RoutingPolicy(
            profiles={
                "cheap": ModelProfile("cheap", "fake", "small", escalates_to="strong"),
                "strong": ModelProfile("strong", "fake", "large"),
                "local": ModelProfile(
                    "local", "fake", "tiny", escalates_to="strong", local_only=True
                ),
            },
            routes={ModelTask.CLASSIFICATION: "cheap"},
            default_profile="cheap",
        )

    def test_routes_task_to_profile(self) -> None:
        assert self.policy().profile_for(ModelTask.CLASSIFICATION).name == "cheap"

    def test_falls_back_to_default_profile(self) -> None:
        assert self.policy().profile_for(ModelTask.PAGE_SYNTHESIS).name == "cheap"

    def test_missing_route_without_default_raises(self) -> None:
        policy = RoutingPolicy(profiles={"a": ModelProfile("a", "fake", "m")})
        with pytest.raises(LookupError, match="no route configured"):
            policy.profile_for(ModelTask.ANSWER_GENERATION)

    def test_unknown_route_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown profile"):
            RoutingPolicy(
                profiles={"a": ModelProfile("a", "fake", "m")},
                routes={ModelTask.CLASSIFICATION: "ghost"},
            )

    def test_unknown_escalation_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="escalates to unknown profile"):
            RoutingPolicy(profiles={"a": ModelProfile("a", "fake", "m", escalates_to="ghost")})

    def test_escalation_returns_next_profile(self) -> None:
        policy = self.policy()
        escalated = policy.escalation_for(policy.profiles["cheap"])
        assert escalated is not None and escalated.name == "strong"

    def test_terminal_profile_does_not_escalate(self) -> None:
        policy = self.policy()
        assert policy.escalation_for(policy.profiles["strong"]) is None

    def test_local_only_never_escalates_to_a_remote_profile(self) -> None:
        # Escalating sensitive work off-box would leak it.
        policy = self.policy()
        assert policy.escalation_for(policy.profiles["local"]) is None


class TestBudget:
    def test_allows_spend_below_limit(self) -> None:
        tracker = BudgetTracker(limits=BudgetLimits(per_job_usd=1.0))
        assert not tracker.would_exceed(0.5)

    def test_blocks_spend_above_job_limit(self) -> None:
        tracker = BudgetTracker(limits=BudgetLimits(per_job_usd=1.0))
        tracker.charge(0.9)
        assert tracker.would_exceed(0.2)

    def test_blocks_spend_above_daily_limit(self) -> None:
        tracker = BudgetTracker(limits=BudgetLimits(daily_usd=2.0))
        tracker.charge(1.9)
        assert tracker.would_exceed(0.2)

    def test_reset_job_keeps_daily_total(self) -> None:
        tracker = BudgetTracker(limits=BudgetLimits(per_job_usd=1.0, daily_usd=10.0))
        tracker.charge(0.8)
        tracker.reset_job()
        assert tracker.job_spend_usd == 0.0
        assert tracker.daily_spend_usd == pytest.approx(0.8)

    def test_unlimited_by_default(self) -> None:
        assert not BudgetTracker().would_exceed(1_000_000.0)

    def test_negative_limits_and_charges_rejected(self) -> None:
        with pytest.raises(ValueError, match="per_job_usd"):
            BudgetLimits(per_job_usd=-1.0)
        with pytest.raises(ValueError, match="cost"):
            BudgetTracker().charge(-1.0)


def test_image_input_defaults_to_png() -> None:
    assert ImageInput(data=b"x").media_type == "image/png"
