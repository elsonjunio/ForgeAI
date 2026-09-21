# Arquitetura e limites

Documento canônico das **fronteiras de responsabilidade** e dos **limites atuais**
do `core-agent`.

Este documento deve ser atualizado sempre que o comportamento ou os contratos
do Core mudarem.

A regra é:

> **Descrever exatamente o que o código faz hoje, sem prometer o que ainda não existe.**

*Última revisão: `core-agent` 0.1.0.*

### TL;DR

- Core = contratos + registry + lifecycle + runtimes; LangGraph só em
  `core/agent/runtime.py` e `core/agent/graph.py`.
- **Planner** (plugin) decide *o que*; **GraphBuilder** converte plano → grafo;
  **NodeRunner/PlanExecutor** executam; plugins fornecem capabilities.
- **Zero plugins** funciona; o host fornece histórico, interação e políticas.
- Limites: sem checkpoint/resume, planos são DAGs, LLM síncrono, sem
  tool-calling/memória/RAG/sandbox (ver §34).

---

# 1. Princípio arquitetural

O ForgeAI é um monorepo que fornece um **Core extensível para Code Agents**.

A arquitetura separa três responsabilidades principais:

```text
CORE
  = contratos
  + registry
  + lifecycle
  + execution runtime
  + graph construction
  + mecanismos de extensão

PLUGIN
  = capabilities
  + strategies
  + domain behavior

HOST / APPLICATION
  = execution session
  + history
  + interaction
  + application policies
```

O princípio fundamental é:

> **O Core define como extensões funcionam; os plugins definem o que o sistema faz.**

O Core não possui implementações concretas de domínio.

Não existem no Core implementações de:

* LLM;
* planner;
* complexity evaluator;
* tool;
* filesystem;
* Git;
* shell;
* code analyzer;
* memory;
* RAG;
* CLI;
* sandbox;
* política de permissões.

Esses comportamentos devem ser fornecidos por plugins ou pela aplicação
hospedeira, conforme sua natureza.

### Regra de alocação

> Se uma decisão é específica do domínio, da estratégia ou da aplicação,
> ela pertence a um plugin ou ao host.
>
> Se algo é necessário para executar extensões de forma uniforme,
> pertence ao Core.

---

# 2. Matriz de responsabilidades

| Componente               | Responsabilidade                                                                                                      | Define estratégia/domínio? | Conhece LangGraph? | Conhece implementações concretas? |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------- | :------------------------: | :----------------: | :-------------------------------: |
| **Core**                 | Contratos, registry, lifecycle, estado/contexto de execução, construção e execução de planos e mecanismos de extensão |              ❌             |    Parcialmente    |        ⚠️ Mecanismos       |
| **Core Contracts**       | Modelos, interfaces e `Protocol`s públicos                                                                            |              ❌             |          ❌         |                 ❌                 |
| **Plugin**               | Fornecer capacidades e comportamento específico                                                                       |              ✅             |          ❌         |                 —                 |
| **Capability**           | Representar/executar uma capacidade disponibilizada por um plugin                                                     |      ✅ No seu domínio      |          ❌         |                 —                 |
| **Plugin Registry**      | Registrar, descobrir, inicializar, encerrar e resolver plugins, capabilities, grupos e planners                       |              ❌             |          ❌         |                 ❌                 |
| **Group**                | Organizar capabilities/plugins por domínio, com associação many-to-many                                               |              ❌             |          ❌         |                 ❌                 |
| **Planner Plugin**       | Transformar uma solicitação em um `ExecutionPlan`                                                                     |              ✅             |          ❌         |    ⚠️ Via contratos/descriptors   |
| **Group Planner**        | Estratégia de planejamento especializada em um grupo                                                                  |              ✅             |          ❌         |    ⚠️ Via contratos/descriptors   |
| **Main Planner**         | Estratégia de planejamento global que pode coordenar planners especializados                                          |              ✅             |          ❌         |          ⚠️ Via contratos         |
| **Complexity Evaluator** | Avaliar complexidade e fornecer uma estratégia/indicação para planejamento                                            |              ✅             |          ❌         |          ⚠️ Via contratos         |
| **ExecutionPlan**        | Representar o que deve ser executado e suas dependências                                                              |              ❌             |          ❌         |                 ❌                 |
| **GraphBuilder**         | Validar estruturalmente e transformar `ExecutionPlan` em grafo LangGraph                                              |              ❌             |          ✅         |                 ❌                 |
| **NodeRunner**           | Resolver capabilities, adaptar executáveis/tools, executar nodes, aplicar retry e controle                            |              ❌             |       ⚠️ Módulo      |                 ❌                 |
| **PlanExecutor**         | Orquestrar build, execução e finalização de um `ExecutionPlan`                                                        |              ❌             |          ✅         |                 ❌                 |
| **AgentRuntime**         | Executar o runtime genérico baseado em `NodeContribution`s                                                            |              ❌             |          ✅         |                 ❌                 |
| **LLM Provider Plugin**  | Fornecer acesso a um modelo de linguagem                                                                              |        ✅ No provider       |          ❌         |                 —                 |
| **Tool Plugin**          | Disponibilizar uma operação executável                                                                                |       ✅ Na ferramenta      |          ❌         |                 —                 |
| **Validator Plugin**     | Fornecer estratégia de validação                                                                                      |              ✅             |          ❌         |                 —                 |
| **Code Analyzer Plugin** | Fornecer análise de código                                                                                            |              ✅             |          ❌         |                 —                 |
| **Discoverer Plugin**    | Fornecer estratégia de descoberta                                                                                     |              ✅             |          ❌         |                 —                 |
| **Memory**               | Gerenciar memória específica de uma execução ou capacidade                                                            |              ✅             |          ❌         |                 —                 |
| **Application / Host**   | Iniciar sessões, selecionar extensões, fornecer contexto/histórico e definir políticas da aplicação                   |              ✅             |      Opcional      |                 ✅                 |
| **Interaction Provider** | Abstrair interação entre execução e usuário/UI                                                                        |              ❌             |          ❌         |                 ❌                 |

