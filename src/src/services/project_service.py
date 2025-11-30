"""Project management service for RFP Copilot.

This module provides functionality to create, manage, and persist projects.
A project is a container for RFP documents, vendor proposals, and associated
analysis state that can be used for incremental procurement workflows.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    """Return current UTC time as ISO format string."""
    return datetime.now(timezone.utc).isoformat()


class DocumentType(str, Enum):
    """Types of documents that can be uploaded to a project."""
    RFP = "rfp"
    PROPOSAL = "proposal"
    SUPPORTING = "supporting"


class AgentType(str, Enum):
    """Agent types available for analysis."""
    RFP_COMPLIANCE = "rfp_compliance"
    LEGAL_COMPLIANCE = "legal_compliance"
    VENDOR_EVALUATION = "vendor_evaluation"
    MARKET_INTELLIGENCE = "market_intelligence"
    NEGOTIATION_STRATEGY = "negotiation_strategy"
    EVALUATION_REPORT = "evaluation_report"


# Default agents for new projects (can be overridden via configuration)
DEFAULT_ENABLED_AGENTS = [AgentType.RFP_COMPLIANCE, AgentType.LEGAL_COMPLIANCE]


class ProjectStatus(str, Enum):
    """Status of a project in the procurement workflow."""
    DRAFT = "draft"
    RFP_UPLOADED = "rfp_uploaded"
    PROPOSALS_UPLOADED = "proposals_uploaded"
    ANALYSIS_IN_PROGRESS = "analysis_in_progress"
    ANALYSIS_COMPLETE = "analysis_complete"
    ARCHIVED = "archived"


@dataclass
class ProjectDocument:
    """Represents a document within a project."""
    id: str
    name: str
    doc_type: DocumentType
    uploaded_at: str
    summary: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "doc_type": self.doc_type.value,
            "uploaded_at": self.uploaded_at,
            "summary": self.summary,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectDocument":
        return cls(
            id=data["id"],
            name=data["name"],
            doc_type=DocumentType(data["doc_type"]),
            uploaded_at=data["uploaded_at"],
            summary=data.get("summary"),
            file_path=data.get("file_path"),
        )


@dataclass
class AgentOutput:
    """Stores the output from a specific agent for a vendor."""
    agent_type: AgentType
    output: str
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_type": self.agent_type.value,
            "output": self.output,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentOutput":
        return cls(
            agent_type=AgentType(data["agent_type"]),
            output=data["output"],
            generated_at=data["generated_at"],
        )


@dataclass
class VendorAnalysis:
    """Analysis results for a specific vendor proposal."""
    vendor_id: str
    vendor_name: str
    document_id: str
    agent_outputs: Dict[str, AgentOutput] = field(default_factory=dict)
    comparison_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "document_id": self.document_id,
            "agent_outputs": {k: v.to_dict() for k, v in self.agent_outputs.items()},
            "comparison_summary": self.comparison_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VendorAnalysis":
        agent_outputs = {}
        for k, v in data.get("agent_outputs", {}).items():
            agent_outputs[k] = AgentOutput.from_dict(v)
        return cls(
            vendor_id=data["vendor_id"],
            vendor_name=data["vendor_name"],
            document_id=data["document_id"],
            agent_outputs=agent_outputs,
            comparison_summary=data.get("comparison_summary"),
        )


@dataclass
class ChatMessage:
    """A message in the project chat history."""
    role: str
    content: str
    timestamp: str
    agent_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "agent_name": self.agent_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
            agent_name=data.get("agent_name"),
        )


@dataclass
class Project:
    """Represents a procurement project containing RFP and vendor proposals."""
    id: str
    name: str
    description: str
    created_at: str
    updated_at: str
    status: ProjectStatus
    documents: List[ProjectDocument] = field(default_factory=list)
    vendor_analyses: List[VendorAnalysis] = field(default_factory=list)
    enabled_agents: List[AgentType] = field(default_factory=list)
    chat_history: List[ChatMessage] = field(default_factory=list)
    rfp_summary: Optional[str] = None
    comparison_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "documents": [doc.to_dict() for doc in self.documents],
            "vendor_analyses": [va.to_dict() for va in self.vendor_analyses],
            "enabled_agents": [agent.value for agent in self.enabled_agents],
            "chat_history": [msg.to_dict() for msg in self.chat_history],
            "rfp_summary": self.rfp_summary,
            "comparison_summary": self.comparison_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        documents = [ProjectDocument.from_dict(d) for d in data.get("documents", [])]
        vendor_analyses = [VendorAnalysis.from_dict(v) for v in data.get("vendor_analyses", [])]
        enabled_agents = [AgentType(a) for a in data.get("enabled_agents", [])]
        chat_history = [ChatMessage.from_dict(m) for m in data.get("chat_history", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            status=ProjectStatus(data["status"]),
            documents=documents,
            vendor_analyses=vendor_analyses,
            enabled_agents=enabled_agents,
            chat_history=chat_history,
            rfp_summary=data.get("rfp_summary"),
            comparison_summary=data.get("comparison_summary"),
        )

    def get_rfp_document(self) -> Optional[ProjectDocument]:
        """Return the RFP document if one exists."""
        for doc in self.documents:
            if doc.doc_type == DocumentType.RFP:
                return doc
        return None

    def get_proposal_documents(self) -> List[ProjectDocument]:
        """Return all proposal documents."""
        return [doc for doc in self.documents if doc.doc_type == DocumentType.PROPOSAL]

    def get_supporting_documents(self) -> List[ProjectDocument]:
        """Return all supporting documents."""
        return [doc for doc in self.documents if doc.doc_type == DocumentType.SUPPORTING]


class ProjectStorage:
    """Handles persistence of projects to disk."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            storage_dir = os.path.join(
                os.path.dirname(__file__), "..", "data", "projects"
            )
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.storage_dir / "index.json"

    def _validate_project_id(self, project_id: str) -> None:
        """Validate project ID to prevent path traversal attacks."""
        if not project_id:
            raise ValueError("Project ID cannot be empty.")
        # Check for path traversal attempts
        if ".." in project_id or "/" in project_id or "\\" in project_id:
            raise ValueError("Invalid project ID format.")
        # Only allow alphanumeric, hyphens, and underscores (UUID format)
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', project_id):
            raise ValueError("Invalid project ID format.")

    def _get_project_path(self, project_id: str) -> Path:
        self._validate_project_id(project_id)
        path = self.storage_dir / f"{project_id}.json"
        # Ensure the resolved path is within the storage directory
        if not path.resolve().is_relative_to(self.storage_dir):
            raise ValueError("Invalid project path.")
        return path

    def _load_index(self) -> Dict[str, Any]:
        if self._index_file.exists():
            with open(self._index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"projects": []}

    def _save_index(self, index: Dict[str, Any]) -> None:
        with open(self._index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

    def save(self, project: Project) -> None:
        """Save a project to disk."""
        project_path = self._get_project_path(project.id)
        with open(project_path, "w", encoding="utf-8") as f:
            json.dump(project.to_dict(), f, indent=2)

        # Update index
        index = self._load_index()
        project_entry = {
            "id": project.id,
            "name": project.name,
            "status": project.status.value,
            "updated_at": project.updated_at,
        }
        existing_ids = {p["id"] for p in index["projects"]}
        if project.id in existing_ids:
            index["projects"] = [
                project_entry if p["id"] == project.id else p
                for p in index["projects"]
            ]
        else:
            index["projects"].append(project_entry)
        self._save_index(index)

    def load(self, project_id: str) -> Optional[Project]:
        """Load a project from disk."""
        project_path = self._get_project_path(project_id)
        if not project_path.exists():
            return None
        with open(project_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Project.from_dict(data)

    def delete(self, project_id: str) -> bool:
        """Delete a project from disk."""
        project_path = self._get_project_path(project_id)
        if project_path.exists():
            project_path.unlink()
            # Update index
            index = self._load_index()
            index["projects"] = [p for p in index["projects"] if p["id"] != project_id]
            self._save_index(index)
            return True
        return False

    def list_all(self) -> List[Dict[str, Any]]:
        """List all project summaries."""
        index = self._load_index()
        return index.get("projects", [])


class ProjectService:
    """Service for managing procurement projects."""

    def __init__(self, storage: Optional[ProjectStorage] = None):
        self.storage = storage or ProjectStorage()

    def create_project(
        self,
        name: str,
        description: str = "",
        enabled_agents: Optional[List[AgentType]] = None,
    ) -> Project:
        """Create a new project."""
        now = _utc_now()
        if enabled_agents is None:
            enabled_agents = list(DEFAULT_ENABLED_AGENTS)

        project = Project(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
            status=ProjectStatus.DRAFT,
            enabled_agents=enabled_agents,
        )
        self.storage.save(project)
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Retrieve a project by ID."""
        return self.storage.load(project_id)

    def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        project.updated_at = _utc_now()
        self.storage.save(project)
        return project

    def delete_project(self, project_id: str) -> bool:
        """Delete a project."""
        return self.storage.delete(project_id)

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects."""
        return self.storage.list_all()

    def add_document(
        self,
        project: Project,
        name: str,
        doc_type: DocumentType,
        summary: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
    ) -> ProjectDocument:
        """Add a document to a project."""
        doc = ProjectDocument(
            id=str(uuid.uuid4()),
            name=name,
            doc_type=doc_type,
            uploaded_at=_utc_now(),
            summary=summary,
            file_path=file_path,
        )
        project.documents.append(doc)

        # Update project status based on documents
        if doc_type == DocumentType.RFP:
            if project.status == ProjectStatus.DRAFT:
                project.status = ProjectStatus.RFP_UPLOADED
        elif doc_type == DocumentType.PROPOSAL:
            if project.status in [ProjectStatus.DRAFT, ProjectStatus.RFP_UPLOADED]:
                project.status = ProjectStatus.PROPOSALS_UPLOADED

        self.update_project(project)
        return doc

    def remove_document(self, project: Project, document_id: str) -> bool:
        """Remove a document from a project."""
        original_count = len(project.documents)
        project.documents = [d for d in project.documents if d.id != document_id]
        if len(project.documents) < original_count:
            self.update_project(project)
            return True
        return False

    def update_enabled_agents(
        self, project: Project, agents: List[AgentType]
    ) -> Project:
        """Update the list of enabled agents for a project."""
        project.enabled_agents = agents
        return self.update_project(project)

    def add_vendor_analysis(
        self,
        project: Project,
        vendor_name: str,
        document_id: str,
    ) -> VendorAnalysis:
        """Add a vendor analysis entry to a project."""
        analysis = VendorAnalysis(
            vendor_id=str(uuid.uuid4()),
            vendor_name=vendor_name,
            document_id=document_id,
        )
        project.vendor_analyses.append(analysis)
        self.update_project(project)
        return analysis

    def update_vendor_analysis(
        self,
        project: Project,
        vendor_id: str,
        agent_type: AgentType,
        output: str,
    ) -> Optional[VendorAnalysis]:
        """Update the analysis output for a vendor."""
        for analysis in project.vendor_analyses:
            if analysis.vendor_id == vendor_id:
                analysis.agent_outputs[agent_type.value] = AgentOutput(
                    agent_type=agent_type,
                    output=output,
                    generated_at=_utc_now(),
                )
                self.update_project(project)
                return analysis
        return None

    def add_chat_message(
        self,
        project: Project,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
    ) -> ChatMessage:
        """Add a chat message to the project history."""
        message = ChatMessage(
            role=role,
            content=content,
            timestamp=_utc_now(),
            agent_name=agent_name,
        )
        project.chat_history.append(message)
        self.update_project(project)
        return message

    def get_project_context(self, project: Project) -> Dict[str, Any]:
        """Get the full context of a project for chat/analysis."""
        return {
            "project_id": project.id,
            "project_name": project.name,
            "rfp_summary": project.rfp_summary,
            "documents": [
                {
                    "id": doc.id,
                    "name": doc.name,
                    "type": doc.doc_type.value,
                    "summary": doc.summary,
                }
                for doc in project.documents
            ],
            "vendor_analyses": [
                {
                    "vendor_id": va.vendor_id,
                    "vendor_name": va.vendor_name,
                    "outputs": {k: v.output for k, v in va.agent_outputs.items()},
                }
                for va in project.vendor_analyses
            ],
            "enabled_agents": [a.value for a in project.enabled_agents],
        }
