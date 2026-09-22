from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from code_agent_plugin_llm_planner import LLMPlannerPlugin
from code_agent_plugin_llm_synthesizer import LLMSynthesizerPlugin
from core import (
    Capability,
    CoreConfig,
    CoreContainer,
    ExecutionBudgets,
    LLMChunkCallback,
    LLMProvider,
    LLMResponse,
    LLMUsage,
    Message,
    Plugin,
    Synthesis,
    SynthesisRequest,
    Synthesizer,
    Tool,
    ToolContract,
    ToolResult,
    ValidationInput,
    ValidationResult,
    Validator,
    build_core,
)
from forge_cli.commands import handle_command
from forge_cli.session import ChatSession


class _EchoLLM(LLMProvider):
    @property
    def name(self) -> str:
        return "echo"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        return LLMResponse(message=Message(role="assistant", content="echo"))


class _FakePlugin(Plugin):
    id = "fake"
    version = "1.0.0"
    description = "fake plugin"

    def declare_capabilities(self) -> list[Capability]:
        return [_EchoLLM()]


def _core() -> CoreContainer:
    return build_core(plugins=[_FakePlugin()], discoverers=[])


def test_help_and_exit() -> None:
    core = _core()
    try:
        session = ChatSession(_EchoLLM(), stream=False)
        help_result = handle_command("/help", core=core, session=session)
        assert help_result is not None
        assert help_result.output
        assert help_result.should_exit is False

        exit_result = handle_command("/exit", core=core, session=session)
        assert exit_result is not None
        assert exit_result.should_exit is True
    finally:
        core.shutdown()


def test_capabilities_and_plugins_commands() -> None:
    core = _core()
    try:
        capabilities = handle_command("/capabilities", core=core, session=None)
        assert capabilities is not None
        assert any("llm:echo" in line for line in capabilities.output)

        plugins = handle_command("/plugins", core=core, session=None)
        assert plugins is not None
        assert any("fake" in line for line in plugins.output)

        providers = handle_command("/providers", core=core, session=None)
        assert providers is not None
        assert any("echo" in line for line in providers.output)
    finally:
        core.shutdown()


def test_non_command_returns_none() -> None:
    core = _core()
    try:
        assert handle_command("olá", core=core, session=None) is None
    finally:
        core.shutdown()


def test_chat_commands_without_session() -> None:
    core = _core()
    try:
        result = handle_command("/clear", core=core, session=None)
        assert result is not None
        assert "sem sessão" in result.output[0]
    finally:
        core.shutdown()


def test_plan_without_planner() -> None:
    core = _core()
    try:
        result = handle_command("/plan fazer algo", core=core, session=None)
        assert result is not None
        assert any("Planner" in line for line in result.output)
    finally:
        core.shutdown()


class _PlanLLM(LLMProvider):
    @property
    def name(self) -> str:
        return "plan-llm"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        content = (
            '{"nodes":[{"id":"n1","capability":"tool:echo",'
            '"description":"echo"}],"edges":[]}'
        )
        return LLMResponse(message=Message(role="assistant", content=content))


class _EchoTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="echo", description="echo")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(output="echo-output")


class _RunFakesPlugin(Plugin):
    id = "run-fakes"

    def declare_capabilities(self) -> list[Capability]:
        return [_PlanLLM(), _EchoTool()]