### Observações

* **Core** refere-se ao pacote como um todo.
* A camada `core.contracts` não conhece LangGraph.
* `core.contracts` não importa plugins em runtime; a única exceção é o tipo
  `Plugin` importado sob `TYPE_CHECKING` em `core/contracts/discovery.py`.
* `core.contracts` **importa** `core.agent.state` (`AgentState`/`Message`/
  `now_utc`) — exceção conhecida ao modelo "contracts puro" (ver §29).
* Somente `core.agent.runtime` e `core.agent.graph` importam LangGraph/LangChain.
* `Planner`, `ComplexityEvaluator`, `LLMProvider`, `Tool`, `Validator`,
  `CodeAnalyzer` e `Discoverer` são contratos do Core, não implementações
  concretas.
* `Main Planner` e `Group Planner` são papéis que podem ser implementados por
  plugins; não são componentes concretos fornecidos pelo Core.
* O Core não decide a estratégia de planejamento.
* O `GraphBuilder` não decide o plano; apenas transforma o plano em uma
  representação executável.
* O `PlanExecutor` não decide o que fazer; executa o plano recebido.
* `EntryPointDiscoverer` é infraestrutura de descoberta do Core, não uma
  capability de domínio.
* Memory e Complexity Evaluator não possuem implementação concreta no Core.
* Application/CLI ainda não existe no repositório.

---

# 3. Regras de alocação

| Se a responsabilidade...                                    | Deve ficar em                                         |
| ----------------------------------------------------------- | ----------------------------------------------------- |
| Define um contrato que qualquer implementação deve obedecer | **Core**                                              |
| É necessária para executar extensões uniformemente          | **Core**                                              |
| É uma decisão sobre como resolver uma tarefa                | **Plugin / Planner**                                  |
| É uma estratégia de planejamento                            | **Planner Plugin**                                    |
| É uma estratégia de avaliação de complexidade               | **Complexity Evaluator Plugin**                       |
| É uma integração com tecnologia externa                     | **Plugin**                                            |
| É uma capability de domínio                                 | **Plugin**                                            |
| É memória de uma execução                                   | **Plugin / Execution Context**, conforme a estratégia |
| É histórico entre execuções                                 | **Application / Host**                                |
| É decisão sobre quais histórico/contexto fornecer           | **Application / Host**                                |
| É interação com o usuário                                   | **Application / Interaction Provider**                |
| É transformação de um plano em execução LangGraph           | **Core / GraphBuilder**                               |
| É resolução e execução de capabilities                      | **Core / Runtime**                                    |
| É decisão sobre *o que* executar                            | **Planner Plugin**                                    |
| É decisão sobre *como* executar um plano já definido        | **Core / Runtime**                                    |
| É política específica da aplicação                          | **Application / Host**                                |
| É política de domínio                                       | **Plugin**                                            |

---

# 4. Fluxo arquitetural

O fluxo principal do plan runtime é:

```text
Application / Host
        │
        │ Request + contexto
        ▼
 Planner Plugin
        │
        │ PlanningResult
        ▼
 ExecutionPlan
        │
        ▼
 GraphBuilder
        │
        │ LangGraph
        ▼
    PlanExecutor
        │
        ▼
    NodeRunner
        │
        │ resolve
        ▼
 PluginRegistry
        │
        ▼
   Capabilities
        │
        ▼
 ExecutionResult
```

A separação fundamental é:

```text
Planner
    │
    │ decide O QUE fazer
    ▼
ExecutionPlan
    │
    │ descreve o plano
    ▼
GraphBuilder
    │
    │ transforma em execução
    ▼
LangGraph
    │
    │ executa
    ▼
PlanExecutor
```

O Planner não conhece LangGraph.

O `ExecutionPlan` não conhece LangGraph.

O GraphBuilder conhece LangGraph.

O Runtime executa o plano.

---

