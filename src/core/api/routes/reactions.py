"""Reaction catalog endpoint for the GUI reactions wizard."""

from fastapi import APIRouter

from core.api.models import ReactionCatalogResponse
from core.api.services.reaction_catalog import build_reaction_catalog

router = APIRouter(tags=["Reactions"])


@router.get("/reactions/catalog", response_model=ReactionCatalogResponse)
async def get_reaction_catalog():
    """Return the merged reaction catalog (core events + plugin events/commands).

    The GUI uses this to build the "Create Reaction" wizard without any
    hardcoded per-plugin knowledge.  Plugins self-describe via their
    ``plugin.json`` ``emitted_events`` / ``accepted_commands``.
    """
    return build_reaction_catalog()
