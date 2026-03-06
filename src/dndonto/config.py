from __future__ import annotations

from pathlib import Path

# Shared project defaults (single source of truth).
DEFAULT_BASE_IRI = "http://example.org/dnd/onto"

# Ontology
DEFAULT_ONTOLOGY_INPUT_YAML_PATH = Path("data/lore.yaml")
DEFAULT_ONTOLOGY_OUTPUT_OWL_PATH = Path("out/dnd_world.owl")

# Ingest 
DEFAULT_INGEST_OUTPUT_OWL_PATH = Path("out/dnd_world_with_data.owl")
DEFAULT_INGEST_OUTPUT_TTL_PATH = Path("out/dnd_world_triples.ttl")

# Reasoning 
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