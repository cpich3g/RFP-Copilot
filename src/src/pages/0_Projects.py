"""Streamlit page for project management.

This page allows users to create, view, and manage procurement projects.
Projects serve as containers for RFP documents, vendor proposals, and
associated analysis that can be conducted incrementally.
"""

from __future__ import annotations

import os
import pathlib
import sys
from time import sleep
from typing import List

import streamlit as st
from PIL import Image

# Add parent directory to path for imports
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from services.project_service import (
    AgentType,
    DocumentType,
    Project,
    ProjectService,
    ProjectStatus,
)
from doc_summarization import summarize_document

st.set_page_config(page_title="Projects", page_icon="📁", layout="wide")


def load_css(file_path):
    with open(file_path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


css_path = pathlib.Path(__file__).parent.parent / "style.css"
if css_path.exists():
    load_css(css_path)

image_path1 = os.path.join(os.path.dirname(__file__), "..", "static", "image1.png")
LOGO_URL_LARGE = Image.open(image_path1)
image_path2 = os.path.join(os.path.dirname(__file__), "..", "static", "image3.jpg")

st.logo(LOGO_URL_LARGE, size="large")

# Initialize service
project_service = ProjectService()

# Session state initialization
if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = None
if "project_view_mode" not in st.session_state:
    st.session_state.project_view_mode = "list"  # list, create, detail


AGENT_LABELS = {
    AgentType.RFP_COMPLIANCE: ("📜 RFP Compliance", "Evaluate proposal alignment with RFP requirements"),
    AgentType.LEGAL_COMPLIANCE: ("⚖️ Legal & Regulatory", "Assess legal and regulatory compliance risks"),
    AgentType.VENDOR_EVALUATION: ("🏢 Vendor Evaluation", "Review vendor reputation and performance history"),
    AgentType.MARKET_INTELLIGENCE: ("📊 Market Intelligence", "Analyze market trends and competitive positioning"),
    AgentType.NEGOTIATION_STRATEGY: ("🤝 Negotiation Strategy", "Generate negotiation recommendations"),
    AgentType.EVALUATION_REPORT: ("📑 Evaluation Report", "Compile consolidated evaluation report"),
}

STATUS_BADGES = {
    ProjectStatus.DRAFT: ("🔵", "Draft"),
    ProjectStatus.RFP_UPLOADED: ("🟡", "RFP Uploaded"),
    ProjectStatus.PROPOSALS_UPLOADED: ("🟠", "Proposals Uploaded"),
    ProjectStatus.ANALYSIS_IN_PROGRESS: ("🟣", "Analysis In Progress"),
    ProjectStatus.ANALYSIS_COMPLETE: ("🟢", "Complete"),
    ProjectStatus.ARCHIVED: ("⚫", "Archived"),
}


def render_sidebar():
    """Render the sidebar with navigation and instructions."""
    with st.sidebar:
        st.image(image_path2, width=160)
        st.markdown("### Project Management")
        st.info(
            "**Projects** allow you to:\n"
            "1. Upload RFP and proposals incrementally\n"
            "2. Select which agents to run at each stage\n"
            "3. Maintain state across sessions\n"
            "4. Chat within project context"
        )
        st.markdown("---")

        if st.button("📁 View All Projects", use_container_width=True):
            st.session_state.project_view_mode = "list"
            st.session_state.current_project_id = None
            st.rerun()

        if st.button("➕ Create New Project", use_container_width=True):
            st.session_state.project_view_mode = "create"
            st.rerun()

        st.markdown("---")
        st.caption("Powered by Azure OpenAI")


def render_project_list():
    """Render the list of all projects."""
    st.title("📁 Procurement Projects")
    st.markdown("Manage your RFP analysis projects. Create a new project or continue working on an existing one.")

    projects = project_service.list_projects()

    if not projects:
        st.info("No projects yet. Click 'Create New Project' to get started.")
        if st.button("➕ Create Your First Project", type="primary"):
            st.session_state.project_view_mode = "create"
            st.rerun()
        return

    # Project cards
    cols = st.columns(3)
    for idx, project_info in enumerate(projects):
        col = cols[idx % 3]
        with col:
            status = ProjectStatus(project_info.get("status", "draft"))
            status_emoji, status_label = STATUS_BADGES.get(status, ("⚪", "Unknown"))

            with st.container(border=True):
                st.markdown(f"### {project_info['name']}")
                st.caption(f"{status_emoji} {status_label}")
                st.caption(f"Updated: {project_info.get('updated_at', 'N/A')[:10]}")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Open", key=f"open_{project_info['id']}", use_container_width=True):
                        st.session_state.current_project_id = project_info["id"]
                        st.session_state.project_view_mode = "detail"
                        st.rerun()
                with col2:
                    if st.button("🗑️", key=f"delete_{project_info['id']}", use_container_width=True):
                        project_service.delete_project(project_info["id"])
                        st.rerun()


def render_create_project():
    """Render the project creation form."""
    st.title("➕ Create New Project")
    st.markdown("Set up a new procurement project to analyze RFPs and vendor proposals.")

    with st.form("create_project_form"):
        name = st.text_input("Project Name", placeholder="e.g., Cloud Services RFP 2025")
        description = st.text_area(
            "Description",
            placeholder="Brief description of the procurement objective...",
        )

        st.markdown("### Select Initial Agents")
        st.caption(
            "Choose which agents to enable for this project. You can modify this later. "
            "For initial RFP review, typically only Compliance and Legal are needed."
        )

        selected_agents: List[AgentType] = []
        cols = st.columns(2)
        for idx, (agent_type, (label, desc)) in enumerate(AGENT_LABELS.items()):
            col = cols[idx % 2]
            with col:
                # Default to RFP and Legal compliance for initial setup
                default = agent_type in [AgentType.RFP_COMPLIANCE, AgentType.LEGAL_COMPLIANCE]
                if st.checkbox(label, value=default, help=desc, key=f"agent_{agent_type.value}"):
                    selected_agents.append(agent_type)

        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Create Project", type="primary", use_container_width=True)
        with col2:
            cancelled = st.form_submit_button("Cancel", use_container_width=True)

    if submitted:
        if not name:
            st.error("Please provide a project name.")
        else:
            project = project_service.create_project(
                name=name,
                description=description,
                enabled_agents=selected_agents if selected_agents else None,
            )
            st.success(f"Project '{name}' created successfully!")
            sleep(1)
            st.session_state.current_project_id = project.id
            st.session_state.project_view_mode = "detail"
            st.rerun()

    if cancelled:
        st.session_state.project_view_mode = "list"
        st.rerun()


def render_document_upload(project: Project):
    """Render the document upload section."""
    st.subheader("📤 Upload Documents")

    tabs = st.tabs(["RFP Document", "Vendor Proposals", "Supporting Documents"])

    with tabs[0]:
        rfp_doc = project.get_rfp_document()
        if rfp_doc:
            st.success(f"✅ RFP uploaded: {rfp_doc.name}")
            if st.button("Replace RFP", key="replace_rfp"):
                project_service.remove_document(project, rfp_doc.id)
                st.rerun()
        else:
            rfp_file = st.file_uploader(
                "Upload RFP Document",
                type=["pdf", "docx", "txt"],
                key="rfp_upload",
            )
            if rfp_file:
                with st.spinner("Processing RFP document..."):
                    rfp_file.seek(0)
                    summary = summarize_document(rfp_file, "rfp")
                    project_service.add_document(
                        project,
                        name=rfp_file.name,
                        doc_type=DocumentType.RFP,
                        summary={"content": summary} if isinstance(summary, str) else summary,
                    )
                    project.rfp_summary = summary if isinstance(summary, str) else summary.get("content", "")
                    project_service.update_project(project)
                st.success("RFP uploaded and summarized!")
                st.rerun()

    with tabs[1]:
        proposals = project.get_proposal_documents()
        if proposals:
            st.markdown("**Uploaded Proposals:**")
            for prop in proposals:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"📄 {prop.name}")
                with col2:
                    if st.button("🗑️", key=f"del_prop_{prop.id}"):
                        project_service.remove_document(project, prop.id)
                        st.rerun()

        proposal_files = st.file_uploader(
            "Upload Vendor Proposal(s)",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="proposal_upload",
        )
        if proposal_files:
            for prop_file in proposal_files:
                with st.spinner(f"Processing {prop_file.name}..."):
                    prop_file.seek(0)
                    summary = summarize_document(prop_file, "proposal")
                    project_service.add_document(
                        project,
                        name=prop_file.name,
                        doc_type=DocumentType.PROPOSAL,
                        summary=summary if isinstance(summary, dict) else {"content": summary},
                    )
            st.success(f"{len(proposal_files)} proposal(s) uploaded!")
            st.rerun()

    with tabs[2]:
        supporting = project.get_supporting_documents()
        if supporting:
            st.markdown("**Supporting Documents:**")
            for doc in supporting:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"📎 {doc.name}")
                with col2:
                    if st.button("🗑️", key=f"del_supp_{doc.id}"):
                        project_service.remove_document(project, doc.id)
                        st.rerun()

        supp_files = st.file_uploader(
            "Upload Supporting Documents",
            type=["pdf", "docx", "txt", "csv", "xlsx", "json"],
            accept_multiple_files=True,
            key="supporting_upload",
        )
        if supp_files:
            for supp_file in supp_files:
                project_service.add_document(
                    project,
                    name=supp_file.name,
                    doc_type=DocumentType.SUPPORTING,
                )
            st.success(f"{len(supp_files)} supporting document(s) uploaded!")
            st.rerun()


