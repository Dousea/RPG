"""The outbreak's stages and the city each one describes (llm-contract)."""

COLLAPSE_FIRST_DAY = 3  # llm-contract: outbreak day
ABANDONED_FIRST_DAY = 14  # llm-contract: outbreak day

STAGE_NORMAL = "normal"
STAGE_PANIC = "panic"
STAGE_COLLAPSE = "collapse"
STAGE_ABANDONED = "abandoned"

# The narrator's line for each stage, beside the outbreak day; none before the outbreak.
STAGE_LINES = {  # llm-contract
    STAGE_PANIC: (
        "The city is in a panic: smoke hangs over it and fires glow at dusk, cars are "
        "left with their doors open, a few windows are broken, litter is starting to "
        "gather, and shelves are thinning."
    ),
    STAGE_COLLAPSE: (
        "The city has collapsed: a thin smoke still rises somewhere, windows are "
        "boarded or broken, cars are wrecked, streetlights are snapped, trash bags and "
        "spilled stock lie about, crosses are sprayed on doors, and there are blood "
        "smears and handprints on the walls."
    ),
    STAGE_ABANDONED: (
        "The city is abandoned and fading: grass grows through the cracks, vines climb "
        "the walls, wrecks have rusted, dust and cobwebs have settled, and the smoke "
        "has long cleared."
    ),
}
