"""
A script to ingest yaml class instances into an OWL ontology and serialize as RDF triples.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import yaml
from rdflib import Graph
from owlready2 import Thing, World
from dndonto.config import (
    DEFAULT_BASE_IRI,
    DEFAULT_INGEST_OUTPUT_OWL_PATH,
    DEFAULT_INGEST_OUTPUT_TTL_PATH,
    DEFAULT_LORE_YAML_PATH,
    DEFAULT_ONTOLOGY_PATH,
    KNOWN_TOP_LEVEL_SECTIONS
)

# ---- config ----
DEFAULT_OUTPUT_OWL_PATH = DEFAULT_INGEST_OUTPUT_OWL_PATH
DEFAULT_OUTPUT_TTL_PATH = DEFAULT_INGEST_OUTPUT_TTL_PATH
DEFAULT_YAML_PATH = DEFAULT_LORE_YAML_PATH



def load_yaml(path: Union[str, Path]) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Top-level YAML document must be a mapping.")
    return data


def get_onto_class(onto, class_name: str):
    cls = getattr(onto, class_name, None)
    if cls is None:
        raise ValueError(f"Class '{class_name}' not found in ontology.")
    return cls


def get_onto_prop(onto, prop_name: str):
    prop = getattr(onto, prop_name, None)
    if prop is None:
        raise ValueError(f"Property '{prop_name}' not found in ontology.")
    return prop


def ensure_individual(onto, cls_name: str, local_id: str) -> Thing:
    """
    Ensure that an individual of the given class and local ID exists in the ontology.

    Parameters:
    - onto: The ontology to search/create in.
    - cls_name: The name of the class (e.g., "City", "NPC") that the individual should belong to.
    - local_id: A unique identifier for the individual (e.g., "waterdeep", "blackstaff").

    Returns:
    - The existing or newly created individual.
    """
    cls = get_onto_class(onto, cls_name)
    ind = onto.search_one(iri=f"*#{local_id}")
    if ind:
        return ind
    return cls(local_id)


def _is_data_property(onto, prop_name: str) -> bool:
    return any(prop.name == prop_name for prop in onto.data_properties())


def _is_functional_property(prop) -> bool:
    return any(base.__name__ == "FunctionalProperty" for base in prop.is_a)


def _as_sequence(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return [value]


def _coerce_data_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(
        f"Unsupported literal type for data property: {type(value).__name__}. "
        "Expected one of: str, int, float, bool."
    )


def _resolve_reference(index: Dict[str, Thing], ref_id: str, *, owner: str, prop_name: str) -> Thing:
    target = index.get(ref_id)
    if target is None:
        raise ValueError(
            f"Unknown reference '{ref_id}' in property '{prop_name}' for individual '{owner}'."
        )
    return target


def _set_functional(individual: Thing, prop_name: str, value: Any) -> None:
    setattr(individual, prop_name, value)


def _append_nonfunctional(individual: Thing, prop_name: str, values: Iterable[Any]) -> None:
    current = getattr(individual, prop_name)
    for value in values:
        if value not in current:
            current.append(value)


def _normalize_section(section_name: str) -> str:
    if section_name not in KNOWN_TOP_LEVEL_SECTIONS:
        raise ValueError(
            f"Unknown top-level section '{section_name}'. "
            f"Allowed sections: {', '.join(KNOWN_TOP_LEVEL_SECTIONS)}"
        )
    return section_name


def create_individuals_from_yaml(onto, lore: Dict[str, Any]) -> Dict[str, Thing]:
    """First pass: create all individuals so cross-references can be resolved in pass two."""
    index: Dict[str, Thing] = {}

    for section_name, section_payload in lore.items():
        cls_name = _normalize_section(section_name)
        if not isinstance(section_payload, dict):
            raise ValueError(f"Section '{section_name}' must map IDs to entity definitions.")

        for local_id in section_payload.keys():
            if local_id in index:
                raise ValueError(
                    f"Duplicate individual id '{local_id}' across sections. IDs must be globally unique."
                )
            index[local_id] = ensure_individual(onto, cls_name, local_id)

    return index


def apply_properties_from_yaml(onto, lore: Dict[str, Any], index: Dict[str, Thing]) -> None:
    """Second pass: set data and object properties after all individuals exist."""
    for section_name, section_payload in lore.items():
        _normalize_section(section_name)
        if not isinstance(section_payload, dict):
            raise ValueError(f"Section '{section_name}' must map IDs to entity definitions.")

        for local_id, attrs in section_payload.items():
            if not isinstance(attrs, dict):
                raise ValueError(
                    f"Entity '{local_id}' in section '{section_name}' must be a mapping of properties."
                )

            subject = index[local_id]

            for prop_name, raw_value in attrs.items():
                prop = get_onto_prop(onto, prop_name)
                values = _as_sequence(raw_value)

                if _is_data_property(onto, prop_name):
                    literals = [_coerce_data_value(value) for value in values]
                    if _is_functional_property(prop):
                        if len(literals) != 1:
                            raise ValueError(
                                f"Functional data property '{prop_name}' on '{local_id}' "
                                "cannot receive multiple values."
                            )
                        _set_functional(subject, prop_name, literals[0])
                    else:
                        _append_nonfunctional(subject, prop_name, literals)
                else:
                    refs: List[Thing] = []
                    for value in values:
                        if not isinstance(value, str):
                            raise ValueError(
                                f"Object property '{prop_name}' on '{local_id}' must reference "
                                "one or more string IDs."
                            )
                        refs.append(
                            _resolve_reference(index, value, owner=local_id, prop_name=prop_name)
                        )

                    if _is_functional_property(prop):
                        if len(refs) != 1:
                            raise ValueError(
                                f"Functional object property '{prop_name}' on '{local_id}' "
                                "cannot receive multiple values."
                            )
                        _set_functional(subject, prop_name, refs[0])
                    else:
                        _append_nonfunctional(subject, prop_name, refs)


def load_ontology_from_path(world: World, ontology_path: Path):
    ontology_path = ontology_path.resolve()
    onto = world.get_ontology(DEFAULT_BASE_IRI)
    with ontology_path.open("rb") as input_file:
        onto.load(fileobj=input_file)
    return onto


def build_rdflib_graph(world: World) -> Graph:
    graph = Graph()
    world_graph = world.as_rdflib_graph()
    for triple in world_graph.triples((None, None, None)):
        graph.add(triple)
    return graph


def ingest_lore(
    yaml_path: Union[str, Path] = DEFAULT_YAML_PATH,
    ontology_path: Union[str, Path] = DEFAULT_ONTOLOGY_PATH,
    output_owl_path: Union[str, Path] = DEFAULT_OUTPUT_OWL_PATH,
    output_ttl_path: Union[str, Path] = DEFAULT_OUTPUT_TTL_PATH,
) -> Tuple[Path, Path, int, int]:
    yaml_path = Path(yaml_path)
    ontology_path = Path(ontology_path)
    output_owl_path = Path(output_owl_path)
    output_ttl_path = Path(output_ttl_path)

    if not yaml_path.exists():
        raise FileNotFoundError(f"Lore YAML not found: {yaml_path}")

    output_owl_path.parent.mkdir(parents=True, exist_ok=True)
    output_ttl_path.parent.mkdir(parents=True, exist_ok=True)

    if not ontology_path.exists():
        raise FileNotFoundError(
            f"Ontology OWL not found: {ontology_path}. "
            "Build ontology first (e.g. run dndonto.ontology) and retry ingestion."
        )

    lore = load_yaml(yaml_path)
    world = World()
    onto = load_ontology_from_path(world, ontology_path)

    with onto:
        index = create_individuals_from_yaml(onto, lore)
        apply_properties_from_yaml(onto, lore, index)

    onto.save(file=str(output_owl_path), format="rdfxml")

    graph = build_rdflib_graph(world)
    graph.serialize(destination=str(output_ttl_path), format="turtle")

    return output_owl_path, output_ttl_path, len(index), len(graph)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest lore YAML into ontology and RDFLib triples.")
    parser.add_argument("--yaml", type=Path, default=DEFAULT_YAML_PATH, help="Path to lore YAML")
    parser.add_argument(
        "--ontology",
        type=Path,
        default=DEFAULT_ONTOLOGY_PATH,
        help="Path to base OWL ontology (required)",
    )
    parser.add_argument(
        "--out-owl",
        type=Path,
        default=DEFAULT_OUTPUT_OWL_PATH,
        help="Output path for OWL file with ingested data",
    )
    parser.add_argument(
        "--out-ttl",
        type=Path,
        default=DEFAULT_OUTPUT_TTL_PATH,
        help="Output path for Turtle triple store",
    )
    return parser 


def main(argv: Optional[List[str]] = None) -> None:
    parser = make_parser()
    args = parser.parse_args(argv)
    
    out_owl, out_ttl, count_individuals, count_triples = ingest_lore(
        yaml_path=args.yaml,
        ontology_path=args.ontology,
        output_owl_path=args.out_owl,
        output_ttl_path=args.out_ttl,
    )

    print("Ingestion complete")
    print(f"Individuals created/updated: {count_individuals}")
    print(f"Triples serialized: {count_triples}")
    print(f"OWL with data: {out_owl}")
    print(f"Turtle triple store: {out_ttl}")


if __name__ == "__main__":
    main()