# 5. Plugins

Um plugin é uma extensão do Core que fornece capacidades ou estratégias
concretas.

A direção de dependência é:

```text
Plugin
   │
   ▼
core-agent
```

e não:

```text
core-agent
   │
   ▼
Plugin concreto
```

O Core não deve importar um plugin específico.

Plugins são descobertos através de Python entry points:

```text
core_agent.plugins
```

O mecanismo de descoberta é responsabilidade do Core, mas o conteúdo dos
plugins pertence aos pacotes externos.

### Exemplo conceitual

```text
packages/
├── core/
│   └── core-agent
│
└── plugins/
    ├── forge-plugin-openai
    ├── forge-plugin-lmstudio
    ├── forge-plugin-filesystem
    ├── forge-plugin-git
    └── forge-plugin-python
```

Esses plugins são exemplos arquiteturais e não fazem parte atualmente do Core.

---

# 6. Capabilities

Uma `Capability` representa uma capacidade disponibilizada por um plugin.

Exemplos possíveis:

```text
LLM
Tool
Planner
Validator
CodeAnalyzer
Discoverer
```

Uma capability não é equivalente a um plugin.

Um plugin pode fornecer várias capabilities.

```text
Plugin
 ├── Capability A
 ├── Capability B
 └── Capability C
```

Também é possível que capabilities diferentes pertençam a diferentes grupos.

O registry identifica capabilities através de:

```text
(kind, name)
```

Esse identificador deve ser único no registry.

---

# 7. CapabilityDescriptor

Capabilities possuem descriptors para permitir descoberta e planejamento sem
expor sua implementação.

Um descriptor representa informações como:

* identificador;
* nome;
* descrição;
* tipo;
* grupos;
* parâmetros;
* constraints;
* metadata.

O descriptor não deve conter detalhes desnecessários da implementação.

O objetivo é permitir que um planner responda perguntas como:

```text
Quais capacidades existem?
O que elas fazem?
A que grupo pertencem?
Que parâmetros aceitam?
```

sem precisar conhecer a implementação concreta.

---

# 8. Grupos

Plugins e capabilities podem pertencer a múltiplos grupos.

A relação é many-to-many.

Exemplo:

```text
Filesystem
 ├── filesystem
 └── code

Git
 ├── code
 ├── project
 └── version-control

Python
 ├── code
 └── execution
```

O grupo não representa um plugin.

O grupo é uma classificação utilizada para organizar capacidades e fornecer
contexto para estratégias de planejamento.

O Core fornece o mecanismo de agrupamento, mas não define quais grupos devem
existir.

---

# 9. Planners

`Planner` é um contrato do Core e uma capability fornecida por plugins.

O Core não possui um planner padrão.

Um planner recebe uma solicitação de planejamento e produz um
`PlanningResult`, contendo um `ExecutionPlan`.

Conceitualmente:

```text
PlanningRequest
       │
       ▼
     Planner
       │
       ▼
PlanningResult
       │
       ▼
ExecutionPlan
```

Um planner pode internamente utilizar:

* LLM;
* regras;
* heurísticas;
* DAGs;
* outros planners;
* múltiplos modelos;
* qualquer combinação dessas estratégias.

Essas decisões não pertencem ao Core.

### Planner e LangGraph

O Planner não conhece LangGraph.

O contrato de planejamento deve permanecer independente do mecanismo de
execução.

Isso permite que um planner seja reutilizado com diferentes mecanismos de
execução ou testado isoladamente.

---

# 10. Planners especializados

A arquitetura permite que plugins forneçam planners especializados.

Conceitualmente:

```text
Main Planner
    │
    ├── Code Planner
    ├── Filesystem Planner
    └── Execution Planner
```

Esses componentes não são implementações do Core.

São estratégias que podem ser fornecidas por plugins.

Um planner global pode utilizar descriptors de planners especializados e
delegar parte do planejamento.

O Core apenas fornece:

* registro;
* descoberta;
* descriptors;
* escopos;
* execução do plano resultante.

A estratégia de coordenação pertence ao plugin.

---

# 11. Complexity Evaluator

`ComplexityEvaluator` é um contrato.

Não existe uma implementação concreta no Core.

Sua finalidade é permitir que uma aplicação/planner avalie uma solicitação e
decida qual estratégia de planejamento utilizar.

Exemplos conceituais:

```text
Request
   │
   ▼
ComplexityEvaluator
   │
   ├── estratégia simples
   ├── estratégia complexa
   └── estratégia especializada
```

O Core não impõe:

* algoritmo;
* threshold;
* heurística;
* modelo;
* classificação.

Tudo isso pertence à implementação fornecida pelo plugin/host.

---

# 12. ExecutionPlan

`ExecutionPlan` representa uma sequência ou estrutura de operações que o Core
deve executar.

O plano é composto por:

```text
ExecutionPlan
 ├── PlanNode
 └── PlanEdge
```

`PlanNode` representa uma unidade de execução.

`PlanEdge` representa uma dependência entre nodes.