def test_run_executes_plan_end_to_end() -> None:
    core = build_core(plugins=[_RunFakesPlugin(), LLMPlannerPlugin()], discoverers=[])
    try:
        result = handle_command("/run fazer algo", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "status: completed" in text
        assert "n1: ok" in text
        assert "echo-output" in text
    finally:
        core.shutdown()


def test_format_node_output() -> None:
    from forge_cli.commands import _format_node_output

    assert _format_node_output(None) == []
    assert _format_node_output("hello") == ["    hello"]

    long_output = _format_node_output("\n".join(str(index) for index in range(100)))
    assert any("truncated" in line for line in long_output)


def test_context_advertises_only_executable_capabilities() -> None:
    from forge_cli.commands import _context

    core = build_core(plugins=[_RunFakesPlugin(), LLMPlannerPlugin()], discoverers=[])
    try:
        context = _context(core, "x")
        assert sorted(descriptor.id for descriptor in context.capabilities) == [
            "tool:echo"
        ]
        assert "working_directory" in context.metadata
    finally:
        core.shutdown()


class _ScriptedPlanLLM(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return "scripted-plan"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        self.prompts.append(messages[-1].content if messages else "")
        index = min(self._index, len(self._responses) - 1)
        content = self._responses[index]
        self._index += 1
        return LLMResponse(message=Message(role="assistant", content=content))


class _IterativePlugin(Plugin):
    id = "iterative-fakes"

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def declare_capabilities(self) -> list[Capability]:
        return [self._llm, _EchoTool()]


def test_run_iterates_until_planner_is_done() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": true, "nodes":[{"id":"list","capability":"tool:echo"}]}',
            '{"needs_more_info": false, "nodes":[{"id":"read","capability":"tool:echo"}]}',
        ]
    )
    core = build_core(
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma os docs", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "[iteração 1]" in text
        assert "[iteração 2]" in text
        assert "list: ok" in text
        assert "read: ok" in text
        assert len(llm.prompts) == 2
        assert "Information already gathered" in llm.prompts[1]
        assert "echo-output" in llm.prompts[1]
    finally:
        core.shutdown()


class _FakeSynthesizer(Synthesizer):
    def __init__(self) -> None:
        self.calls: list[SynthesisRequest] = []

    @property
    def name(self) -> str:
        return "fake-synthesizer"

    def synthesize(self, request: SynthesisRequest) -> Synthesis:
        self.calls.append(request)
        body = "|".join(observation.output for observation in request.observations)
        if request.mode == "compact":
            return Synthesis(text=f"CHECKPOINT:{body}")
        return Synthesis(text=f"ANSWER:{request.checkpoint or ''}:{body}")


class _SynthesisPlugin(Plugin):
    id = "synthesis-fakes"

    def __init__(self, llm: LLMProvider, synthesizer: Synthesizer) -> None:
        self._llm = llm
        self._synthesizer = synthesizer

    def declare_capabilities(self) -> list[Capability]:
        return [self._llm, _EchoTool(), self._synthesizer]


def test_run_synthesizes_final_answer() -> None:
    llm = _ScriptedPlanLLM(
        ['{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}']
    )
    synthesizer = _FakeSynthesizer()
    core = build_core(
        plugins=[_SynthesisPlugin(llm, synthesizer), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "resposta:" in text
        assert "ANSWER:" in text
        assert "echo-output" in text
        assert [call.mode for call in synthesizer.calls] == ["answer"]
    finally:
        core.shutdown()


def test_run_compacts_when_planner_requests_it() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": true, "compaction": {"keep_last": 0},'
            ' "nodes":[{"id":"list","capability":"tool:echo"}]}',
            '{"needs_more_info": false, "nodes":[{"id":"read","capability":"tool:echo"}]}',
        ]
    )
    synthesizer = _FakeSynthesizer()
    core = build_core(
        plugins=[_SynthesisPlugin(llm, synthesizer), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "compactação: 1 observação(ões) resumida(s)" in text
        assert "resposta:" in text
        assert [call.mode for call in synthesizer.calls] == ["compact", "answer"]
        assert "Previous checkpoint" in llm.prompts[1]
        assert "CHECKPOINT:echo-output" in llm.prompts[1]
    finally:
        core.shutdown()


def test_run_ignores_compaction_without_synthesizer() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": true, "compaction": {"keep_last": 0},'
            ' "nodes":[{"id":"list","capability":"tool:echo"}]}',
            '{"needs_more_info": false, "nodes":[{"id":"read","capability":"tool:echo"}]}',
        ]
    )
    core = build_core(
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "compactação pedida, mas nenhum Synthesizer registrado" in text
        assert "resposta:" not in text
    finally:
        core.shutdown()


def test_run_hints_when_no_synthesizer() -> None:
    llm = _ScriptedPlanLLM(
        ['{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}']
    )
    core = build_core(
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "instale um plugin de síntese" in text
        assert "resposta:" not in text
    finally:
        core.shutdown()


class _RecoverableFailTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="flaky", description="fails recoverably")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(
            output="FileNotFoundError: README.md",
            is_error=True,
            recoverable=True,
        )


class _FatalFailTool(Tool):
    @property
    def contract(self) -> ToolContract:
        return ToolContract(name="fatal", description="fails fatally")

    def invoke(self, arguments: Mapping[str, Any]) -> ToolResult:
        return ToolResult(
            output="PermissionError: denied",
            is_error=True,
            recoverable=False,
        )


class _FailurePlugin(Plugin):
    id = "failure-fakes"

    def __init__(self, llm: LLMProvider, failing: Tool) -> None:
        self._llm = llm
        self._failing = failing

    def declare_capabilities(self) -> list[Capability]:
        return [self._llm, self._failing, _EchoTool()]


def test_run_recovers_from_recoverable_failure() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": false, "nodes":[{"id":"read",'
            '"capability":"tool:flaky","parameters":{"path":"README.md"}}]}',
            '{"needs_more_info": false, "nodes":[{"id":"list",'
            '"capability":"tool:echo"}]}',
        ]
    )
    core = build_core(
        plugins=[_FailurePlugin(llm, _RecoverableFailTool()), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "recuperação 1/3" in text
        assert "[iteração 2]" in text
        assert "[FAILED]" in llm.prompts[1]
        assert '"path": "README.md"' in llm.prompts[1]
    finally:
        core.shutdown()


def test_run_stops_on_fatal_failure() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": false, "nodes":[{"id":"read",'
            '"capability":"tool:fatal","parameters":{"path":"x"}}]}',
            '{"needs_more_info": false, "nodes":[{"id":"list",'
            '"capability":"tool:echo"}]}',
        ]
    )
    core = build_core(
        plugins=[_FailurePlugin(llm, _FatalFailTool()), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "falha não recuperável" in text
        assert len(llm.prompts) == 1
    finally:
        core.shutdown()


def test_run_stops_on_repeated_failure() -> None:
    repeated = (
        '{"needs_more_info": false, "nodes":[{"id":"read",'
        '"capability":"tool:flaky","parameters":{"path":"README.md"}}]}'
    )
    llm = _ScriptedPlanLLM([repeated, repeated])
    core = build_core(
        plugins=[_FailurePlugin(llm, _RecoverableFailTool()), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "recuperação 1/3" in text
        assert "falha repetida; sem progresso" in text
        assert len(llm.prompts) == 2
    finally:
        core.shutdown()


def test_run_recovers_from_invalid_plan() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": true, "nodes":[{"id":"list","capability":"tool:echo"}]}',
            '{"nodes":[{"id":"read","capability":"tool:echo"}],'
            ' "edges":[{"source":"n1","target":"read"}]}',
            '{"needs_more_info": false, "nodes":[{"id":"read","capability":"tool:echo"}]}',
        ]
    )
    core = build_core(
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "plano inválido descartado" in text
        assert "recuperação 1/3" in text
        assert "[iteração 3]" in text
        # the gathered history survives the discarded plan
        assert "echo-output" in llm.prompts[2]
        assert "rejected plan" in llm.prompts[2]
    finally:
        core.shutdown()


def test_run_stops_on_repeated_invalid_plan() -> None:
    invalid = (
        '{"nodes":[{"id":"read","capability":"tool:echo"}],'
        ' "edges":[{"source":"n1","target":"read"}]}'
    )
    llm = _ScriptedPlanLLM([invalid, invalid])
    core = build_core(
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "plano inválido descartado" in text
        assert "erro de plano repetido" in text
        assert len(llm.prompts) == 2
    finally:
        core.shutdown()


def test_run_honors_max_iterations_budget() -> None:
    llm = _ScriptedPlanLLM(
        ['{"needs_more_info": true, "nodes":[{"id":"list","capability":"tool:echo"}]}']
    )
    config = CoreConfig(budgets=ExecutionBudgets(max_iterations=1))
    core = build_core(
        config=config,
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "[iteração 1]" in text
        assert "[iteração 2]" not in text
        assert "limite de iterações (1) atingido" in text
    finally:
        core.shutdown()


def test_run_injects_session_history() -> None:
    llm = _ScriptedPlanLLM(
        ['{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}']
    )
    core = build_core(
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        session = ChatSession(_EchoLLM(), stream=False)
        session.send("contexto anterior importante")
        result = handle_command("/run resuma", core=core, session=session)
        assert result is not None
        assert "Conversation history" in llm.prompts[0]
        assert "contexto anterior importante" in llm.prompts[0]
    finally:
        core.shutdown()


def test_run_auto_compacts_on_context_threshold() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": true, "nodes":[{"id":"list","capability":"tool:echo"}]}',
            '{"needs_more_info": false, "nodes":[{"id":"read","capability":"tool:echo"}]}',
        ]
    )
    synthesizer = _FakeSynthesizer()
    config = CoreConfig(
        budgets=ExecutionBudgets(compaction_chars=5, compaction_keep_last=0)
    )
    core = build_core(
        config=config,
        plugins=[_SynthesisPlugin(llm, synthesizer), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "compactação: 1 observação(ões) resumida(s)" in text
        assert [call.mode for call in synthesizer.calls] == ["compact", "answer"]
    finally:
        core.shutdown()


class _UsagePlanLLM(_ScriptedPlanLLM):
    def complete(
        self,
        messages: Sequence[Message],
        *,
        on_chunk: LLMChunkCallback | None = None,
        **options: Any,
    ) -> LLMResponse:
        response = super().complete(messages, on_chunk=on_chunk, **options)
        return LLMResponse(
            message=response.message,
            usage=LLMUsage(prompt_tokens=5, completion_tokens=6, total_tokens=11),
        )


def test_run_reports_usage() -> None:
    llm = _UsagePlanLLM(
        ['{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}']
    )
    core = build_core(
        plugins=[_IterativePlugin(llm), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "uso: prompt=5 completion=6 total=11" in text
    finally:
        core.shutdown()


class _LongSynthesizer(Synthesizer):
    @property
    def name(self) -> str:
        return "long-synth"

    def synthesize(self, request: SynthesisRequest) -> Synthesis:
        return Synthesis(text="\n".join(f"linha {index}" for index in range(120)))


def test_run_prints_full_synthesized_answer() -> None:
    llm = _ScriptedPlanLLM(
        ['{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}']
    )
    core = build_core(
        plugins=[_SynthesisPlugin(llm, _LongSynthesizer()), LLMPlannerPlugin()],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "resposta: [long-synth]" in text
        assert "linha 119" in text
        assert "output truncated" not in text
    finally:
        core.shutdown()


class _ScriptedValidator(Validator):
    def __init__(self, verdicts: list[ValidationResult]) -> None:
        self._verdicts = list(verdicts)
        self.inputs: list[ValidationInput] = []

    @property
    def name(self) -> str:
        return "scripted-validator"

    def validate(self, data: ValidationInput) -> ValidationResult:
        self.inputs.append(data)
        index = min(len(self.inputs) - 1, len(self._verdicts) - 1)
        return self._verdicts[index]


class _ValidatorPlugin(Plugin):
    id = "validator-fakes"

    def __init__(self, llm: LLMProvider, validator: Validator) -> None:
        self._llm = llm
        self._validator = validator

    def declare_capabilities(self) -> list[Capability]:
        return [self._llm, _EchoTool(), self._validator]


def test_run_replans_when_validation_fails() -> None:
    llm = _ScriptedPlanLLM(
        [
            '{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}',
            '{"needs_more_info": false, "nodes":[{"id":"n2","capability":"tool:echo"}]}',
        ]
    )
    validator = _ScriptedValidator(
        [ValidationResult(passed=False, messages=("faltou o README",))]
    )
    core = build_core(
        plugins=[_ValidatorPlugin(llm, validator), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "validação não atendida: scripted-validator: faltou o README" in text
        assert "recuperação 1/3" in text
        assert "[iteração 2]" in text
        # the validator saw the whole outcome
        assert validator.inputs[0].observations
    finally:
        core.shutdown()


def test_run_reports_when_validation_never_passes() -> None:
    llm = _ScriptedPlanLLM(
        ['{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}']
    )
    validator = _ScriptedValidator(
        [ValidationResult(passed=False, messages=("sempre falta",))]
    )
    core = build_core(
        plugins=[_ValidatorPlugin(llm, validator), LLMPlannerPlugin()], discoverers=[]
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "validação falhou de novo; sem progresso" in text
    finally:
        core.shutdown()


def test_run_passes_validation_and_synthesizes() -> None:
    llm = _ScriptedPlanLLM(
        ['{"needs_more_info": false, "nodes":[{"id":"n1","capability":"tool:echo"}]}']
    )
    validator = _ScriptedValidator([ValidationResult(passed=True)])
    core = build_core(
        plugins=[
            _ValidatorPlugin(llm, validator),
            LLMSynthesizerPlugin(),
            LLMPlannerPlugin(),
        ],
        discoverers=[],
    )
    try:
        result = handle_command("/run resuma", core=core, session=None)
        assert result is not None
        text = "\n".join(result.output)
        assert "resposta: [llm-synthesizer]" in text
        assert "validação não atendida" not in text
    finally:
        core.shutdown()
