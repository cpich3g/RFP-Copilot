"""Shared helper utilities for working with Microsoft Agent Framework chat clients."""
from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Any, Dict, List

import pandas as pd

from app import create_chat_client

# Maximum rows to include when serializing DataFrames to prevent memory issues
MAX_DATAFRAME_ROWS = 25


@lru_cache(maxsize=1)
def get_chat_client():
    """Return a cached Azure OpenAI chat client instance."""
    return create_chat_client()


def _ensure_serialisable_records(
    df: pd.DataFrame,
    *,
    max_rows: int = MAX_DATAFRAME_ROWS,
) -> List[Dict[str, Any]]:
    """Convert DataFrame to JSON-serializable records with row limit.
    
    Args:
        df: The DataFrame to convert.
        max_rows: Maximum number of rows to include.
        
    Returns:
        List of dictionaries representing the DataFrame rows.
    """
    limited = df.copy()
    if len(limited) > max_rows:
        limited = limited.head(max_rows)
    return json.loads(limited.to_json(orient="records", date_format="iso"))


async def _run_agent_async(name: str, instructions: str, message: str) -> str:
    """Run an agent asynchronously and return the response text.
    
    Args:
        name: The agent name.
        instructions: Instructions for the agent.
        message: The message to send to the agent.
        
    Returns:
        The agent's response text, or empty string if no response.
    """
    client = get_chat_client()
    agent = client.create_agent(
        name=name,
        instructions=instructions,
        description=instructions.splitlines()[0][:80],
    )
    thread = agent.get_new_thread()
    result = await agent.run(message, thread=thread)
    return result.text if result and result.text else ""


def run_agent_sync(name: str, instructions: str, message: str) -> str:
    """Run an agent synchronously, handling event loop context properly.
    
    This function handles the case where it may be called from within an
    existing async context (e.g., Streamlit) or from synchronous code.
    
    Args:
        name: The agent name.
        instructions: Instructions for the agent.
        message: The message to send to the agent.
        
    Returns:
        The agent's response text, or empty string if no response.
    """
    async def _runner() -> str:
        return await _run_agent_async(name, instructions, message)

    # Check if we're in an async context
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - safe to use asyncio.run()
        return asyncio.run(_runner())

    # We're inside a running loop - need to run in a new thread
    # to avoid "cannot be called from a running event loop" error
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _runner())
        return future.result()


def dataframe_to_pretty_json(df: pd.DataFrame, *, max_rows: int = 20) -> str:
    """Convert a DataFrame to a pretty-printed JSON string.
    
    Args:
        df: The DataFrame to convert.
        max_rows: Maximum number of rows to include.
        
    Returns:
        Pretty-printed JSON string representation.
    """
    records = _ensure_serialisable_records(df, max_rows=max_rows)
    return json.dumps(records, indent=2)
