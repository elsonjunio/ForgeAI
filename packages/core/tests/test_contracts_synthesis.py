from __future__ import annotations

import pytest
from pydantic import ValidationError

from core import (
    Capability,
    CapabilityDescriptor,
    CompactionRequest,
    ExecutionContext,
    ExecutionPlan,
    Observation,
    PlanningRequest,
    PlanningResult,
    Synthesis,
    SynthesisRequest,
    Synthesizer,
)


class _FakeSynthesizer(Synthesizer):
    @property
    def name(self) -> str:
        return "fake-synthesizer"

    def synthesize(self, request: SynthesisRequest) -> Synthesis:
        joined = " | ".join(obs.output for obs in request.observations)
        if request.mode == "compact":
            return Synthesis(text=f"summary: {joined}")
        return Synthesis(text=f"answer: {joined}")


def test_synthesizer_is_a_capability_not_executable() -> None:
    synthesizer = _FakeSynthesizer()

    assert isinstance(synthesizer, Capability)
    assert synthesizer.kind == "synthesizer"
    assert synthesizer.name == "fake-synthesizer"
    assert synthesizer.describe().id == "synthesizer:fake-synthesizer"
    assert not hasattr(synthesizer, "execute")


def test_synthesizer_produces_answer_and_checkpoint() -> None:
    request = SynthesisRequest(
        request="do it",
        observations=(Observation(node_id="n1", output="step-1"),),
    )

    answer = _FakeSynthesizer().synthesize(request)
    assert answer.text == "answer: step-1"

    checkpoint = _FakeSynthesizer().synthesize(
        SynthesisRequest(request="do it", mode="compact")
    )
    assert checkpoint.text == "summary: "


def test_synthesis_request_defaults_and_checkpoint() -> None:
    request = SynthesisRequest(request="do it")
    assert request.observations == ()
    assert request.checkpoint is None
    assert request.mode == "answer"
    assert request.metadata == {}

    carried = SynthesisRequest(
        request="do it",
        observations=(Observation(node_id="n1", role="checkpoint", output="sum"),),
        checkpoint="earlier summary",
        mode="compact",
    )
    assert carried.checkpoint == "earlier summary"
    assert carried.observations[0].role == "checkpoint"


def test_synthesis_request_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SynthesisRequest(request="do it", unexpected=True)  # type: ignore[call-arg]


def test_synthesis_request_rejects_invalid_mode() -> None:
    with pytest.raises(ValidationError):
        SynthesisRequest(request="do it", mode="merge")


def test_observation_role_defaults_to_result() -> None:
    assert Observation(node_id="n1").role == "result"
    with pytest.raises(ValidationError):
        Observation(node_id="n1", role="summary")


def test_planning_request_carries_checkpoint_and_synthesizers() -> None:
    descriptor = CapabilityDescriptor(
        id="synthesizer:default", name="default", kind="synthesizer"
    )
    request = PlanningRequest(
        request="do it",
        context=ExecutionContext(request="do it"),
        synthesizers=(descriptor,),
        checkpoint="prior summary",
    )

    assert request.synthesizers == (descriptor,)
    assert request.checkpoint == "prior summary"


def test_planning_request_budget_and_scratchpad_defaults() -> None:
    request = PlanningRequest(request="do it", context=ExecutionContext(request="do it"))
    assert request.max_nodes is None
    assert request.scratchpad == ""


def test_usage_is_optional_on_results() -> None:
    from core import ExecutionPlan

    assert PlanningResult(plan=ExecutionPlan(id="p")).usage is None
    assert Synthesis(text="x").usage is None


def test_planning_result_carries_compaction_request() -> None:
    plan = ExecutionPlan(id="plan-1")
    default = PlanningResult(plan=plan)
    assert default.compaction is None

    result = PlanningResult(
        plan=plan,
        compaction=CompactionRequest(keep_last=2, reason="too many steps"),
    )
    assert result.compaction is not None
    assert result.compaction.enabled is True
    assert result.compaction.keep_last == 2


def test_compaction_request_validates_keep_last() -> None:
    assert CompactionRequest().keep_last == 0
    with pytest.raises(ValidationError):
        CompactionRequest(keep_last=-1)
