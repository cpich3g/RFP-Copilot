"""Negotiation strategy services supporting pre-brief, live guidance, and post-session logging."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from services.llm_helpers import dataframe_to_pretty_json, run_agent_sync


DEFAULT_TACTICS = [
    {
        "name": "Volume Leverage",
        "description": "Offer longer-term commitment for tiered pricing concessions.",
        "category": "Pricing",
    },
    {
        "name": "Scope Trade",
        "description": "Propose scope reduction on low-value features in exchange for warranty extension.",
        "category": "Value",
    },
    {
        "name": "Risk Mitigation",
        "description": "Introduce performance bonds or penalties tied to SLA breaches.",
        "category": "Risk",
    },
    {
        "name": "BATNA Reminder",
        "description": "Reinforce fallback supplier or internal alternative to maintain leverage.",
        "category": "BATNA",
    },
    {
        "name": "Concession Ladder",
        "description": "Pre-plan concession steps with corresponding asks on warranty, SLA, and penalties.",
        "category": "Playbook",
    },
    {
        "name": "Counter-Proposal Draft",
        "description": "Template a packaged counter-offer bundling price, service credits, and penalty triggers.",
        "category": "Counter",
    },
]


@dataclass
class SupplierProfile:
    supplier_id: str
    description: str
    historic_notes: List[str] = field(default_factory=list)
    risk_level: str = "Medium"
    last_negotiated: Optional[str] = None


@dataclass
class NegotiationObjective:
    target_price: Optional[float] = None
    sla: Optional[str] = None
    warranty: Optional[str] = None
    penalties: Optional[str] = None
    moq: Optional[int] = None
    currency: str = "USD"
    incoterms: Optional[str] = None
    additional_constraints: List[str] = field(default_factory=list)


@dataclass
class LiveNegotiationState:
    transcripts: List[Dict[str, str]] = field(default_factory=list)
    tactics_used: List[str] = field(default_factory=list)
    live_recommendations: List[str] = field(default_factory=list)


@dataclass
class PostNegotiationSummary:
    outcome: str
    concessions: List[str]
    action_items: List[str]
    lessons_learned: str
    timestamp: dt.datetime = field(default_factory=dt.datetime.utcnow)


class NegotiationStrategyEngine:
    def __init__(self) -> None:
        self.strategy_memory: Dict[str, List[PostNegotiationSummary]] = {}
        self.market_benchmarks_cache: Dict[str, Dict[str, Any]] = {}

    def preload_supplier_profile(self, supplier_id: str, profile_data: Dict[str, Any]) -> SupplierProfile:
        profile = SupplierProfile(
            supplier_id=supplier_id,
            description=profile_data.get("description", ""),
            historic_notes=profile_data.get("historic_notes", []),
            risk_level=profile_data.get("risk_level", "Medium"),
            last_negotiated=profile_data.get("last_negotiated"),
        )
        return profile

    def fetch_market_benchmarks(self, category: str) -> Dict[str, Any]:
        if category in self.market_benchmarks_cache:
            return self.market_benchmarks_cache[category]
        benchmark = {
            "category": category,
            "median_discount": 0.08,
            "sla_norm": "99.5% uptime",
            "warranty_norm": "12 months",
            "currency": "USD",
            "recency": "Q3 2025",
            "notes": "Stub benchmark data—replace with live source integration",
        }
        self.market_benchmarks_cache[category] = benchmark
        return benchmark

    def build_prebrief(self, profile: SupplierProfile, benchmark: Dict[str, Any], objectives: NegotiationObjective) -> str:
        instructions = (
            "You are the Negotiation Pre-Brief Agent."
            " Summarize supplier positioning, leverage points, and risks."
            " Provide actionable talking points for the negotiator."
        )
        message = (
            f"Supplier profile:\n```json\n{json.dumps(profile.__dict__, indent=2)}\n```\n"
            f"Market benchmarks:\n```json\n{json.dumps(benchmark, indent=2)}\n```\n"
            f"Objectives:\n```json\n{json.dumps(objectives.__dict__, indent=2)}\n```\n"
            "Return the pre-brief with sections for Strengths, Weaknesses, Opportunities, Risks, and Recommended Tactics."
        )
        return run_agent_sync("NegotiationPrebriefAgent", instructions, message)

    def live_guidance(
        self,
        profile: SupplierProfile,
        objectives: NegotiationObjective,
        transcript: List[Dict[str, str]],
        market_context: Dict[str, Any],
    ) -> str:
        instructions = (
            "You are the Live Negotiation Copilot Agent."
            " Provide real-time prompts, counter-offers, and risk alerts based on the evolving conversation."
            " Return guidance in Markdown with sections for Immediate Action, Suggested Counter Offer, Risk Alerts, and Suggested Questions."
        )
        message = (
            f"Supplier profile:\n```json\n{json.dumps(profile.__dict__, indent=2)}\n```\n"
            f"Objectives:\n```json\n{json.dumps(objectives.__dict__, indent=2)}\n```\n"
            f"Market context:\n```json\n{json.dumps(market_context, indent=2)}\n```\n"
            f"Live transcript:\n```json\n{json.dumps(transcript[-10:], indent=2)}\n```\n"
            "Respond concisely and highlight the most relevant tactic from the tactic palette."
        )
        return run_agent_sync("NegotiationLiveCopilot", instructions, message)

    def log_outcome(
        self,
        supplier_id: str,
        summary: PostNegotiationSummary,
    ) -> None:
        self.strategy_memory.setdefault(supplier_id, []).append(summary)

    def get_strategy_memory(self, supplier_id: str) -> List[PostNegotiationSummary]:
        return self.strategy_memory.get(supplier_id, [])

    def render_tactics_palette(self, additional_notes: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, str]]:
        palette = DEFAULT_TACTICS.copy()
        if additional_notes:
            palette.extend(additional_notes)
        return palette
