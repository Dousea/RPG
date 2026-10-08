"""Which silhouette set the scene draws for a zone (llm-contract)."""

import logging

from data.world.scenes import (
    INDOORS_FALLBACK_SETTING,
    OUTDOORS_FALLBACK_SETTING,
    SETTING_BY_ZONE,
)
from modules.world.location import Location

logger = logging.getLogger(__name__)

_warned: set[str] = set()


def setting_word(zone: Location) -> str:
    """The zone's setting; a zone missing from the table draws as a street or an apartment."""
    setting = SETTING_BY_ZONE.get(zone.id)
    if setting is not None:
        return setting
    if zone.id not in _warned:
        _warned.add(zone.id)
        logger.warning(f"Zone {zone.id} has no scene setting; drawing the fallback.")
    return INDOORS_FALLBACK_SETTING if zone.indoors else OUTDOORS_FALLBACK_SETTING