Nodes referenciam capabilities através dos identificadores resolvíveis pelo
registry.

O plano não contém implementações concretas.

---

# 13. GraphBuilder

O `GraphBuilder` é responsável por transformar um `ExecutionPlan` em um grafo
LangGraph executável.

Suas responsabilidades são:

1. validar o plano;
2. validar referências;
3. resolver a estrutura necessária para construção;
4. criar os nodes LangGraph;
5. criar as edges;
6. produzir o grafo compilável.

O `GraphBuilder` **não executa capabilities**.

O `GraphBuilder` **não emite eventos de execução**.

O `GraphBuilder` **não decide a estratégia de planejamento**.

A validação de referências (`validate`) consulta o `NodeRunner`, que resolve a
capability no registry; portanto, uma capability ausente ou não executável falha
**antes** de qualquer execução (`MissingCapabilityError`/
`UnsupportedCapabilityError`).

A separação é:

```text
ExecutionPlan
      │
      ▼
GraphBuilder
      │
      ▼
LangGraph
```

---

# 14. NodeRunner

O `NodeRunner` é responsável pela execução individual dos nodes.

Suas responsabilidades incluem:

* resolver a capability;
* adaptar `Executable`/`Tool` quando necessário;
* executar a operação;
* aplicar retry;
* aplicar controle de execução;
* produzir `NodeResult`;
* emitir eventos de node.

O `NodeRunner` não escolhe qual capability deve ser usada.

Essa decisão já está representada pelo `ExecutionPlan`.

---

# 15. PlanExecutor

O `PlanExecutor` coordena a execução de um plano.

Seu fluxo atual é:

```text
validate
   │
   ▼
build
   │
   ▼
run
   │
   ▼
finalize
```

Ele é responsável por:

* validar o `ExecutionPlan`;
* chamar o `GraphBuilder`;
* executar o grafo;
* coletar resultados;
* produzir `ExecutionResult`;
* emitir eventos de execução.

O `PlanExecutor` não contém estratégia de planejamento.

---

# 16. Generic Node Runtime

Além do Plan Runtime, o Core possui um runtime genérico baseado em
`NodeContribution`.

Esse runtime é implementado por:

```text
AgentRuntime
```

Seu fluxo é:

```text
START
  │
  ▼
__core_init__
  │
  ▼
n1
  │
  ▼
n2
  │
  ▼
...
  │
  ▼
nn
  │
  ▼
END
```

Plugins podem contribuir nodes que transformam `AgentState`.

O `AgentRuntime` expõe:

```text
run()
arun()
```

Esse runtime é distinto do Plan Runtime.

---

# 17. Dois runtimes

O Core atualmente possui dois mecanismos de execução.

| Runtime                  | Componente                                     | Finalidade                                           |
| ------------------------ | ---------------------------------------------- | ---------------------------------------------------- |
| **Generic Node Runtime** | `AgentRuntime`                                 | Executar nodes contribuídos diretamente por plugins  |
| **Plan Runtime**         | `GraphBuilder` + `NodeRunner` + `PlanExecutor` | Executar um `ExecutionPlan` produzido por um planner |

### Generic Node Runtime

```text
NodeContribution
       │
       ▼
AgentRuntime
       │
       ▼
LangGraph
```

### Plan Runtime

```text
Planner
   │
   ▼
ExecutionPlan
   │
   ▼
GraphBuilder
   │
   ▼
LangGraph
   │
   ▼
PlanExecutor
```

Os dois runtimes utilizam LangGraph, mas possuem responsabilidades diferentes.

---

# 18. ExecutionContext

`ExecutionContext` representa o contexto da execução atual.

Ele permite transportar informações como:

* request;
* state;
* metadata;
* capabilities;
* histórico fornecido pelo host;
* informações necessárias aos plugins.

O Core não busca automaticamente histórico.

A aplicação decide se uma execução deve receber contexto anterior.

Conceitualmente:

```text
Application / Host
       │
       │ history/context
       ▼
ExecutionContext
       │
       ▼
Execution
```

O histórico entre execuções não pertence ao Core.

---

# 19. Memory e histórico

O Core atualmente **não possui implementação de Memory**.

Também não possui:

* vector store;
* embeddings;
* RAG;
* memória persistente;
* recuperação automática de histórico.

O histórico pode ser fornecido explicitamente pelo host através do
`ExecutionContext`.

Isso permite que diferentes aplicações adotem estratégias diferentes sem
acoplar o Core a uma solução de memória.

---

# 20. LLM Provider

`LLMProvider` é um contrato.

A implementação pertence a um plugin.

O Core não conhece:

* OpenAI;
* Anthropic;
* Ollama;
* LM Studio;
* modelos locais;
* APIs HTTP específicas.

O contrato suporta uma resposta acumulada e chunks observacionais.

Conceitualmente:

```text
LLM Provider
     │
     ├── chunk ─────────► Observer / callback
     │
     └── accumulated
             │
             ▼
        LLMResponse
```

