"""Shared helper utilities for building RFP analysis agents and prompts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Sequence

from agent_framework import ChatAgent, ChatMessage, Role

from app import AGENT_NAMES, create_chat_client, get_reasoning_options

# Order in which the agents should be invoked for the base evaluation pipeline.
INITIAL_SEQUENCE_ORDER: Sequence[str] = (
    AGENT_NAMES["rfp_compliance"],
    AGENT_NAMES["legal_compliance"],
    AGENT_NAMES["vendor_evaluation"],
    AGENT_NAMES["market_intelligence"],
    AGENT_NAMES["negotiation_strategy"],
    AGENT_NAMES["evaluation_report"],
)

# Extra guidance appended to the Jinja prompt for each agent.
SUPPLEMENTAL_INSTRUCTIONS: Mapping[str, str] = {
    "rfp_compliance": "Always ground your assessment in the RFP and vendor summaries provided in each message.",
    "legal_compliance": "Focus on regulatory, contractual, and legal posture based on supplied evidence.",
    "vendor_evaluation": "Leverage historic insights to rate credibility and stability.",
    "market_intelligence": "Provide market trends and risk signals grounded in the context provided.",
    "negotiation_strategy": "Synthesize cross-agent findings into negotiation guidance.",
    "evaluation_report": "Deliver concise, decision-ready summaries aggregating every agent's output.",
}


@dataclass(frozen=True)
class VendorContext:
    """Static data describing the vendor analysis context."""

    rfp_summary: str
    proposal_summary: Mapping[str, str] | str
    policy_context: str
    vendor_insights: str
    market_insights: str


def _compose_instruction(agent_key: str, agent_prompts: Mapping[str, str]) -> str:
    prompt = agent_prompts.get(agent_key, "")
    supplemental = SUPPLEMENTAL_INSTRUCTIONS.get(agent_key, "")
    if supplemental:
        return f"{prompt}\n\n{supplemental}\nAlways respond in Markdown."
    return f"{prompt}\n\nAlways respond in Markdown."
AGENT_MODEL_VARIANTS: Mapping[str, str] = {
    AGENT_NAMES["rfp_compliance"]: "gpt5-mini",
    AGENT_NAMES["legal_compliance"]: "gpt5-mini",
    AGENT_NAMES["vendor_evaluation"]: "gpt5-mini",
    AGENT_NAMES["market_intelligence"]: "gpt5-mini",
    AGENT_NAMES["negotiation_strategy"]: "gpt5-mini",
    AGENT_NAMES["evaluation_report"]: "gpt5-mini",
}


def create_agents(agent_prompts: Mapping[str, str]) -> Dict[str, ChatAgent]:
    """Instantiate chat agents with consistent instructions, descriptions, and model variants."""

    agent_definitions: Mapping[str, Mapping[str, Any]] = {
        AGENT_NAMES["rfp_compliance"]: {
            "instructions": _compose_instruction("rfp_compliance", agent_prompts),
            "description": "Analyzes proposal alignment with RFP requirements.",
            "temperature": 0.1,
        },
        AGENT_NAMES["legal_compliance"]: {
            "instructions": _compose_instruction("legal_compliance", agent_prompts),
            "description": "Evaluates legal and regulatory adherence.",
            "temperature": 0.1,
        },
        AGENT_NAMES["vendor_evaluation"]: {
            "instructions": _compose_instruction("vendor_evaluation", agent_prompts),
            "description": "Reviews vendor reputation and historical performance.",
            "temperature": 0.2,
        },
        AGENT_NAMES["market_intelligence"]: {
            "instructions": _compose_instruction("market_intelligence", agent_prompts),
            "description": "Summarizes market conditions and risks.",
            "temperature": 0.2,
        },
        AGENT_NAMES["negotiation_strategy"]: {
            "instructions": _compose_instruction("negotiation_strategy", agent_prompts),
            "description": "Crafts negotiation recommendations based on all findings.",
            "temperature": 0.4,
        },
        AGENT_NAMES["evaluation_report"]: {
            "instructions": _compose_instruction("evaluation_report", agent_prompts),
            "description": "Produces the consolidated evaluation report.",
            "temperature": 0.2,
        },
    }

    agents: Dict[str, ChatAgent] = {}
    for agent_name, settings in agent_definitions.items():
        variant = AGENT_MODEL_VARIANTS.get(agent_name, "gpt5-mini")
        client = create_chat_client(model_variant=variant)
        reasoning_options = get_reasoning_options(variant)
        additional_options = settings.get("additional_options") or {}
        if reasoning_options:
            merged_options = {**reasoning_options, **additional_options}
        else:
            merged_options = additional_options

        chat_options = dict(merged_options)
        chat_options.pop("reasoning", None)

        temperature = settings.get("temperature")
        if reasoning_options:
            temperature = None

        agents[agent_name] = client.create_agent(
            name=agent_name,
            instructions=settings["instructions"],
            description=settings["description"],
            temperature=temperature,
            additional_chat_options=chat_options or None,
        )
    return agents


def proposal_overall_summary(proposal_summary: Mapping[str, str] | str) -> str:
    if isinstance(proposal_summary, Mapping):
        return str(proposal_summary.get("overall_summary", "Not specified in the proposal."))
    return str(proposal_summary)


def proposal_legal_summary(proposal_summary: Mapping[str, str] | str) -> str:
    if isinstance(proposal_summary, Mapping):
        return str(proposal_summary.get("legal_summary", "Not specified in the proposal."))
    return str(proposal_summary)


def build_initial_task(
    agent_name: str,
    context: VendorContext,
    last_agent_outputs: Mapping[str, str] | None = None,
) -> str:
    """Compose the initial task payload for the specified agent."""

    last_outputs = last_agent_outputs or {}

    if agent_name == AGENT_NAMES["rfp_compliance"]:
        return (
            "Produce an initial compliance assessment using the summaries below."
            "\n\n### RFP Summary\n"
            f"{context.rfp_summary}\n\n"
            "### Vendor Proposal Summary\n"
            f"{proposal_overall_summary(context.proposal_summary)}\n"
        )

    if agent_name == AGENT_NAMES["legal_compliance"]:
        return (
            "Identify legal or policy gaps based on the vendor's legal summary and retrieved policies."
            "\n\n### Vendor Legal Summary\n"
            f"{proposal_legal_summary(context.proposal_summary)}\n\n"
            "### Retrieved Policy Context\n"
            f"{context.policy_context or 'No relevant policies were retrieved.'}\n"
        )

    if agent_name == AGENT_NAMES["vendor_evaluation"]:
        return (
            "Summarize the vendor's reputation, financial stability, and historical performance."
            "\n\n### Vendor Insights\n"
            f"{context.vendor_insights}\n"
        )

    if agent_name == AGENT_NAMES["market_intelligence"]:
        return (
            "Summarize market trends, competitor positioning, and regulatory changes for context."
            "\n\n### Market Intelligence\n"
            f"{context.market_insights}\n"
        )

    if agent_name == AGENT_NAMES["negotiation_strategy"]:
        return (
            "Draft a negotiation strategy using the latest findings from all prior agents."
            "\n\n### Compliance Highlights\n"
            f"{last_outputs.get(AGENT_NAMES['rfp_compliance'], 'Pending results.')}\n\n"
            "### Legal Risk Overview\n"
            f"{last_outputs.get(AGENT_NAMES['legal_compliance'], 'Pending results.')}\n\n"
            "### Vendor Evaluation\n"
            f"{last_outputs.get(AGENT_NAMES['vendor_evaluation'], 'Pending results.')}\n\n"
            "### Market Intelligence\n"
            f"{last_outputs.get(AGENT_NAMES['market_intelligence'], 'Pending results.')}\n"
        )

    if agent_name == AGENT_NAMES["evaluation_report"]:
        return compose_evaluation_request(
            last_outputs,
            "Provide the initial consolidated evaluation report.",
        )

    return "Provide a concise update based on the available context."


def build_followup_task(
    agent_name: str,
    prompt: str,
    context: VendorContext,
    last_agent_outputs: Mapping[str, str] | None = None,
    *,
    is_follow_up: bool = False,
) -> str:
    """Compose a follow-up task payload for the specified agent."""

    last_outputs = last_agent_outputs or {}
    user_section = f"### User Request\n{prompt}\n\n"

    if agent_name == AGENT_NAMES["rfp_compliance"]:
        return (
            user_section
            + "Re-evaluate proposal compliance considering the user's question.\n\n"
            "### RFP Summary\n"
            f"{context.rfp_summary}\n\n"
            "### Vendor Proposal Summary\n"
            f"{proposal_overall_summary(context.proposal_summary)}\n\n"
            "### Latest Compliance Findings\n"
            f"{last_outputs.get(agent_name, 'No findings yet.')}\n"
        )

    if agent_name == AGENT_NAMES["legal_compliance"]:
        return (
            user_section
            + "Assess legal and regulatory implications relevant to the request.\n\n"
            "### Vendor Legal Summary\n"
            f"{proposal_legal_summary(context.proposal_summary)}\n\n"
            "### Retrieved Policy Context\n"
            f"{context.policy_context or 'No relevant policies were retrieved.'}\n\n"
            "### Supporting Findings\n"
            f"{last_outputs.get(AGENT_NAMES['rfp_compliance'], 'No compliance analysis yet.')}\n"
        )

    if agent_name == AGENT_NAMES["vendor_evaluation"]:
        return (
            user_section
            + "Update the vendor assessment to answer the question.\n\n"
            "### Vendor Insights\n"
            f"{context.vendor_insights}\n\n"
            "### Current Legal Risk\n"
            f"{last_outputs.get(AGENT_NAMES['legal_compliance'], 'No legal analysis yet.')}\n"
        )

    if agent_name == AGENT_NAMES["market_intelligence"]:
        return (
            user_section
            + "Provide market or industry context that addresses the request.\n\n"
            "### Market Intelligence\n"
            f"{context.market_insights}\n\n"
            "### Related Vendor Insights\n"
            f"{last_outputs.get(AGENT_NAMES['vendor_evaluation'], 'No vendor evaluation yet.')}\n"
        )

    if agent_name == AGENT_NAMES["negotiation_strategy"]:
        return (
            user_section
            + "Create or refine negotiation guidance using the cross-agent context.\n\n"
            "### Compliance Highlights\n"
            f"{last_outputs.get(AGENT_NAMES['rfp_compliance'], 'No compliance analysis yet.')}\n\n"
            "### Legal Risk Overview\n"
            f"{last_outputs.get(AGENT_NAMES['legal_compliance'], 'No legal analysis yet.')}\n\n"
            "### Vendor Evaluation\n"
            f"{last_outputs.get(AGENT_NAMES['vendor_evaluation'], 'No vendor evaluation yet.')}\n\n"
            "### Market Intelligence\n"
            f"{last_outputs.get(AGENT_NAMES['market_intelligence'], 'No market intelligence yet.')}\n"
        )

    if agent_name == AGENT_NAMES["evaluation_report"]:
        instruction = "Summarize the overall position and answer the user's question directly."
        if is_follow_up:
            instruction = "Update the consolidated summary to reflect the latest agent responses."
        return compose_evaluation_request(
            last_outputs,
            instruction,
            include_user_section=user_section,
        )

    return user_section + "Respond with the best available guidance."


def compose_evaluation_request(
    last_agent_outputs: Mapping[str, str],
    instruction: str,
    *,
    include_user_section: str | None = None,
) -> str:
    sections = [instruction]
    if include_user_section:
        sections.append(include_user_section)
    sections.append("### Combined Agent Findings")
    for key in INITIAL_SEQUENCE_ORDER:
        if key == AGENT_NAMES["evaluation_report"]:
            continue
        sections.append(f"#### {key}\n{last_agent_outputs.get(key, 'No output recorded yet.')}\n")
    return "\n\n".join(sections)


def make_system_seed_message(vendor_label: str) -> ChatMessage:
    """Create a system message that frames the workflow for the agents."""

    return ChatMessage(
        role=Role.SYSTEM,
        text=(
            "You are part of a cooperative multi-agent evaluation chain for procurement analysis. "
            "Always format outputs in Markdown with clear headings and bullet points. "
            f"Focus on the provided evidence for vendor: {vendor_label}."
        ),
    )


def make_vendor_context_message(context: VendorContext, vendor_label: str) -> ChatMessage:
    """Create a shared user message summarizing the vendor context."""

    payload = {
        "vendor": vendor_label,
        "rfp_summary": context.rfp_summary,
        "proposal_summary": context.proposal_summary,
        "policy_context": context.policy_context,
        "vendor_insights": context.vendor_insights,
        "market_insights": context.market_insights,
    }
    return ChatMessage(
        role=Role.USER,
        text=(
            "Context bundle for all agents (use selectively):\n\n"
            + json.dumps(payload, indent=2)
        ),
    )


def attach_agent_output(
    agent_outputs: MutableMapping[str, str],
    agent_name: str,
    message: ChatMessage | None,
) -> MutableMapping[str, str]:
    """Update the agent output mapping with the assistant message text if available."""

    if message and message.text:
        agent_outputs[agent_name] = message.text
    return agent_outputs
