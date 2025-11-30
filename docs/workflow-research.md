# Agent Framework Workflow Research & Integration Plan

## 1. What Workflows Provide

Microsoft's `agent-framework` package ships with a full workflow engine under `agent_framework._workflows`. Key building blocks that matter for the RFP copilot:

| Concept | Purpose | Notes for RFP Copilot |
| --- | --- | --- |
| `WorkflowBuilder` + `Workflow` | Graph engine that executes connected executors in supersteps, supports streaming, checkpoints, and nesting. | Lets us assemble multi-agent orchestration declaratively instead of imperative session code. |
| `AgentExecutor` | Wraps a `ChatAgent` (or any `AgentProtocol`) so it can run inside a workflow. Automatically emits streaming `AgentRunUpdateEvent` tokens when the workflow is in streaming mode. | Direct replacement for the custom `AgentFrameworkSession._invoke_agent`. |
| `SequentialBuilder` | High-level helper that wires agents/executors in order while keeping a shared `list[ChatMessage]` conversation. | Perfect for the per-vendor “rfp-compliance → legal → vendor → market → negotiation → evaluation” chain. |
| `ConcurrentBuilder` | Fans out input to many agents/executors in parallel and aggregates their `AgentExecutorResponse` objects (custom aggregator supported). | Lets us run the per-vendor workflows for all vendors at once and then aggregate their findings. |
| `FunctionExecutor` / `executor` decorator | Wrap any Python callable as a workflow node that can send messages or return outputs. | Ideal for the final HTML/Markdown/JSON comparison composer. |
| `WorkflowExecutor` | Allows nesting one workflow inside another as a single executor node. | Useful when a top-level workflow needs to invoke the per-vendor sequential workflow as one step. |

The engine also exposes `Workflow.run()`/`run_stream()` APIs, plus checkpoint and visualization support.

## 2. Proposed Orchestration for Multi-Proposal Comparison

```text
                        +-------------------+
 User prompt / trigger → |  Dispatcher node  |  (creates Fan-Out)
                        +---------+---------+
                                  |
                  +---------------+---------------+
                  |                               |
         (WorkflowExecutor)               (WorkflowExecutor)
          Vendor Workflow A                Vendor Workflow B
                  |                               |
                  +---------------+---------------+
                                  |
                        +-------------------+
                        | Aggregator (Func) |
                        +---------+---------+
                                  |
                     Final Markdown / HTML report
```

### 2.1 Per-Vendor Sequential Workflow

```python
from agent_framework import SequentialBuilder, ChatMessage, Role
from agent_framework._workflows import FunctionExecutor

async def build_vendor_workflow(chat_client, prompts, market_context):
    agents = [
        chat_client.create_agent(name=AGENT_NAMES["rfp_compliance"], instructions=prompts["rfp_compliance"]),
        chat_client.create_agent(name=AGENT_NAMES["legal_compliance"], instructions=prompts["legal_compliance"]),
        chat_client.create_agent(name=AGENT_NAMES["vendor_evaluation"], instructions=prompts["vendor_evaluation"]),
        chat_client.create_agent(name=AGENT_NAMES["market_intelligence"], instructions=prompts["market_intelligence"]),
        chat_client.create_agent(name=AGENT_NAMES["negotiation_strategy"], instructions=prompts["negotiation_strategy"]),
        chat_client.create_agent(name=AGENT_NAMES["evaluation_report"], instructions=prompts["evaluation_report"]),
    ]

    workflow = (
        SequentialBuilder()
        .participants(agents)
        .build()
    )

    # Initial conversation seeded with RFP+proposal snippets
    conversation = [
        ChatMessage(Role.SYSTEM, text="Use the following RFP and vendor summary as context."),
        ChatMessage(Role.USER, text=json.dumps({"rfp": rfp_summary, "vendor": vendor_summary})),
    ]

    return workflow, conversation
```

Calling `workflow.run_stream(conversation)` yields streaming `WorkflowEvent`s. Whenever `AgentExecutor` is invoked in streaming mode, we receive `AgentRunUpdateEvent`s that already contain token-by-token updates.

### 2.2 Multi-Vendor Aggregation Workflow