O runtime utiliza a resposta acumulada.

O streaming atualmente não é utilizado pelo Core como mecanismo de controle
da execução.

---

# 21. Tool

`Tool` representa uma operação executável disponibilizada por uma extensão.

O Core possui o contrato e adaptadores necessários para sua execução no Plan
Runtime.

O Core não possui tools concretas.

Exemplos possíveis de plugins futuros:

```text
filesystem
git
shell
python
docker
database
http
```

Nenhuma dessas capacidades é fornecida atualmente pelo Core.

---

# 22. Interaction Provider

`InteractionProvider` é uma abstração para interação entre a execução e o
host/usuário.

Pode ser utilizada futuramente para situações como:

```text
"Confirmar operação?"
"Qual arquivo devo modificar?"
"Autorizar esta ação?"
```

O Core não conhece:

* terminal;
* stdin;
* HTTP;
* WebSocket;
* GUI;
* Web UI.

A aplicação fornece a implementação.

O provider é opcional.

Quando não fornecido, seu valor é `None`.

A responsabilidade por tratar essa ausência pertence ao plugin/capability que
necessita da interação.

---

# 23. Callbacks e observabilidade

O Core fornece mecanismos de observação e controle da execução.

Entre os eventos/contratos existentes estão:

* execution start;
* execution complete;
* node start;
* node complete;
* erro;
* controle da execução;
* chunks de LLM.

O mecanismo de callback permite que o host acompanhe a execução sem que o Core
precise conhecer a interface utilizada.

Exemplos de consumidores:

```text
CLI
Web UI
IDE
Logging
Testing
Tracing futuro
```

A aplicação pode utilizar callbacks para observar ou controlar uma execução.

---

# 24. Execution Control

O Core possui `ExecutionControl` com estados como:

```text
CONTINUE
PAUSE
INTERRUPT
RETRY
```

Atualmente, `PAUSE` e `INTERRUPT` não representam checkpoint persistente.

A execução atual é encerrada e não existe mecanismo de resume.

Não existe atualmente:

* checkpoint;
* persistência de state;
* replay;
* recuperação de execução.

---

# 25. Plugin lifecycle

O lifecycle atual é:

```text
register()
    │
    ▼
load()
    │
    ▼
activate_all()
    │
    ├── declare_groups()
    ▼
initialize(context)
    │
    ▼
declare_capabilities()
    │
    ▼
running
    │
    ▼
deactivate_all()
    │
    ▼
shutdown()
```

O shutdown ocorre em ordem reversa.

Plugins desabilitados através da configuração não são registrados.

---

# 26. Capability resolution

Capabilities são identificadas por:

```text
(kind, name)
```

O registry garante unicidade desse identificador.

A resolução de uma capability default segue:

```text
CoreConfig.defaults
       │
       ▼
default = True
       │
       ▼
único provider
       │
       ├── encontrado → resolve
       ├── nenhum → None
       └── múltiplos → Ambiguous
```

O Core não escolhe arbitrariamente entre múltiplos providers.

---

# 27. Grupos e resolução

Capabilities e plugins podem declarar grupos.

Exemplo:

```text
Capability: git.commit

Groups:
  code
  project
  version-control
```

O registry mantém a associação many-to-many.

Ele fornece mecanismos para consultar:

* grupos;
* capabilities de um grupo;
* plugins de um grupo;
* planners associados a um grupo.

O registry não define a estratégia de utilização desses grupos.

---

# 28. Configuração

O Core possui `CoreConfig`.

A configuração pode ser carregada a partir de:

* `None`;
* mapping;
* arquivo JSON.

Atualmente não existe suporte nativo a:

* TOML;
* YAML.

Modelos de contrato utilizam `extra="forbid"` quando aplicável.

Dados livres devem ser colocados em `metadata`.

`AgentState` e `Message` também usam `extra="forbid"`.

Identificadores reservados:

* planos não podem usar `__start__`/`__end__` (senão `InvalidPlanError`);
* o generic node runtime reserva `__core_init__` (senão `InvalidGraphError`).

---

# 29. Camadas e dependências

A estrutura lógica do Core é:

```text
core.contracts
       │
       ▼
core.agent
       │
       ├── runtime.py
       └── graph.py
       │
       ▼
core.plugins
       │
       ▼
core.events
       │
       ▼
core.config
       │
       ▼
core.runtime
```

Mais precisamente:

```text
core.contracts
  └── modelos e interfaces

core.agent
  └── state + runtimes + GraphBuilder

core.plugins
  └── Plugin + Registry + discovery + lifecycle

core.events
  └── EventBus + CoreEvents

core.config
  └── CoreConfig + loader

core.runtime
  └── build_core + CoreContainer
```

### Regras de dependência

* `core.contracts` não importa LangGraph/LangChain.
* `core.contracts` não importa plugins em runtime (exceção: o tipo `Plugin` sob
  `TYPE_CHECKING` em `core/contracts/discovery.py`).
