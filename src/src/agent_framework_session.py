"""Utility classes for coordinating Microsoft Agent Framework agents in the RFP Copilot app."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from agent_framework import ChatAgent

from app import AGENT_NAMES
from rfp_agents import (
    INITIAL_SEQUENCE_ORDER,
    VendorContext,
    build_followup_task,
    build_initial_task,
    compose_evaluation_request,
    create_agents,
)


class AgentFrameworkSession:
    """Encapsulates multi-agent orchestration using Microsoft Agent Framework."""

    def __init__(
        self,
        *,
        agent_prompts: Dict[str, str],
        rfp_summary: str,
        proposal_summary: Dict[str, str] | str,
        policy_context: str,
        vendor_insights: str,
        market_insights: str,
    ) -> None:
        self.agent_prompts = agent_prompts
        self.rfp_summary = rfp_summary
        self.proposal_summary = proposal_summary
        self.policy_context = policy_context
        self.vendor_insights = vendor_insights
        self.market_insights = market_insights

        self.context = VendorContext(
            rfp_summary=rfp_summary,
            proposal_summary=proposal_summary,
            policy_context=policy_context,
            vendor_insights=vendor_insights,
            market_insights=market_insights,
        )

        self.agents = create_agents(self.agent_prompts)
        self.threads = {name: agent.get_new_thread() for name, agent in self.agents.items()}
        self.initial_sequence_order = list(INITIAL_SEQUENCE_ORDER)

        self.initial_run_complete = False
        self.last_agent_outputs: Dict[str, str] = {}
        self.initial_messages: List[Dict[str, str]] = []

    async def bootstrap(
        self,
        *,
        stream_handler: Optional[Callable[[str, str], None]] = None,
    ) -> List[Dict[str, str]]:
        """Run the initial sequence once and return the generated messages."""

        if not self.initial_run_complete:
            responses = await self._run_initial_sequence(stream_handler=stream_handler)
            self.initial_messages = [
                {"role": agent_name, "content": text} for agent_name, text in responses if text
            ]
            self.initial_run_complete = True
        return self.initial_messages

    async def handle_user_prompt(self, prompt: str) -> List[Tuple[str, str]]:
        """Process a user prompt and return (agent_name, response) pairs."""

        if not self.initial_run_complete:
            await self.bootstrap()

        agent_name = self._select_agent(prompt)
        message = build_followup_task(
            agent_name,
            prompt,
            self.context,
            self.last_agent_outputs,
        )
        response = await self._invoke_agent(agent_name, message)

        replies: List[Tuple[str, str]] = [(agent_name, response)] if response else []

        # Refresh the evaluation report to keep the summary current unless it was already the responder.
        evaluation_agent = AGENT_NAMES["evaluation_report"]
        if agent_name != evaluation_agent:
            evaluation_message = build_followup_task(
                evaluation_agent,
                prompt,
                self.context,
                self.last_agent_outputs,
                is_follow_up=True,
            )
            evaluation_response = await self._invoke_agent(evaluation_agent, evaluation_message)
            if evaluation_response:
                replies.append((evaluation_agent, evaluation_response))

        return replies

    async def handle_user_prompt_streaming(
        self,
        prompt: str,
        *,
        stream_handler: Callable[[str, str], None],
    ) -> List[Tuple[str, str]]:
        """Process a user prompt with streaming updates."""

        if not self.initial_run_complete:
            await self.bootstrap(stream_handler=stream_handler)

        agent_name = self._select_agent(prompt)
        message = build_followup_task(
            agent_name,
            prompt,
            self.context,
            self.last_agent_outputs,
        )
        response = await self._invoke_agent(agent_name, message, stream_handler=stream_handler)

        replies: List[Tuple[str, str]] = [(agent_name, response)] if response else []

        evaluation_agent = AGENT_NAMES["evaluation_report"]
        if agent_name != evaluation_agent:
            evaluation_message = build_followup_task(
                evaluation_agent,
                prompt,
                self.context,
                self.last_agent_outputs,
                is_follow_up=True,
            )
            evaluation_response = await self._invoke_agent(
                evaluation_agent,
                evaluation_message,
                stream_handler=stream_handler,
            )
            if evaluation_response:
                replies.append((evaluation_agent, evaluation_response))

        return replies

    async def _run_initial_sequence(
        self,
        *,
        stream_handler: Optional[Callable[[str, str], None]] = None,
    ) -> List[Tuple[str, str]]:
        outputs: List[Tuple[str, str]] = []
        for agent_name in self.initial_sequence_order:
            message = build_initial_task(agent_name, self.context, self.last_agent_outputs)
            response = await self._invoke_agent(agent_name, message, stream_handler=stream_handler)
            outputs.append((agent_name, response))
        return outputs

    async def _invoke_agent(
        self,
        agent_name: str,
        message: str,
        *,
        stream_handler: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        agent = self.agents[agent_name]
        thread = self.threads[agent_name]
        if stream_handler is not None:
            return await self._invoke_agent_stream(agent_name, agent, message, thread, stream_handler)

        result = await agent.run(message, thread=thread)
        text = result.text if result and result.text else ""
        if text:
            self.last_agent_outputs[agent_name] = text
        return text

    async def _invoke_agent_stream(
        self,
        agent_name: str,
        agent: ChatAgent,
        message: str,
        thread,
        stream_handler: Callable[[str, str], None],
    ) -> str:
        chunks: List[str] = []
        async for update in agent.run_stream(message, thread=thread):
            text = update.text
            if text:
                chunks.append(text)
                stream_handler(agent_name, text)

        combined = "".join(chunks)
        if combined:
            self.last_agent_outputs[agent_name] = combined
        return combined

    def _select_agent(self, prompt: str) -> str:
        text = prompt.lower()
        if any(keyword in text for keyword in ["legal", "policy", "regulation", "compliance risk"]):
            return AGENT_NAMES["legal_compliance"]
        if any(keyword in text for keyword in ["vendor", "history", "reputation", "credibility", "reference"]):
            return AGENT_NAMES["vendor_evaluation"]
        if any(keyword in text for keyword in ["market", "industry", "trend", "competition", "regulatory"]):
            return AGENT_NAMES["market_intelligence"]
        if any(keyword in text for keyword in ["negotiation", "terms", "contract", "pricing", "leverage"]):
            return AGENT_NAMES["negotiation_strategy"]
        if any(keyword in text for keyword in ["rfp", "requirement", "alignment", "mandatory"]):
            return AGENT_NAMES["rfp_compliance"]
        return AGENT_NAMES["evaluation_report"]
