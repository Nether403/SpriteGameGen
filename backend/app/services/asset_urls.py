"""Versioned URLs for mutable project assets."""
from __future__ import annotations

from uuid import uuid4


def asset_url(project_id: str, filename: str) -> str:
    """Return a cache-busting URL for an asset just written to a project."""
    return f"/projects/{project_id}/{filename}?v={uuid4().hex}"
