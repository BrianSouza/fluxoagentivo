"""Routing Model Gateway (TASK-023, TASK-024).

Resolves task -> profile -> provider/model, applies profile defaults,
records telemetry for every call including failures, and escalates when a
structured response is invalid or confidence is below threshold (spec §6).

This is the only place that knows both routing policy and concrete
providers; application code sees the capability interface alone.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from harness.domain.models.budget import BudgetExceededError, BudgetTracker
from harness.domain.models.contracts import (
    Capability,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelResponse,
    ModelTask,
    MultimodalRequest,
    RerankRequest,
    RerankResponse,
    StructuredOutputError,
    TextGenerationRequest,
    UnsupportedCapabilityError,
    Usage,
)
from harness.domain.models.ports import ModelCallSink, ModelProvider
from harness.domain.models.routing import ModelProfile, RoutingPolicy
from harness.domain.models.telemetry import ModelCall, ModelCallStatus

ResponseValidator = Callable[[ModelResponse], bool]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class NullCallSink:
    """Discards telemetry. Useful in tests and one-off scripts."""

    def record(self, call: ModelCall) -> None:
        return None


class RoutingModelGateway:
    """Satisfies harness.domain.models.ports.ModelGateway."""

    def __init__(
        self,
        providers: dict[str, ModelProvider],
        policy: RoutingPolicy,
        *,
        sink: ModelCallSink | None = None,
        budget: BudgetTracker | None = None,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        missing = {
            profile.provider
            for profile in policy.profiles.values()
            if profile.provider not in providers
        }
        if missing:
            raise ValueError(f"routing policy references unconfigured providers: {sorted(missing)}")
        self._providers = providers
        self._policy = policy
        self._sink = sink or NullCallSink()
        self._budget = budget
        self._now = now

    async def generate_text(
        self,
        request: TextGenerationRequest,
        *,
        validator: ResponseValidator | None = None,
        artifact_id: UUID | None = None,
    ) -> ModelResponse:
        return await self._generate(
            request=request,
            capability=Capability.TEXT,
            call=lambda provider, profile: provider.generate_text(
                _apply_text_defaults(request, profile), profile.model
            ),
            validator=validator,
            artifact_id=artifact_id,
        )

    async def generate_multimodal(
        self,
        request: MultimodalRequest,
        *,
        validator: ResponseValidator | None = None,
        artifact_id: UUID | None = None,
    ) -> ModelResponse:
        return await self._generate(
            request=request,
            capability=Capability.MULTIMODAL,
            call=lambda provider, profile: provider.generate_multimodal(
                _apply_multimodal_defaults(request, profile), profile.model
            ),
            validator=validator,
            artifact_id=artifact_id,
        )

    async def embed(
        self, request: EmbeddingRequest, *, artifact_id: UUID | None = None
    ) -> EmbeddingResponse:
        profile = self._resolve(request.task, Capability.EMBEDDING)
        provider = self._providers[profile.provider]
        started = time.perf_counter()
        try:
            response = await provider.embed(request, profile.model)
        except Exception as exc:
            self._record_failure(request.task, profile, started, exc, artifact_id)
            raise
        response.latency_ms = _elapsed_ms(started)
        self._record_success(
            request.task, profile, response.usage, response.latency_ms, artifact_id
        )
        return response

    async def rerank(
        self, request: RerankRequest, *, artifact_id: UUID | None = None
    ) -> RerankResponse:
        profile = self._resolve(request.task, Capability.RERANK)
        provider = self._providers[profile.provider]
        started = time.perf_counter()
        try:
            response = await provider.rerank(request, profile.model)
        except Exception as exc:
            self._record_failure(request.task, profile, started, exc, artifact_id)
            raise
        response.latency_ms = _elapsed_ms(started)
        self._record_success(
            request.task, profile, response.usage, response.latency_ms, artifact_id
        )
        return response

    async def _generate(
        self,
        *,
        request: TextGenerationRequest | MultimodalRequest,
        capability: Capability,
        call: Callable[[ModelProvider, ModelProfile], Any],
        validator: ResponseValidator | None,
        artifact_id: UUID | None,
    ) -> ModelResponse:
        profile: ModelProfile | None = self._resolve(request.task, capability)
        last_error: Exception | None = None

        while profile is not None:
            provider = self._providers[profile.provider]
            if not provider.supports(capability):
                profile = self._policy.escalation_for(profile)
                continue

            self._check_budget(profile)
            started = time.perf_counter()
            try:
                response: ModelResponse = await call(provider, profile)
            except StructuredOutputError as exc:
                # Invalid structured output is an escalation trigger (§6),
                # not an immediate failure.
                self._record_failure(request.task, profile, started, exc, artifact_id)
                last_error = exc
                profile = self._policy.escalation_for(profile)
                continue
            except Exception as exc:
                self._record_failure(request.task, profile, started, exc, artifact_id)
                raise

            response.latency_ms = _elapsed_ms(started)
            cost = self._record_success(
                request.task,
                profile,
                response.usage,
                response.latency_ms,
                artifact_id,
                prompt_version=request.prompt_version,
            )
            if validator is not None and not validator(response):
                last_error = StructuredOutputError(
                    f"response from profile {profile.name!r} rejected by validator"
                )
                profile = self._policy.escalation_for(profile)
                continue
            if self._budget is not None:
                self._budget.charge(cost)
            return response

        if last_error is not None:
            raise last_error
        raise UnsupportedCapabilityError(
            f"no configured profile can serve {capability.value!r} for task {request.task.value!r}"
        )

    def _resolve(self, task: ModelTask, capability: Capability) -> ModelProfile:
        profile = self._policy.profile_for(task)
        provider = self._providers[profile.provider]
        if provider.supports(capability):
            return profile
        escalated = self._policy.escalation_for(profile)
        while escalated is not None:
            if self._providers[escalated.provider].supports(capability):
                return escalated
            escalated = self._policy.escalation_for(escalated)
        raise UnsupportedCapabilityError(
            f"provider {profile.provider!r} does not support {capability.value!r}"
        )

    def _check_budget(self, profile: ModelProfile) -> None:
        if self._budget is None:
            return
        # Charge is applied after the call, when real usage is known; this
        # only blocks work that is already over budget.
        if self._budget.would_exceed(0.0):
            raise BudgetExceededError(
                f"budget exhausted before calling profile {profile.name!r}"
            )

    def _record_success(
        self,
        task: ModelTask,
        profile: ModelProfile,
        usage: Usage,
        latency_ms: int,
        artifact_id: UUID | None,
        *,
        prompt_version: str | None = None,
    ) -> float:
        cost = profile.pricing.estimate(usage)
        self._sink.record(
            ModelCall(
                task=task,
                provider=profile.provider,
                model=profile.model,
                status=ModelCallStatus.SUCCEEDED,
                created_at=self._now(),
                usage=usage,
                latency_ms=latency_ms,
                estimated_cost=cost,
                profile=profile.name,
                prompt_version=prompt_version,
                artifact_id=artifact_id,
            )
        )
        return cost

    def _record_failure(
        self,
        task: ModelTask,
        profile: ModelProfile,
        started: float,
        error: Exception,
        artifact_id: UUID | None,
    ) -> None:
        self._sink.record(
            ModelCall(
                task=task,
                provider=profile.provider,
                model=profile.model,
                status=ModelCallStatus.FAILED,
                created_at=self._now(),
                latency_ms=_elapsed_ms(started),
                profile=profile.name,
                artifact_id=artifact_id,
                error_message=str(error),
            )
        )


def _elapsed_ms(started: float) -> int:
    return max(int((time.perf_counter() - started) * 1000), 0)


def _apply_text_defaults(
    request: TextGenerationRequest, profile: ModelProfile
) -> TextGenerationRequest:
    return TextGenerationRequest(
        prompt=request.prompt,
        task=request.task,
        system=request.system,
        temperature=request.temperature if request.temperature is not None else profile.temperature,
        max_output_tokens=(
            request.max_output_tokens
            if request.max_output_tokens is not None
            else profile.max_output_tokens
        ),
        json_schema=request.json_schema,
        prompt_version=request.prompt_version,
        metadata=request.metadata,
    )


def _apply_multimodal_defaults(
    request: MultimodalRequest, profile: ModelProfile
) -> MultimodalRequest:
    return MultimodalRequest(
        prompt=request.prompt,
        images=request.images,
        task=request.task,
        system=request.system,
        temperature=request.temperature if request.temperature is not None else profile.temperature,
        max_output_tokens=(
            request.max_output_tokens
            if request.max_output_tokens is not None
            else profile.max_output_tokens
        ),
        json_schema=request.json_schema,
        prompt_version=request.prompt_version,
        metadata=request.metadata,
    )