* `core.contracts` **importa** `core.agent.state` (`AgentState`/`Message`/
  `now_utc`) — exceção conhecida; `core.agent.state` não importa contracts, então
  não há ciclo de módulo.
* `core.agent.*` depende de contracts.
* `core.agent.*` não depende de `core.plugins.*`.
* `core.plugins` não importa `core.agent`.
* `PluginRegistry` não depende dos runtimes.
* LangGraph/LangChain só são importados por:

  * `core/agent/runtime.py`
  * `core/agent/graph.py`
* Plugins dependem do `core-agent`, nunca o contrário.
* O host depende do Core e pode instalar plugins.

---

# 30. Composition Root

`build_core` e `CoreContainer` representam a composição do Core.

O Core não decide quais extensões utilizar.

O host fornece configuração e plugins.

Conceitualmente:

```text
Application
     │
     ├── configuration
     └── plugins
             │
             ▼
        build_core()
             │
             ▼
       CoreContainer
             │
             ▼
       PluginRegistry
```

O `build_core` apenas realiza o wiring necessário para construir o sistema.

Não existe lógica de domínio nesse processo.

---

# 31. Zero-plugin behavior

O Core deve funcionar sem plugins.

Com zero plugins é possível:

```text
build_core()
     │
     ▼
CoreContainer
     │
     ▼
AgentRuntime
```

Não é necessário:

* LLM;
* planner;
* tool;
* filesystem;
* Git;
* CLI.

Nesse estado não existem capabilities concretas disponíveis, mas o mecanismo
de Core continua inicializável e executável dentro das capacidades nativas
existentes.

---

# 32. Tratamento de erros

Erros relacionados ao plano e suas capabilities são representados através de
exceções específicas.

Entre elas:

```text
InvalidPlanError
MissingCapabilityError
UnsupportedCapabilityError
GraphBuildError
```

Erros de capability durante a execução são representados no resultado do node:

```text
NodeResult.failed
```

e refletem-se no `ExecutionResult`:

```text
status = "completed" | "failed" | "stopped"
success = True somente quando status == "completed"
```

A distinção entre erro de construção e erro de execução deve ser preservada.

---

# 33. Estado atual do Plan Runtime

O fluxo implementado atualmente é:

```text
PlanningRequest
      │
      ▼
Planner Plugin
      │
      ▼
ExecutionPlan
      │
      ▼
validate
      │
      ▼
GraphBuilder
      │
      ▼
LangGraph
      │
      ▼
PlanExecutor
      │
      ▼
NodeRunner
      │
      ▼
PluginRegistry
      │
      ▼
Capability
      │
      ▼
NodeResult
      │
      ▼
ExecutionResult
```

O planner é externo ao Core.

O Core executa o plano produzido.

---

# 34. Limites atuais

Os pontos abaixo **não estão implementados** e não devem ser tratados como
funcionalidades disponíveis.

## 34.1 Checkpoint e resume

Não existe checkpoint persistente.

Atualmente:

```text
PAUSE / INTERRUPT
        │
        ▼
execução encerrada
```

Não existe:

* resume;
* persistência;
* replay;
* recuperação após falha.

---

## 34.2 Ciclos e iteração

Os planos atuais são DAGs.

O Core não interpreta ciclos.

Não existe um loop ReAct fixo.

Não existe um loop de agente implementado diretamente no Core.

Uma estratégia que necessite de iteração deve produzir um plano compatível com
o modelo atual ou implementar sua própria estratégia fora do Core.

---

## 34.3 Paralelismo

As edges do plano podem representar branches paralelos.

Entretanto, o estado de execução atual é:

* mutável;
* compartilhado;
* não serializável;
* não thread-safe;
* não checkpointável.

Portanto, o modelo atual não deve ser interpretado como uma infraestrutura
completa de execução concorrente segura.

---

## 34.4 Falha de node

Uma falha de node interrompe o grafo.

Nodes que já foram concluídos permanecem representados nos resultados.

Isso inclui nodes concluídos em branches anteriores.

Não existe atualmente uma política geral de:

* compensação;
* rollback;
* retomada;
* execução parcial recuperável.

---

## 34.5 LLM assíncrono

`LLMProvider.complete` é síncrono.

Não existe:

```text
LLMProvider.acomplete
```

O `PlanExecutor` também não possui `arun`.

O `AgentRuntime` possui `arun`, mas isso não significa que o Plan Runtime
seja atualmente assíncrono.

---

## 34.6 Streaming

`LLMChunk` e `on_chunk` existem para observabilidade.

O runtime não utiliza chunks para controlar a execução.

A resposta utilizada pelo fluxo é sempre o `LLMResponse` acumulado.

---

## 34.7 Tool calling

O contrato atual de `Message` possui `tool_call_id`, mas não existe
representação completa de `tool_calls`.

Também não existe no Core:

* loop de tool-calling;
* ReAct;
* seleção automática de ferramentas;
* execução iterativa baseada em respostas de ferramentas.

---

