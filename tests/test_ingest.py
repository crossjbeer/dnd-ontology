from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from owlready2 import World

from dndonto.ingest import ingest_lore
from dndonto.ontology import build_ontology


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _build_base_ontology(path: Path) -> Path:
    build_ontology(out_path=path, overwrite=True)
    return path


def test_ingest_lore_happy_path_with_declared_subclasses(tmp_path: Path) -> None:
    ontology_path = _build_base_ontology(tmp_path / "base.owl")
    yaml_path = _write_yaml(
        tmp_path / "lore.yaml",
        {
            "Location": {
                "faerun": {"type": "Continent", "hasName": "Faerun"},
                "waterdeep": {
                    "type": "City",
                    "hasName": "Waterdeep",
                    "partOf": "faerun",
                    "hasPopulation": 100000,
                },
            },
            "Faction": {
                "lords_alliance": {"hasName": "Lords' Alliance"},
            },
            "NPC": {
                "blackstaff": {
                    "hasName": "Vajra Safahr",
                    "hasCR": 8.0,
                    "locatedIn": "waterdeep",
                    "memberOf": "lords_alliance",
                }
            },
            "Artifact": {
                "staff_of_power": {"hasName": "Staff of Power"},
            },
            "Quest": {
                "recover_staff": {
                    "hasName": "Recover the Staff",
                    "questGiver": "blackstaff",
                    "targetsLocation": "waterdeep",
                    "rewardsItem": "staff_of_power",
                }
            },
        },
    )

    out_owl = tmp_path / "with_data.owl"
    out_ttl = tmp_path / "triples.ttl"

    written_owl, written_ttl, count_individuals, count_triples = ingest_lore(
        yaml_path=yaml_path,
        ontology_path=ontology_path,
        output_owl_path=out_owl,
        output_ttl_path=out_ttl,
    )

    assert written_owl == out_owl
    assert written_ttl == out_ttl
    assert out_owl.exists()
    assert out_ttl.exists()
    assert count_individuals == 6
    assert count_triples > 0

    world = World()
    onto = world.get_ontology("http://example.org/dnd/onto").load(fileobj=out_owl.open("rb"))

    waterdeep = onto.search_one(iri="*#waterdeep")
    assert waterdeep is not None
    assert any(cls.name == "City" for cls in waterdeep.is_a)


def test_ingest_rejects_unknown_top_level_section(tmp_path: Path) -> None:
    ontology_path = _build_base_ontology(tmp_path / "base.owl")
    yaml_path = _write_yaml(
        tmp_path / "lore.yaml",
        {
            "Monster": {
                "owlbear": {"hasName": "Owlbear"},
            }
        },
    )

    with pytest.raises(ValueError, match="Unknown top-level section"):
        ingest_lore(yaml_path=yaml_path, ontology_path=ontology_path)


def test_ingest_rejects_incompatible_declared_type(tmp_path: Path) -> None:
    ontology_path = _build_base_ontology(tmp_path / "base.owl")
    yaml_path = _write_yaml(
        tmp_path / "lore.yaml",
        {
            "Location": {
                "not_a_location": {
                    "type": "NPC",
                    "hasName": "Definitely Not A Location",
                }
            }
        },
    )

    with pytest.raises(ValueError, match="not a subclass of section"):
        ingest_lore(yaml_path=yaml_path, ontology_path=ontology_path)


def test_ingest_rejects_unknown_object_reference(tmp_path: Path) -> None:
    ontology_path = _build_base_ontology(tmp_path / "base.owl")
    yaml_path = _write_yaml(
        tmp_path / "lore.yaml",
        {
            "Location": {
                "waterdeep": {"type": "City", "hasName": "Waterdeep"},
            },
            "NPC": {
                "blackstaff": {
                    "hasName": "Vajra Safahr",
                    "hasCR": 8.0,
                    "locatedIn": "missing_place",
                }
            },
        },
    )

    with pytest.raises(ValueError, match="Unknown reference 'missing_place'"):
        ingest_lore(yaml_path=yaml_path, ontology_path=ontology_path)


def test_ingest_rejects_multiple_values_for_functional_data_property(tmp_path: Path) -> None:
    ontology_path = _build_base_ontology(tmp_path / "base.owl")
    yaml_path = _write_yaml(
        tmp_path / "lore.yaml",
        {
            "Location": {
                "waterdeep": {
                    "type": "City",
                    "hasName": ["Waterdeep", "City of Splendors"],
                }
            }
        },
    )

    with pytest.raises(ValueError, match="Functional data property 'hasName'"):
        ingest_lore(yaml_path=yaml_path, ontology_path=ontology_path)
