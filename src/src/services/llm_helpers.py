"""Shared helper utilities for working with Microsoft Agent Framework chat clients."""
from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Any, Dict

import pandas as pd

from app import create_chat_client


@lru_cache(maxsize=1)
def get_chat_client():
    """Return a cached Azure OpenAI chat client instance."""

    return create_chat_client()


def _ensure_serialisable_records(df: pd.DataFrame, *, max_rows: int = 25) -> list[Dict[str, Any]]:
    limited = df.copy()
    if len(limited) > max_rows:
        limited = limited.head(max_rows)
    return json.loads(limited.to_json(orient="records", date_format="iso"))


async def _run_agent_async(name: str, instructions: str, message: str) -> str:
    client = get_chat_client()
    agent = client.create_agent(name=name, instructions=instructions, description=instructions.splitlines()[0][:80])
    thread = agent.get_new_thread()
    result = await agent.run(message, thread=thread)
    return result.text if result and result.text else ""


def run_agent_sync(name: str, instructions: str, message: str) -> str:
    async def _runner():
        return await _run_agent_async(name, instructions, message)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(_runner())
        finally:
            new_loop.close()
    return asyncio.run(_runner())


def dataframe_to_pretty_json(df: pd.DataFrame, *, max_rows: int = 20) -> str:
    records = _ensure_serialisable_records(df, max_rows=max_rows)
    return json.dumps(records, indent=2)