## 34.8 Memory e RAG

Não existe implementação de:

* Memory;
* embeddings;
* vector store;
* RAG;
* recuperação automática de contexto.

O histórico deve ser fornecido explicitamente pelo host.

---

## 34.9 Segurança

`CapabilityDescriptor.constraints` é atualmente descritivo.

O Core não aplica essas constraints.

Não existe:

* sandbox;
* allowlist;
* denylist;
* política de permissões;
* isolamento de processo;
* isolamento de filesystem;
* controle de recursos.

---

## 34.10 Interaction Provider

`InteractionProvider` é opcional.

Se o host não fornecer um provider, seu valor será `None`.

Não existe atualmente uma política global do Core para determinar o que fazer
quando uma capability necessita de interação e nenhum provider está
disponível.

---

## 34.11 Multi-agent

Não existe orquestração nativa de múltiplos agentes.

Planners podem utilizar outros planners conforme sua implementação, mas o Core
não fornece:

* handoff;
* delegação automática;
* agent-to-agent messaging;
* hierarquia de agentes;
* supervisão multi-agent.

---

## 34.12 Tracing, tokens e custo

Não existe tracing distribuído.

Não existe contabilização própria de:

* tokens;
* custo;
* latência por provider;
* custo por node;
* custo por execução.

`LLMUsage` e metadata fornecidos pelo provider podem ser transportados, mas não
há agregação/política de custos implementada pelo Core.

---

## 34.13 CLI

Existe um CLI inicial (`apps/cli/`, distribuição `forgeai-cli`, comando
`forgeai`) que hoje serve para **chat** e para **inspeção de plugins**
(`/plugins`, `/capabilities`, `/groups`, `/planners`, `/providers`, `/config`).

O chat usa apenas `LLMProvider.complete`; **não** passa por
planner/`PlanExecutor` ainda. O CLI tem `/plan` (mostra o `ExecutionPlan`) e
`/run` (planeja e executa via `PlanExecutor`), que exigem um plugin de planner
(ex.: `code-agent-plugin-llm-planner`). O CLI é host, não core.

---

## 34.14 Memory entre execuções

O Core não persiste histórico.

O host é responsável por decidir:

```text
execução anterior
       │
       ▼
histórico selecionado
       │
       ▼
nova ExecutionContext
```

Não existe política automática de retenção ou compactação.

---

## 34.15 Formato de configuração

`load_config` atualmente aceita:

* `None`;
* mapping;
* arquivo JSON.

Não existe suporte nativo a TOML/YAML.

---

# 35. Garantias de fronteira

As seguintes propriedades são protegidas por testes arquiteturais:

* `Planner` não importa LangGraph.
* `ExecutionPlan` não importa LangGraph.
* `core.contracts` não importa LangGraph/LangChain.
* LangGraph só é importado por `core/agent/runtime.py` e
  `core/agent/graph.py`.
* `GraphBuilder.build` não executa capabilities.
* `GraphBuilder.build` não emite eventos de execução.
* `Capability != Plugin`.
* `Group != Plugin`.
* `PluginRegistry` não importa `core.agent`.
* `PluginRegistry` não importa `core.runtime`.
* Não existe workflow fixo de agente no Core.
* Não existe ReAct loop no Core.
* Não existe Memory concreta no Core.
* Não existe CLI no Core.
* Não existe planner concreto no Core.
* Não existe LLM provider concreto no Core.
* Não existe tool concreta no Core.
* O Core pode ser construído sem plugins.

Essas garantias são parte da arquitetura, não apenas detalhes de implementação.

Elas são verificadas em
`packages/core/tests/test_architecture_boundaries.py` (imports de LangGraph,
execução/emissão do `GraphBuilder`, separação de tipos) e pelos demais testes de
contratos e execução de planos.

---

# 36. Critério para novas funcionalidades

Antes de adicionar uma nova funcionalidade ao Core, deve-se responder:

### 1. É um contrato?

Se sim, provavelmente pertence ao:

```text
core.contracts
```

### 2. É necessário para executar qualquer plugin de maneira uniforme?

Se sim, provavelmente pertence ao Core.

### 3. É uma estratégia?

Se sim, provavelmente pertence a um plugin.

Exemplos:

```text
estratégia de planejamento
estratégia de memória
estratégia de seleção de tools
estratégia de avaliação
estratégia de retry
```

### 4. É uma integração externa?

Se sim, deve ser considerada como plugin.

### 5. É uma política da aplicação?

Se sim, deve permanecer no host/application.

### 6. É específica do domínio?

Se sim, não deve entrar no Core.

---

# 37. Princípios de isolamento

O Core deve permanecer:

* provider-neutral;
* domain-neutral;
* application-neutral;
* plugin-neutral.

Isso significa que o Core não deve assumir que o sistema utiliza:

* OpenAI;
* Anthropic;
* Ollama;
* LM Studio;
* Git;
* GitHub;
* filesystem local;
* Docker;
* Python;
* shell;
* CLI;
* Web UI;
* IDE.

