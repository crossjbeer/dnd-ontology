"""Run OWL reasoning over ingested ontology data and persist inferred triples.

Primary demo reasoner:
- Owlready2 + HermiT 

Other reasoners worth considering:
- Pellet (Java OWL DL reasoner, Relies on JDK25)
- ELK (fast EL profile reasoner)
- RDFox (high-performance materialization / Datalog style reasoning)
- GraphDB/Fuseki rule engines or OWL-RL pipelines for triplestore-centric flows
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Tuple, Union

from owlready2 import World, sync_reasoner, OwlReadyInconsistentOntologyError
from rdflib import Graph

from dndonto.config import (
    DEFAULT_INGEST_OUTPUT_OWL_PATH,
    DEFAULT_INGEST_OUTPUT_TTL_PATH,
    DEFAULT_REASON_OUTPUT_OWL_PATH,
    DEFAULT_REASON_OUTPUT_TTL_PATH,
)
from dndonto.ingest import build_rdflib_graph, load_ontology_from_path

def _load_ttl(ttl_path: Path) -> Graph:
    """Read a Turtle graph from disk and return the graph object."""
    graph = Graph()
    graph.parse(str(ttl_path), format="turtle")
    return(graph)

def _get_inconsistent_class_names(world: World) -> List[str]:
    """Return inconsistent class names reported by Owlready2 for this world."""
    names: List[str] = []
    for cls in world.inconsistent_classes():
        name = getattr(cls, "name", str(cls))
        names.append(name)
    return sorted(set(names))

def reason_over_ontology(
    input_owl_path: Union[str, Path] = DEFAULT_INGEST_OUTPUT_OWL_PATH,
    output_owl_path: Union[str, Path] = DEFAULT_REASON_OUTPUT_OWL_PATH,
    output_ttl_path: Union[str, Path] = DEFAULT_REASON_OUTPUT_TTL_PATH,
    asserted_ttl_path: Optional[Union[str, Path]] = DEFAULT_INGEST_OUTPUT_TTL_PATH,
    fail_on_inconsistency: bool = True,
) -> Tuple[Path, Path, int, int]:
    """Run HermiT reasoning and save inferred ontology artifacts.

    Returns:
    - inferred OWL output path
    - inferred TTL output path
    - triples before reasoning
    - triples after reasoning
    """
    input_owl_path = Path(input_owl_path)
    output_owl_path = Path(output_owl_path)
    output_ttl_path = Path(output_ttl_path)
    asserted_ttl = Path(asserted_ttl_path) if asserted_ttl_path is not None else None

    if not input_owl_path.exists():
        raise FileNotFoundError(
            f"Input OWL not found: {input_owl_path}. "
            "Run ontology + ingest first, then retry."
        )

    output_owl_path.parent.mkdir(parents=True, exist_ok=True)
    output_ttl_path.parent.mkdir(parents=True, exist_ok=True)

    world = World()
    onto = load_ontology_from_path(world, input_owl_path)

    if asserted_ttl is not None and asserted_ttl.exists():
        triples_before = len(_load_ttl(asserted_ttl))
    else:
        raise FileNotFoundError(
            f"Asserted TTL not found for baseline triple count: {asserted_ttl}. "
            "Ensure ingest stage completed successfully and produced the expected TTL output."
        )

    try:
        # Important: pass [onto] so the reasoner runs on the loaded world, not default_world.
        sync_reasoner([onto], infer_property_values=True)
    except OwlReadyInconsistentOntologyError as exc:
        inconsistent_classes = _get_inconsistent_class_names(world)
        message = [
            "Ontology is inconsistent according to HermiT.",
            "This often indicates disjointness/domain-range conflicts in asserted facts.",
        ]
        if inconsistent_classes:
            message.append(f"Inconsistent classes: {', '.join(inconsistent_classes)}")

        if fail_on_inconsistency:
            raise RuntimeError("\n".join(message)) from exc

        print("WARNING: " + " ".join(message))

    inconsistent_classes = _get_inconsistent_class_names(world)
    if inconsistent_classes:
        print(f"Consistency check: INCONSISTENT ({', '.join(inconsistent_classes)})")
        if fail_on_inconsistency:
            raise RuntimeError("Consistency check failed after reasoning.")
    else:
        print("Consistency check: CONSISTENT")

    # Save inferred ontology and complete triple graph for downstream query endpoints.
    onto.save(file=str(output_owl_path), format="rdfxml")
    inferred_graph = build_rdflib_graph(world)
    inferred_graph.serialize(destination=str(output_ttl_path), format="turtle")

    triples_after = len(inferred_graph)
    return output_owl_path, output_ttl_path, triples_before, triples_after



def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Owlready2 HermiT reasoning and save inferred OWL/Turtle outputs."
    )
    parser.add_argument(
        "--input-owl",
        type=Path,
        default=DEFAULT_INGEST_OUTPUT_OWL_PATH,
        help="Path to ingested OWL file (asserted graph)",
    )
    parser.add_argument(
        "--out-owl",
        type=Path,
        default=DEFAULT_REASON_OUTPUT_OWL_PATH,
        help="Output path for inferred OWL",
    )
    parser.add_argument(
        "--out-ttl",
        type=Path,
        default=DEFAULT_REASON_OUTPUT_TTL_PATH,
        help="Output path for inferred Turtle graph",
    )
    parser.add_argument(
        "--asserted-ttl",
        type=Path,
        default=DEFAULT_INGEST_OUTPUT_TTL_PATH,
        help=(
            "Asserted Turtle from ingest for baseline triple count; "
        ),
    )
    parser.add_argument(
        "--allow-inconsistent",
        action="store_true",
        help="Continue and write outputs even when ontology is inconsistent",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = make_parser()
    args = parser.parse_args(argv)

    out_owl, out_ttl, triples_before, triples_after = reason_over_ontology(
        input_owl_path=args.input_owl,
        output_owl_path=args.out_owl,
        output_ttl_path=args.out_ttl,
        asserted_ttl_path=args.asserted_ttl,
        fail_on_inconsistency=not args.allow_inconsistent,
    )

    print("Reasoning complete")
    print("Primary reasoner: Owlready2 HermiT")
    print(
        "Other common options: Pellet, ELK, RDFox, GraphDB/Fuseki rule engines, OWL-RL pipelines"
    )
    print(f"Triples before reasoning: {triples_before}")
    print(f"Triples after reasoning: {triples_after}")
    print(f"Inferred OWL: {out_owl}")
    print(f"Inferred Turtle: {out_ttl}")


if __name__ == "__main__":
    main()

