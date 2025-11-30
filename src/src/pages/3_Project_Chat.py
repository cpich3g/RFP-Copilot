"""Streamlit page for project-based chat.

This page provides a chat interface within the context of a specific project,
allowing users to ask questions about the RFP, proposals, and analysis results.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
from time import sleep
from typing import Callable, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

# Add parent directory to path for imports
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from services.project_service import (
    AgentType,
    Project,
    ProjectService,
    ProjectStatus,
)

# Try to import Azure and agent-related modules - they may fail if not configured
CHAT_AVAILABLE = True
CHAT_ERROR_MSG = ""

try:
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from app import AGENT_NAMES, create_chat_client, get_agent_prompts, get_reasoning_options
    from plugins.legal_compliance_plugin import LegalCompliancePlugin
    from plugins.vendor_evaluation_plugin import VendorEvaluationPlugin
    from plugins.market_intelligence_plugin import MarketIntelligencePlugin
    from rfp_agents import VendorContext, create_agents, INITIAL_SEQUENCE_ORDER
    from agent_framework_session import AgentFrameworkSession
    from agent_framework import ChatMessage, TextContent
except Exception as e:
    CHAT_AVAILABLE = False
    CHAT_ERROR_MSG = str(e)
    # Define fallback constants
    AGENT_NAMES = {
        "rfp_compliance": "RFPCompliance",
        "legal_compliance": "LegalCompliance", 
        "vendor_evaluation": "VendorEvaluation",
        "market_intelligence": "MarketIntelligence",
        "negotiation_strategy": "NegotiationStrategy",
        "evaluation_report": "EvaluationReport",
    }

st.set_page_config(page_title="Project Chat", page_icon="💬", layout="wide")

load_dotenv()


def load_css(file_path):
    with open(file_path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


css_path = pathlib.Path(__file__).parent.parent / "style.css"
if css_path.exists():
    load_css(css_path)

image_path1 = os.path.join(os.path.dirname(__file__), "..", "static", "image1.png")
image_path2 = os.path.join(os.path.dirname(__file__), "..", "static", "image3.jpg")

LOGO_URL_LARGE = Image.open(image_path1)
st.logo(LOGO_URL_LARGE, size="large")

MARKET_INTELLIGENCE_DATASET = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "documents", "market-intelligence.json")
)

legal_policy_index = os.getenv("LEGAL_POLICY_INDEX")
supplier_insights_index = os.getenv("SUPPLIER_INDEX")

# Agent styling
AGENT_LOGOS = {
    AGENT_NAMES["rfp_compliance"]: "📜",
    AGENT_NAMES["legal_compliance"]: "⚖️",
    AGENT_NAMES["vendor_evaluation"]: "🏢",
    AGENT_NAMES["market_intelligence"]: "📊",
    AGENT_NAMES["negotiation_strategy"]: "🤝",
    AGENT_NAMES["evaluation_report"]: "📑",
}

USER_LOGO = "https://cdn.pixabay.com/photo/2016/03/31/17/33/avatar-1293744_1280.png"
SYSTEM_LOGO = "https://cdn.pixabay.com/photo/2016/03/31/18/43/gear-1294576_1280.png"

# Initialize services
project_service = ProjectService()

# Session state initialization
if "project_chat_messages" not in st.session_state:
    st.session_state.project_chat_messages = []
if "project_chat_session" not in st.session_state:
    st.session_state.project_chat_session = None
if "project_chat_initialized" not in st.session_state:
    st.session_state.project_chat_initialized = False


def get_active_project() -> Optional[Project]:
    """Get the currently active project."""
    project_id = st.session_state.get("active_project_id")
    if not project_id:
        return None
    return project_service.get_project(project_id)


async def build_project_context(project: Project) -> VendorContext:
    """Build the vendor context from project data."""
    rfp_summary = project.rfp_summary or ""

    # Get first proposal summary if available
    proposals = project.get_proposal_documents()
    proposal_summary = {}
    if proposals and proposals[0].summary:
        proposal_summary = proposals[0].summary

    # Fetch policy context
    azure_endpoint = os.environ.get("AZURE_AI_SEARCH_ENDPOINT")
    azure_api_key = os.environ.get("AZURE_AI_SEARCH_API_KEY")

    policy_context = "Azure AI Search legal policy index is not configured."
    if azure_endpoint and azure_api_key and legal_policy_index:
        legal_search_client = SearchClient(
            endpoint=azure_endpoint,
            index_name=legal_policy_index,
            credential=AzureKeyCredential(azure_api_key),
        )
        legal_summary = proposal_summary.get("legal_summary", "") if isinstance(proposal_summary, dict) else ""
        legal_compliance_plugin = LegalCompliancePlugin(
            search_client=legal_search_client,
            vendor_legal_summary=legal_summary,
        )
        policy_context = await legal_compliance_plugin.check_compliance()

    vendor_insights = "Azure AI Search supplier insights index is not configured."
    if azure_endpoint and azure_api_key and supplier_insights_index:
        vendor_search_client = SearchClient(
            endpoint=azure_endpoint,
            index_name=supplier_insights_index,
            credential=AzureKeyCredential(azure_api_key),
        )
        vendor_name = proposal_summary.get("vendor_name", "Unknown Vendor") if isinstance(proposal_summary, dict) else "Unknown Vendor"
        vendor_evaluation_plugin = VendorEvaluationPlugin(
            search_client=vendor_search_client,
            vendor_name=vendor_name,
        )
        vendor_insights = await vendor_evaluation_plugin.get_vendor_insights()

    market_intelligence_plugin = MarketIntelligencePlugin(MARKET_INTELLIGENCE_DATASET)
    market_insights = market_intelligence_plugin.get_market_insights("Cloud Computing")

    return VendorContext(
        rfp_summary=rfp_summary,
        proposal_summary=proposal_summary,
        policy_context=policy_context,
        vendor_insights=vendor_insights,
        market_insights=market_insights,
    )


async def initialize_project_chat(
    project: Project,
    stream_handler: Optional[Callable[[str, str], None]] = None,
):
    """Initialize the chat session for a project."""
    prompt_instructions = get_agent_prompts()
    context = await build_project_context(project)

    session = AgentFrameworkSession(
        agent_prompts=prompt_instructions,
        rfp_summary=context.rfp_summary,
        proposal_summary=context.proposal_summary,
        policy_context=context.policy_context,
        vendor_insights=context.vendor_insights,
        market_insights=context.market_insights,
    )

    initial_messages = await session.bootstrap(stream_handler=stream_handler)
    return session, initial_messages


def render_sidebar(project: Optional[Project]):
    """Render the sidebar."""
    with st.sidebar:
        st.image(image_path2, width=160)

        if project:
            st.markdown(f"### 📁 {project.name}")
            st.caption(f"Status: {project.status.value}")

            if st.button("← Back to Project", use_container_width=True):
                st.session_state.project_view_mode = "detail"
                st.session_state.current_project_id = project.id
                st.switch_page("pages/0_Projects.py")

            st.markdown("---")

            # Show project context
            with st.expander("📄 Project Context", expanded=False):
                rfp_doc = project.get_rfp_document()
                if rfp_doc:
                    st.markdown(f"**RFP:** {rfp_doc.name}")

                proposals = project.get_proposal_documents()
                if proposals:
                    st.markdown(f"**Proposals:** {len(proposals)}")
                    for p in proposals:
                        st.caption(f"• {p.name}")

                st.markdown("**Enabled Agents:**")
                for agent in project.enabled_agents:
                    st.caption(f"• {agent.value}")

            if st.button("🔄 Reset Chat", use_container_width=True):
                st.session_state.project_chat_messages = []
                st.session_state.project_chat_session = None
                st.session_state.project_chat_initialized = False
                st.rerun()

        else:
            st.warning("No project selected")
            if st.button("Go to Projects", use_container_width=True):
                st.switch_page("pages/0_Projects.py")

        st.markdown("---")
        st.caption("Powered by Azure OpenAI")


def render_project_info(project: Project):
    """Render project information header."""
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(image_path2, width=80)
    with col2:
        st.title(f"💬 {project.name} - Chat")
        st.caption(
            f"Ask questions about the RFP, proposals, and analysis results. "
            f"Enabled agents: {', '.join(a.value for a in project.enabled_agents)}"
        )


def render_chat_messages():
    """Render the chat message history."""
    for message in st.session_state.project_chat_messages:
        role = message.get("role", "assistant")
        content = message.get("content", "")

        if role == "user":
            with st.chat_message("user", avatar=USER_LOGO):
                st.markdown("**You:**")
                st.markdown(content)
        elif role == "system":
            with st.chat_message("assistant", avatar=SYSTEM_LOGO):
                st.markdown("**System:**")
                st.markdown(content)
        else:
            agent_logo = AGENT_LOGOS.get(role, "🤖")
            with st.chat_message("assistant", avatar=agent_logo):
                st.markdown(f"**{role} Agent:**")
                st.markdown(content)


def main():
    """Main entry point for the Project Chat page."""
    project = get_active_project()
    render_sidebar(project)

    if not project:
        st.warning("No project selected. Please select a project first.")
        if st.button("Go to Projects"):
            st.switch_page("pages/0_Projects.py")
        return

    # Check if chat functionality is available
    if not CHAT_AVAILABLE:
        st.error(
            "⚠️ Chat functionality is not available. "
            "Azure OpenAI and related services must be configured.\n\n"
            f"Error: {CHAT_ERROR_MSG}"
        )
        if st.button("← Back to Project"):
            st.session_state.project_view_mode = "detail"
            st.session_state.current_project_id = project.id
            st.switch_page("pages/0_Projects.py")
        return

    render_project_info(project)

    # Check if we have necessary data
    if not project.rfp_summary and not project.get_rfp_document():
        st.warning("Please upload an RFP document to the project first.")
        if st.button("Go to Project"):
            st.session_state.project_view_mode = "detail"
            st.session_state.current_project_id = project.id
            st.switch_page("pages/0_Projects.py")
        return

    # Initialize chat session if needed
    just_bootstrapped = False
    if st.session_state.project_chat_session is None:
        bootstrap_stream_context: Dict[str, Dict[str, object]] = {}

        def bootstrap_stream_handler(agent_name: str, chunk: str) -> None:
            if not chunk:
                return

            context = bootstrap_stream_context.get(agent_name)
            if context is None:
                agent_logo = AGENT_LOGOS.get(agent_name, "🤖")
                message_container = st.chat_message("assistant", avatar=agent_logo)
                placeholder = message_container.empty()
                header = f"**{agent_name} Agent:**\n\n"
                placeholder.markdown(header)
                context = {"placeholder": placeholder, "buffer": header}
                bootstrap_stream_context[agent_name] = context

            context = bootstrap_stream_context[agent_name]
            context["buffer"] += chunk
            placeholder = context["placeholder"]
            if hasattr(placeholder, "markdown"):
                placeholder.markdown(context["buffer"])

        with st.spinner("Initializing project chat..."):
            session, initial_messages = asyncio.run(
                initialize_project_chat(project, stream_handler=bootstrap_stream_handler)
            )
            st.session_state.project_chat_session = session
            if not st.session_state.project_chat_initialized:
                st.session_state.project_chat_messages.extend(initial_messages)
                st.session_state.project_chat_initialized = True
                just_bootstrapped = True

    # Welcome message
    if not st.session_state.get("project_welcome_displayed"):
        with st.chat_message("assistant", avatar=SYSTEM_LOGO):
            st.markdown("**System:**")
            st.markdown(
                f"Welcome to the **{project.name}** project chat! "
                "Feel free to ask questions about the RFP, vendor proposals, or request analysis from our agents."
            )
        st.session_state.project_welcome_displayed = True

    # Display previous messages
    if not just_bootstrapped:
        render_chat_messages()

    # Chat input
    prompt = st.chat_input("Ask a question about this project...")

    if prompt:
        # Display user message
        with st.chat_message("user", avatar=USER_LOGO):
            st.markdown("**You:**")
            st.markdown(prompt)

        st.session_state.project_chat_messages.append({"role": "user", "content": prompt})

        # Save to project history
        project_service.add_chat_message(project, "user", prompt)

        # Get agent responses
        stream_context: Dict[str, Dict[str, object]] = {}
        streamed_content: Dict[str, str] = {}

        def stream_handler(agent_name: str, chunk: str) -> None:
            if not chunk:
                return

            context = stream_context.get(agent_name)
            if context is None:
                agent_logo = AGENT_LOGOS.get(agent_name, "🤖")
                message_container = st.chat_message("assistant", avatar=agent_logo)
                placeholder = message_container.empty()
                header = f"**{agent_name} Agent:**\n\n"
                placeholder.markdown(header)
                context = {"placeholder": placeholder, "buffer": header}
                stream_context[agent_name] = context
                streamed_content[agent_name] = ""

            context = stream_context[agent_name]
            context["buffer"] += chunk
            context_placeholder = context["placeholder"]
            if hasattr(context_placeholder, "markdown"):
                context_placeholder.markdown(context["buffer"])
            streamed_content[agent_name] = streamed_content.get(agent_name, "") + chunk

        agent_responses = asyncio.run(
            st.session_state.project_chat_session.handle_user_prompt_streaming(
                prompt,
                stream_handler=stream_handler,
            )
        )

        for agent_name, agent_text in agent_responses:
            if not agent_text:
                agent_text = streamed_content.get(agent_name, "")
            if not agent_text:
                continue
            st.session_state.project_chat_messages.append(
                {"role": agent_name, "content": agent_text}
            )
            # Save to project history
            project_service.add_chat_message(project, agent_name, agent_text, agent_name)

        st.rerun()


if __name__ == "__main__":
    main()