def render_agent_configuration(project: Project):
    """Render agent configuration section."""
    st.subheader("🤖 Agent Configuration")
    st.caption("Select which agents to run for this project. You can enable/disable agents at any stage.")

    with st.form("agent_config_form"):
        selected_agents: List[AgentType] = []
        cols = st.columns(3)
        for idx, (agent_type, (label, desc)) in enumerate(AGENT_LABELS.items()):
            col = cols[idx % 3]
            with col:
                is_enabled = agent_type in project.enabled_agents
                if st.checkbox(label, value=is_enabled, help=desc, key=f"cfg_agent_{agent_type.value}"):
                    selected_agents.append(agent_type)

        if st.form_submit_button("Update Agent Configuration", use_container_width=True):
            project_service.update_enabled_agents(project, selected_agents)
            st.success("Agent configuration updated!")
            st.rerun()


def render_analysis_panel(project: Project):
    """Render the analysis panel."""
    st.subheader("🔬 Run Analysis")

    rfp_doc = project.get_rfp_document()
    proposals = project.get_proposal_documents()

    if not rfp_doc:
        st.warning("Please upload an RFP document to start analysis.")
        return

    if not proposals:
        st.info("Upload vendor proposals to run full analysis. You can still analyze the RFP alone.")

    if not project.enabled_agents:
        st.warning("Please enable at least one agent to run analysis.")
        return

    enabled_labels = [AGENT_LABELS[a][0] for a in project.enabled_agents]
    st.markdown(f"**Enabled Agents:** {', '.join(enabled_labels)}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Run Analysis", type="primary", use_container_width=True):
            # Store project info in session state for chat.py to use
            st.session_state.project_analysis_mode = True
            st.session_state.active_project_id = project.id

            # Prepare session state for existing workflow
            st.session_state.rfp_uploaded = True
            st.session_state.rfp_file = None  # File object not needed, we have summary
            st.session_state.rfp_summary_ready = project.rfp_summary

            if proposals:
                st.session_state.vendor_uploaded = True
                st.session_state.vendor_files = []
                st.session_state.vendor_summaries = [
                    {"file_name": p.name, "summary": p.summary or {}}
                    for p in proposals
                ]
                st.session_state.vendor_summary_ready = st.session_state.vendor_summaries
            else:
                st.session_state.vendor_uploaded = False
                st.session_state.vendor_files = []
                st.session_state.vendor_summaries = []

            st.session_state.chat_ready = True
            st.session_state.process_running = False

            # Update project status
            project.status = ProjectStatus.ANALYSIS_IN_PROGRESS
            project_service.update_project(project)

            st.success("Analysis context prepared! Redirecting...")
            sleep(1)
            st.switch_page("pages/chat.py")

    with col2:
        if st.button("💬 Open Project Chat", use_container_width=True):
            st.session_state.project_chat_mode = True
            st.session_state.active_project_id = project.id
            st.switch_page("pages/3_Project_Chat.py")


