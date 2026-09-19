"""Exemplo mínimo e executável do core (zero plugins + um plugin).

Rodar pelo terminal::

    .venv/bin/python examples/hello_core.py

Ou no VS Code: pressione **F5** com a configuração ``Python: exemplo core``.
"""

from __future__ import annotations

from core import AgentState, NodeContract, NodeContribution, Plugin, build_core


class UppercasePlugin(Plugin):
    """Contribui um nó que transforma a task em MAIÚSCULAS."""

    id = "uppercase"
    version = "0.1.0"

    def declare_nodes(self) -> list[NodeContribution]:
        def node(state: AgentState) -> AgentState:
            return state.model_copy(update={"output": (state.task or "").upper()})

        return [NodeContribution(contract=NodeContract(id="uppercase"), node=node)]


def main() -> None:
    # Zero plugins: o grafo se reduz à inicialização do estado.
    core = build_core()
    print("nodes (zero plugins):", core.node_ids)
    final = core.runtime.run(task="refatore este arquivo")
    print("status:", final.status)
    print("output:", final.output)
    core.shutdown()

    # Um plugin contribui um nó de transformação.
    core = build_core(plugins=[UppercasePlugin()])
    print("nodes (com plugin):", core.node_ids)
    final = core.runtime.run(task="refatore este arquivo")
    print("status:", final.status)
    print("output:", final.output)
    core.shutdown()


if __name__ == "__main__":
    main()
