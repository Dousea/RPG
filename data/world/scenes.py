"""The silhouette set the scene draws for each zone (llm-contract)."""

SETTING_BY_ZONE = {
    "zone_home": "apartment",
    "zone_flat_vacant": "apartment",
    "zone_flat_tenant": "apartment",
    "zone_building": "hallway",
    "zone_street": "street",
    "zone_neighborhood": "neighborhood",
    "zone_bodega": "store",
    "zone_pharmacy": "store",
    "zone_hardware": "store",
    "zone_supermarket": "store",
    "zone_clinic": "clinic",
}
OUTDOORS_FALLBACK_SETTING = "street"
INDOORS_FALLBACK_SETTING = "apartment"