def render_project_summary(project: Project):
    """Render the project summary panel."""
    st.subheader("📊 Project Summary")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Documents", len(project.documents))
    with col2:
        st.metric("Proposals", len(project.get_proposal_documents()))
    with col3:
        st.metric("Analyses", len(project.vendor_analyses))

    if project.rfp_summary:
        with st.expander("📄 RFP Summary", expanded=False):
            st.markdown(project.rfp_summary)

    if project.vendor_analyses:
        with st.expander("📑 Vendor Analysis Results", expanded=False):
            for va in project.vendor_analyses:
                st.markdown(f"### {va.vendor_name}")
                for agent_key, output in va.agent_outputs.items():
                    st.markdown(f"**{agent_key}:**")
                    st.markdown(output.output[:500] + "..." if len(output.output) > 500 else output.output)


def render_project_detail():
    """Render the project detail view."""
    project = project_service.get_project(st.session_state.current_project_id)
    if not project:
        st.error("Project not found.")
        st.session_state.project_view_mode = "list"
        st.rerun()
        return

    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(f"📁 {project.name}")
        status_emoji, status_label = STATUS_BADGES.get(project.status, ("⚪", "Unknown"))
        st.caption(f"{status_emoji} {status_label} | Created: {project.created_at[:10]}")
    with col2:
        if st.button("← Back to Projects"):
            st.session_state.project_view_mode = "list"
            st.session_state.current_project_id = None
            st.rerun()

    if project.description:
        st.markdown(project.description)

    st.markdown("---")

    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📤 Documents", "🤖 Agents", "🔬 Analysis", "📊 Summary"])

    with tab1:
        render_document_upload(project)

    with tab2:
        render_agent_configuration(project)

    with tab3:
        render_analysis_panel(project)

    with tab4:
        render_project_summary(project)


def main():
    """Main entry point for the Projects page."""
    render_sidebar()

    view_mode = st.session_state.get("project_view_mode", "list")

    if view_mode == "create":
        render_create_project()
    elif view_mode == "detail" and st.session_state.get("current_project_id"):
        render_project_detail()
    else:
        render_project_list()


if __name__ == "__main__":
    main()