```python
from agent_framework import ConcurrentBuilder, WorkflowExecutor, ChatMessage, Role
from agent_framework._workflows import FunctionExecutor, WorkflowBuilder

@executor(id="vendor_report")
def render_vendor_report(results: list[AgentExecutorResponse], ctx: WorkflowContext[str]):
    structured = []
    for r in results:
        summary = extract_agent_sections(r.agent_run_response)
        structured.append(summary)
    html = html_renderer(structured)
    ctx.yield_output(html)

per_vendor_workflows = []
for vendor in vendor_payloads:
    vendor_wf, seed = build_vendor_workflow(...)
    vendor_exec = WorkflowExecutor(vendor_wf, id=f"vendor-{vendor['id']}")
    per_vendor_workflows.append(vendor_exec)

comparison_workflow = (
    ConcurrentBuilder()
    .participants(per_vendor_workflows)
    .with_aggregator(vendor_report)
    .build()
)

# run with streaming enabled
events = comparison_workflow.run_stream(AgentExecutorRequest(messages=[ChatMessage(Role.USER, text="Start")]))
```

`Comparison_workflow.run_stream(...)` will emit:

- `AgentRunUpdateEvent`s for every agent token (already streaming-friendly).
- A final `WorkflowOutputEvent` containing the rendered HTML report.

### 2.3 Streaming in Practice

Enable streaming when running the workflow:

```python
events = []
async for event in comparison_workflow.run_stream(seed_message):
    if isinstance(event, AgentRunUpdateEvent):
        emit_stream(event.executor_id, event.update.text)
    elif isinstance(event, WorkflowOutputEvent):
        final_html = event.data
        persist(final_html)
```

The workflow engine automatically switches all `AgentExecutor`s to `run_stream()` when `run_stream` is used; no extra plumbing is required.

## 3. Integration Roadmap for the RFP Copilot

1. **Encapsulate Agent Creation** – extract the agent-factory logic from `AgentFrameworkSession` into a reusable helper that returns a list of `ChatAgent` instances.
2. **Vendor Workflow Factory** – build a `build_vendor_workflow(vendor_payload) -> WorkflowExecutor`. Seed the initial conversation with the vendor + RFP summaries.
3. **Comparison Workflow** – use `ConcurrentBuilder` or `WorkflowBuilder` to fan out across vendor executors, then attach a `FunctionExecutor` that turns aggregated agent outputs into Markdown/HTML.
4. **Session State Wiring** – replace the manual per-vendor loop in `perform_multi_vendor_analysis()` with a single `comparison_workflow.run_stream(...)`. Use the emitted events to update Streamlit state incrementally.
5. **Final Report Output** – persist the HTML to `st.session_state.vendor_comparison_summary_html` for download, or render directly in Streamlit via `st.components.v1.html`.
6. **Optional Enhancements**

   - Add checkpoints with `FileCheckpointStorage` to resume runs after errors.
   - Visualize the graph with `WorkflowViz` for debugging.
   - Supply a custom aggregator that emits both structured JSON and HTML so the UI can present tables & download artifacts.

## 4. Benefits vs Existing Session Logic

| Current Implementation | Workflow-Based Approach |
| --- | --- |
| Imperative loops per vendor, manual state tracking, limited composability. | Declarative graph with clear edges, reusable across vendors and pages. |
| Custom streaming hook per agent. | Streaming built-in via `run_stream` and `AgentRunUpdateEvent`s. |
| Hard to parallelize vendor runs. | `ConcurrentBuilder` handles fan-out/fan-in automatically. |
| No built-in checkpointing. | Checkpoints available by plugging `FileCheckpointStorage`. |
| Manual aggregation code. | Aggregator executor cleanly encapsulates HTML/Markdown generation. |

## 5. Next Steps

- [ ] Extract agent factory + prompt wiring into `rfp_agents.py` so both the existing session and workflows can reuse it.
- [ ] Prototype `build_vendor_workflow()` returning a `WorkflowExecutor` and confirm output parity with current session logic.
- [ ] Replace `perform_multi_vendor_analysis()` with a top-level workflow run, observing streamed events to keep the UI responsive.
- [ ] Implement an aggregator that returns both HTML and machine-readable JSON to unlock richer visualizations/downloads.
- [ ] Add regression tests that validate the workflow output matches the previous imperative code for sample RFPs/proposals.

