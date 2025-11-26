"""Workflow utilities for orchestrating per-vendor RFP analysis."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Union

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    ConcurrentBuilder,
    Role,
    SequentialBuilder,
    Workflow,
    WorkflowBuilder,
    WorkflowExecutor,
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
    async def _append_prompt(conversation: Union[List[ChatMessage], AgentExecutorRequest], ctx: WorkflowContext) -> None:
        if isinstance(conversation, AgentExecutorRequest):
            conversation = conversation.messages

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


def _make_capture_executor(agent_name: str, output_sink: Optional[Dict[str, str]] = None) -> FunctionExecutor:
    async def _capture(conversation: Union[List[ChatMessage], AgentExecutorResponse], ctx: WorkflowContext) -> None:
        if isinstance(conversation, AgentExecutorResponse):
            if conversation.full_conversation is None:
                raise RuntimeError("AgentExecutorResponse.full_conversation missing.")
            conversation = conversation.full_conversation

        state = await _ensure_agent_output_state(ctx)
        latest = _extract_latest_assistant(conversation)
        attach_agent_output(state, agent_name, latest)
        await ctx.set_shared_state(_STATE_KEY, dict(state))
        
        if latest and latest.text:
            if output_sink is not None:
                output_sink[agent_name] = latest.text
            await ctx.yield_output({"agent_name": agent_name, "agent_output": latest.text})
            
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


def _make_populate_state_executor(initial_state: Dict[str, str]) -> FunctionExecutor:
    async def _populate(conversation: List[ChatMessage], ctx: WorkflowContext) -> None:
        state = await _ensure_agent_output_state(ctx)
        state.update(initial_state)
        await ctx.set_shared_state(_STATE_KEY, dict(state))
        await ctx.send_message(list(conversation))
    return FunctionExecutor(_populate, id="populate-state")


import asyncio

def build_single_agent_workflow(
    *,
    agent_name: str,
    agent_prompts: Mapping[str, str],
    context: VendorContext,
    output_sink: Optional[Dict[str, str]] = None,
) -> Workflow:
    """Build a workflow for a single agent."""
    agents = create_agents(agent_prompts)
    agent = agents[agent_name]
    
    prompt_exec = _make_prompt_executor(agent_name, context)
    agent_exec = AgentExecutor(agent, agent_thread=agent.get_new_thread(), id=agent_name)
    capture_exec = _make_capture_executor(agent_name, output_sink)

    return (
        WorkflowBuilder()
        .add_chain([prompt_exec, agent_exec, capture_exec])
        .set_start_executor(prompt_exec)
        .build()
    )


def build_sequential_workflow(
    *,
    agent_prompts: Mapping[str, str],
    vendor_label: str,
    context: VendorContext,
    initial_state: Dict[str, str],
    output_sink: Optional[Dict[str, str]] = None,
) -> Workflow:
    agents = create_agents(agent_prompts)
    
    participants: List[Any] = [_make_populate_state_executor(initial_state)]

    sequential_agents = [
        AGENT_NAMES["negotiation_strategy"],
        AGENT_NAMES["evaluation_report"],
    ]

    for agent_name in sequential_agents:
        agent = agents[agent_name]
        participants.append(_make_prompt_executor(agent_name, context))
        participants.append(
            AgentExecutor(
                agent,
                agent_thread=agent.get_new_thread(),
                id=agent_name,
            )
        )
        participants.append(_make_capture_executor(agent_name, output_sink))

    participants.append(_make_emit_executor(vendor_label))

    return SequentialBuilder().participants(participants).build()


async def run_single_agent_workflow(
    workflow: Workflow,
    seed_messages: List[ChatMessage],
    vendor_label: str,
    stream_callback: Optional[StreamingCallback],
    output_sink: Dict[str, str],
) -> None:
    """Run a single agent workflow and capture outputs."""
    async for event in workflow.run_stream(seed_messages):
        if isinstance(event, AgentRunUpdateEvent) and stream_callback:
            stream_callback(vendor_label, event.executor_id, event.update.text)
        elif isinstance(event, WorkflowOutputEvent):
            data = event.data
            if isinstance(data, dict) and "agent_name" in data and "agent_output" in data:
                output_sink[data["agent_name"]] = data["agent_output"]


async def run_full_vendor_process(
    *,
    agent_prompts: Mapping[str, str],
    vendor_label: str,
    context: VendorContext,
    stream_callback: Optional[StreamingCallback] = None,
) -> VendorWorkflowResult:
    """Execute the full vendor analysis process (parallel + sequential phases)."""
    
    seed_messages = [
        make_system_seed_message(vendor_label),
        make_vendor_context_message(context, vendor_label),
    ]
    
    agent_outputs: Dict[str, str] = {}
    
    # Phase 1: Parallel Analysis (Manual Concurrency)
    parallel_agents = [
        AGENT_NAMES["rfp_compliance"],
        AGENT_NAMES["legal_compliance"],
        AGENT_NAMES["vendor_evaluation"],
        AGENT_NAMES["market_intelligence"],
    ]
    
    parallel_tasks = []
    for agent_name in parallel_agents:
        wf = build_single_agent_workflow(
            agent_name=agent_name,
            agent_prompts=agent_prompts,
            context=context,
            output_sink=agent_outputs
        )
        parallel_tasks.append(
            run_single_agent_workflow(
                wf, 
                list(seed_messages), # Pass a copy to avoid mutation issues
                vendor_label, 
                stream_callback, 
                agent_outputs
            )
        )
    
    await asyncio.gather(*parallel_tasks)

    # Phase 2: Sequential Synthesis
    sequential_workflow = build_sequential_workflow(
        agent_prompts=agent_prompts,
        vendor_label=vendor_label,
        context=context,
        initial_state=agent_outputs,
        output_sink=agent_outputs
    )
    
    final_conversation: List[ChatMessage] = []
    
    async for event in sequential_workflow.run_stream(seed_messages):
        if isinstance(event, AgentRunUpdateEvent) and stream_callback:
            stream_callback(vendor_label, event.executor_id, event.update.text)
        elif isinstance(event, WorkflowOutputEvent):
            data = event.data
            if isinstance(data, dict) and {"vendor_label", "agent_outputs"} <= data.keys():
                agent_outputs.update(data.get("agent_outputs", {}))
            elif isinstance(data, list):
                final_conversation = [msg for msg in data if isinstance(msg, ChatMessage)]

    if not final_conversation:
        # Fallback if streaming didn't yield conversation
        # Note: run_stream usually yields output events. If not, we might need to run() but that re-executes.
        # For now, assume streaming works or conversation is less critical than outputs.
        pass

    return VendorWorkflowResult(
        vendor_label=vendor_label,
        agent_outputs=agent_outputs,
        conversation=final_conversation,
    )
