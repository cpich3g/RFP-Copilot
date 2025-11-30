"""Plugin to assess vendor credibility by retrieving historical insights from Azure AI Search."""

from typing import Any, Dict, List, Optional

from azure.search.documents import SearchClient
from azure.search.documents.models import (
    QueryAnswerType,
    QueryCaptionType,
    QueryType,
    VectorizableTextQuery,
)


class VendorEvaluationPlugin:
    """Plugin to assess vendor credibility by retrieving historical insights from Azure AI Search."""

    # Fields to retrieve from the search index
    SEARCH_FIELDS = [
        "chunk",
        "past_clients",
        "industries_served",
        "customer_satisfaction_avg",
        "financial_growth_5y",
        "compliance_issues",
        "market_growth",
        "bbb_accreditation",
        "contract_disputes",
        "notes",
    ]

    def __init__(self, search_client: SearchClient, vendor_name: str) -> None:
        """Initialize the Vendor Evaluation Plugin.

        Args:
            search_client: Azure AI Search client instance.
            vendor_name: Name of the vendor being evaluated.
        """
        self.search_client = search_client
        self.vendor_name = vendor_name

    async def get_vendor_insights(self) -> str:
        """Retrieve vendor reputation insights from the search index.
        
        Returns:
            Formatted string with historical insights about the vendor,
            or an error message if no data is found.
        """
        vector_query = VectorizableTextQuery(
            text=self.vendor_name,
            k_nearest_neighbors=1,
            fields="text_vector",
            exhaustive=True,
        )

        results = self.search_client.search(
            search_text=self.vendor_name,
            vector_queries=[vector_query],
            select=self.SEARCH_FIELDS,
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name="supplier-insights-index-semantic-configuration",
            query_caption=QueryCaptionType.EXTRACTIVE,
            query_answer=QueryAnswerType.EXTRACTIVE,
            top=1,
        )

        vendor_record: Optional[Dict[str, Any]] = next(iter(results), None)
        
        if not vendor_record:
            return "No historical data found for this vendor. Ensure the index is correctly populated."
        
        return self._format_vendor_insights(vendor_record)

    def _format_vendor_insights(self, vendor_record: Dict[str, Any]) -> str:
        """Format vendor record into a readable Markdown string.
        
        Args:
            vendor_record: Dictionary containing vendor data from search.
            
        Returns:
            Formatted Markdown string with vendor insights.
        """
        def _format_list(items: Any) -> str:
            """Safely format a list of items as comma-separated string."""
            if isinstance(items, list):
                return ", ".join(str(item) for item in items)
            return str(items) if items else "Not available"

        def _format_value(value: Any) -> str:
            """Safely format any value for display."""
            if value is None:
                return "Not available"
            return str(value)

        return (
            f"### **Vendor:** {vendor_record.get('chunk', 'Unknown')}\n"
            f"- **Past Clients:** {_format_list(vendor_record.get('past_clients'))}\n"
            f"- **Industries Served:** {_format_list(vendor_record.get('industries_served'))}\n"
            f"- **Customer Satisfaction:** {_format_value(vendor_record.get('customer_satisfaction_avg'))}%\n"
            f"- **Financial Growth (5y):** {_format_value(vendor_record.get('financial_growth_5y'))}\n"
            f"- **Compliance Issues:** {_format_value(vendor_record.get('compliance_issues'))}\n"
            f"- **Market Growth:** {_format_value(vendor_record.get('market_growth'))}\n"
            f"- **BBB Accreditation:** {_format_value(vendor_record.get('bbb_accreditation'))}\n"
            f"- **Contract Disputes:** {_format_value(vendor_record.get('contract_disputes'))}\n"
            f"- **Additional Notes:** {_format_value(vendor_record.get('notes'))}\n"
        )