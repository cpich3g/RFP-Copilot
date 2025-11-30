"""Plugin to assess vendor legal compliance by retrieving relevant policies from Azure AI Search."""

from typing import List

from azure.search.documents import SearchClient
from azure.search.documents.models import (
    QueryAnswerType,
    QueryCaptionType,
    QueryType,
    VectorizableTextQuery,
)


class LegalCompliancePlugin:
    """Plugin to assess vendor legal compliance by retrieving relevant policies.
    
    Uses Azure AI Search to find and retrieve legal and regulatory policies
    that may be relevant to the vendor proposal's legal summary.
    """

    # Search configuration constants
    K_NEAREST_NEIGHBORS = 50
    TOP_RESULTS = 5
    SEMANTIC_CONFIG_NAME = "legal-policy-index-semantic-configuration"

    def __init__(self, search_client: SearchClient, vendor_legal_summary: str) -> None:
        """Initialize the Legal Compliance Plugin.

        Args:
            search_client: Azure AI Search client instance.
            vendor_legal_summary: The legal-related section of the vendor proposal.
        """
        self.search_client = search_client
        self.vendor_legal_summary = vendor_legal_summary

    async def check_compliance(self) -> str:
        """Perform legal compliance check for a given vendor's legal summary.

        Returns:
            Retrieved legal policy context as a formatted string,
            or an error message if no policies are found.
        """
        vector_query = VectorizableTextQuery(
            text=self.vendor_legal_summary,
            k_nearest_neighbors=self.K_NEAREST_NEIGHBORS,
            fields="text_vector",
            exhaustive=True,
        )

        results = self.search_client.search(
            search_text=self.vendor_legal_summary,
            vector_queries=[vector_query],
            select=["chunk"],
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name=self.SEMANTIC_CONFIG_NAME,
            query_caption=QueryCaptionType.EXTRACTIVE,
            query_answer=QueryAnswerType.EXTRACTIVE,
            top=self.TOP_RESULTS,
        )

        # Extract and join policy chunks
        policy_chunks: List[str] = []
        for doc in results:
            chunk = doc.get("chunk")
            if chunk:
                policy_chunks.append(str(chunk))

        if not policy_chunks:
            return "No relevant legal policies found. Ensure the policies are indexed correctly."

        return "\n\n".join(policy_chunks)