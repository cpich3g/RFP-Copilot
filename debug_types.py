
import asyncio
from typing import List, Union
from agent_framework import ChatMessage, Role, AgentExecutorRequest
from agent_framework._workflows import FunctionExecutor
from agent_framework._workflows._workflow_context import WorkflowContext

async def _append_prompt(conversation: Union[List[ChatMessage], AgentExecutorRequest], ctx: WorkflowContext) -> None:
    pass

executor = FunctionExecutor(_append_prompt, id="test-prompt")
print(f"Input types: {executor.input_types}")
