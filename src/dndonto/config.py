from __future__ import annotations

from pathlib import Path

# Shared project defaults (single source of truth).
DEFAULT_BASE_IRI = "http://example.org/dnd/onto"

DEFAULT_ONTOLOGY_PATH = Path("out/dnd_world.owl")
DEFAULT_LORE_YAML_PATH = Path("data/lore.yaml")

# Ingest outputs
DEFAULT_INGEST_OUTPUT_OWL_PATH = Path("out/dnd_world_with_data.owl")
DEFAULT_INGEST_OUTPUT_TTL_PATH = Path("out/dnd_world_triples.ttl")

# Reasoning outputs
DEFAULT_REASON_INPUT_OWL_PATH = DEFAULT_INGEST_OUTPUT_OWL_PATH
DEFAULT_REASON_OUTPUT_OWL_PATH = Path("out/dnd_world_inferred.owl")
DEFAULT_REASON_OUTPUT_TTL_PATH = Path("out/dnd_world_inferred.ttl")

# For validation during ingest - these are the only top-level sections we expect in the lore.yaml file. 
# Could be represented in a variety of ways, but going for simplicity here. 
KNOWN_TOP_LEVEL_SECTIONS = [
    "Location",
    "Faction",
    "AdventuringParty",
    "NPC",
    "PlayerCharacter",
    "Artifact",
    "Quest",
    "Species",
    "ClassRole",
]