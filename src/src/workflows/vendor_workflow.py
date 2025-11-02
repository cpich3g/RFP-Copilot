"""Workflow utilities for orchestrating per-vendor RFP analysis."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from agent_framework import (
    AgentExecutor,
    AgentRunUpdateEvent,
    ChatMessage,
    Role,
    SequentialBuilder,
    Workflow,
    WorkflowOutputEvent,
    WorkflowRunResult,
)
from agent_framework._workflows import FunctionExecutor
from agent_framework._workflows._workflow_context import WorkflowContext
from app import AGENT_NAMES
from rfp_agents import (
    INITIAL_SEQUENCE_ORDER,
    VendorContext,
    attach_agent_output,
    build_initial_task,
    create_agents,
    make_system_seed_message,
    make_vendor_context_message,
)

StreamingCallback = Callable[[str, str, str], None]

_STATE_KEY = "rfp_workflow_agent_outputs"


async def _ensure_agent_output_state(ctx: WorkflowContext) -> MutableMapping[str, str]:
    """Fetch the shared agent output mapping, initializing it when absent."""

    try:
        state = await ctx.get_shared_state(_STATE_KEY)
    except KeyError:
        state = {}
    if not isinstance(state, MutableMapping):
        state = dict(state or {})
    await ctx.set_shared_state(_STATE_KEY, state)
    return state


@dataclass
class VendorWorkflowResult:
    """Structured output captured from a completed vendor workflow run."""

    vendor_label: str
    agent_outputs: Dict[str, str]
    conversation: List[ChatMessage]


async def _ensure_state(conversation: List[ChatMessage], ctx: WorkflowContext) -> None:
    await _ensure_agent_output_state(ctx)
    await ctx.send_message(list(conversation))


def _make_prompt_executor(agent_name: str, context: VendorContext) -> FunctionExecutor:
    async def _append_prompt(conversation: List[ChatMessage], ctx: WorkflowContext) -> None:
        state = await _ensure_agent_output_state(ctx)
        message = build_initial_task(agent_name, context, state)
        updated = list(conversation)
        updated.append(ChatMessage(role=Role.USER, text=message))
        await ctx.send_message(updated)

    return FunctionExecutor(_append_prompt, id=f"{agent_name}-prompt")


def _extract_latest_assistant(conversation: Sequence[ChatMessage]) -> ChatMessage | None:
    for message in reversed(conversation):
        if str(message.role).lower().endswith("assistant") and message.text:
            return message
    return None


def _make_capture_executor(agent_name: str) -> FunctionExecutor:
    async def _capture(conversation: List[ChatMessage], ctx: WorkflowContext) -> None:
        state = await _ensure_agent_output_state(ctx)
        latest = _extract_latest_assistant(conversation)
        attach_agent_output(state, agent_name, latest)
        await ctx.set_shared_state(_STATE_KEY, dict(state))
        await ctx.send_message(list(conversation))

    return FunctionExecutor(_capture, id=f"{agent_name}-capture")


def _make_emit_executor(vendor_label: str) -> FunctionExecutor:
    async def _emit(conversation: List[ChatMessage], ctx: WorkflowContext) -> None:
        state = await _ensure_agent_output_state(ctx)
        payload = {
            "vendor_label": vendor_label,
            "agent_outputs": dict(state),
        }
        await ctx.yield_output(payload)
        await ctx.send_message(list(conversation))

    return FunctionExecutor(_emit, id=f"{vendor_label}-emit")


def build_vendor_workflow(
    *,
    agent_prompts: Mapping[str, str],
    vendor_label: str,
    context: VendorContext,
) -> tuple[Workflow, List[ChatMessage]]:
    """Assemble the Sequential workflow that evaluates a single vendor."""

    agents = create_agents(agent_prompts)
    participants: List[Any] = [FunctionExecutor(_ensure_state, id="init-state")]

    for agent_name in INITIAL_SEQUENCE_ORDER:
        agent = agents[agent_name]
        participants.append(_make_prompt_executor(agent_name, context))
        participants.append(
            AgentExecutor(
                agent,
                agent_thread=agent.get_new_thread(),
                id=agent_name,
            )
        )
        participants.append(_make_capture_executor(agent_name))

    participants.append(_make_emit_executor(vendor_label))

    workflow = SequentialBuilder().participants(participants).build()
    seed_conversation = [
        make_system_seed_message(vendor_label),
        make_vendor_context_message(context, vendor_label),
    ]
    return workflow, seed_conversation


def _parse_conversation(conversation: Sequence[ChatMessage]) -> Dict[str, str]:
    agent_outputs: Dict[str, str] = {}
    user_messages_seen = 0
    agent_index = -1
    expecting_agent: str | None = None

    for message in conversation:
        role_value = str(message.role).lower()
        if role_value.endswith("user"):
            user_messages_seen += 1
            if user_messages_seen <= 1:
                continue  # Skip global context payload
            if agent_index + 1 < len(INITIAL_SEQUENCE_ORDER):
                agent_index += 1
                expecting_agent = INITIAL_SEQUENCE_ORDER[agent_index]
            else:
                expecting_agent = None
        elif role_value.endswith("assistant") and expecting_agent:
            agent_outputs[expecting_agent] = message.text
            expecting_agent = None

    return agent_outputs


async def run_vendor_workflow(
    workflow: Workflow,
    seed_messages: Iterable[ChatMessage],
    *,
    vendor_label: str,
    stream_callback: Optional[StreamingCallback] = None,
) -> VendorWorkflowResult:
    """Execute the vendor workflow and yield structured outputs."""

    final_conversation: List[ChatMessage] | None = None
    agent_outputs: Dict[str, str] = {}
    seed_messages_list = list(seed_messages)

    async for event in workflow.run_stream(seed_messages_list):
        if isinstance(event, AgentRunUpdateEvent) and stream_callback:
            stream_callback(vendor_label, event.executor_id, event.update.text)
        elif isinstance(event, WorkflowOutputEvent):
            data = event.data
            if isinstance(data, dict) and {"vendor_label", "agent_outputs"} <= data.keys():
                agent_outputs = {**data.get("agent_outputs", {})}
            elif isinstance(data, list):
                final_conversation = [msg for msg in data if isinstance(msg, ChatMessage)]

    if final_conversation is None:
        # Fallback: attempt to fetch last available conversation by re-running in non-streaming mode.
        result: WorkflowRunResult = await workflow.run(seed_messages_list)
        for output in result.get_outputs():
            if isinstance(output, list):
                final_conversation = [msg for msg in output if isinstance(msg, ChatMessage)]
                break

    final_conversation = final_conversation or []
    if not agent_outputs:
        agent_outputs = _parse_conversation(final_conversation)

    return VendorWorkflowResult(
        vendor_label=vendor_label,
        agent_outputs=agent_outputs,
        conversation=final_conversation,
    )