Essas tecnologias podem ser utilizadas por extensões, mas não devem se tornar
dependências conceituais do Core.

---

# 38. Princípio Planner → Plan → Runtime

A separação entre planejamento e execução é uma das principais invariantes
arquiteturais do sistema.

```text
┌───────────────┐
│    Planner    │
│    Plugin     │
└───────┬───────┘
        │
        │ decide
        ▼
┌───────────────┐
│ ExecutionPlan │
└───────┬───────┘
        │
        │ transforma
        ▼
┌───────────────┐
│ GraphBuilder  │
└───────┬───────┘
        │
        │ constrói
        ▼
┌───────────────┐
│   LangGraph   │
└───────┬───────┘
        │
        │ executa
        ▼
┌───────────────┐
│ PlanExecutor  │
└───────┬───────┘
        │
        │ resolve
        ▼
┌───────────────┐
│   Registry    │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Capabilities  │
└───────────────┘
```

Cada camada possui uma responsabilidade diferente.

Essa separação deve ser preservada mesmo quando novos plugins e estratégias
forem adicionados.

---

# 39. Estrutura atual do monorepo

A estrutura relevante atualmente é:

```text
packages/
└── core/
    ├── src/
    │   └── core/
    │       ├── contracts/
    │       ├── agent/
    │       ├── plugins/
    │       ├── events/
    │       ├── config/
    │       └── runtime/
    ├── tests/
    └── examples/

packages/
└── plugins/
    ├── README.md
    ├── code-agent-plugin-opencode-go/
    │   ├── src/code_agent_plugin_opencode_go/
    │   └── tests/
    └── code-agent-plugin-llm-planner/
        ├── src/code_agent_plugin_llm_planner/
        └── tests/

apps/
└── cli/
    ├── src/forge_cli/
    └── tests/

docs/
├── architecture.md
├── using-the-core.md
├── creating-an-llm-plugin.md
└── creating-plugins.md
```

O repositório também possui:

```text
scripts/build_packages.py
.github/workflows/
├── ci.yml
└── release.yml
```

---

# 40. Qualidade atual

O Core atualmente possui:

* 178 testes unitários e de integração;
* `ruff check .` limpo;
* `mypy --strict` aplicado;
* CI para Python 3.10–3.12;
* workflow de release baseado em tags;
* empacotamento wheel + sdist em ZIP;
* release `v0.1.0`.

O pacote não depende de publicação no PyPI para ser utilizado.

---

# 41. Empacotamento e release

O script:

```text
scripts/build_packages.py
```

gera artefatos por pacote.

O fluxo atual é:

```text
tag v*
   │
   ▼
GitHub Actions
   │
   ▼
build_packages.py
   │
   ├── wheel
   └── sdist
        │
        ▼
      ZIP
        │
        ▼
GitHub Release
```

O release atual é:

```text
v0.1.0
```

---

# 42. API pública

O pacote atualmente expõe uma facade pública relativamente ampla, com
aproximadamente 85 nomes exportados.

A API pode ser enxugada em versões futuras.

Enquanto isso, alterações nos exports públicos devem ser consideradas
mudanças de API e avaliadas com cuidado.

---

# 43. Próximas extensões

As seguintes funcionalidades são extensões futuras e **não fazem parte do
Core atual**:

1. plugin de **tool** de exemplo (já existem plugins de **LLM** e **planner**:
   `packages/plugins/code-agent-plugin-opencode-go` e
   `code-agent-plugin-llm-planner`);
2. execução via planner/`PlanExecutor` no CLI (o chat já existe em
   `apps/cli`);
3. tool calling;
4. loop de tool-calling;
5. sandbox;
6. permissões;
7. memória;
8. checkpoint;
9. resume;
10. tracing;
11. contabilização de tokens/custos;
12. estratégias multi-agent.

A implementação dessas funcionalidades deve preservar as fronteiras descritas
neste documento.

Em particular:

> A existência de uma funcionalidade no ecossistema ForgeAI não implica que
> ela deva ser implementada dentro do Core.

---

# 44. Regra final de arquitetura

A regra mais importante para evolução do projeto é:

> **Se uma decisão pode ser específica para uma aplicação, domínio ou
> estratégia, ela não deve ser embutida no Core.**

O Core deve permanecer responsável por fornecer o **protocolo e o mecanismo de
execução**.

Plugins devem fornecer **capacidades e estratégias**.

A aplicação deve fornecer **contexto, sessão, interação e políticas próprias**.

Em termos resumidos:

```text
                 WHAT TO DO
                     │
                     ▼
              ┌──────────────┐
              │    PLUGIN    │
              │   PLANNER    │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ EXECUTION    │
              │    PLAN      │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │     CORE     │
              │ GRAPH/RUNTIME│
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ CAPABILITIES │
              │   PLUGINS    │
              └──────────────┘
```

**Planner decide. Core executa. Plugins fornecem capacidades. Host fornece a
sessão e o contexto.**
