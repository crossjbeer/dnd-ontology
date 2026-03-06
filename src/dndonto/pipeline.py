from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from dndonto.check_env import configure_java
from dndonto.config import (
    DEFAULT_INGEST_OUTPUT_OWL_PATH,
    DEFAULT_INGEST_OUTPUT_TTL_PATH,
    DEFAULT_ONTOLOGY_INPUT_YAML_PATH,
    DEFAULT_ONTOLOGY_OUTPUT_OWL_PATH,
    DEFAULT_REASON_OUTPUT_OWL_PATH,
    DEFAULT_REASON_OUTPUT_TTL_PATH,
)
from dndonto.ingest import ingest_lore
from dndonto.ontology import BASE_IRI, build_ontology
from dndonto.query import execute_queries, resolve_custom_query_text
from dndonto.reason import reason_over_ontology


def _stage_banner(stage_number: int, total_stages: int, title: str) -> None:
    print(f"\n[{stage_number}/{total_stages}] {title}")


def _maybe_pause(enabled: bool) -> None:
    if enabled:
        input("Press Enter to continue to the next stage...")


def run_pipeline(
    ontology_path: Path = DEFAULT_ONTOLOGY_OUTPUT_OWL_PATH,
    yaml_path: Path = DEFAULT_ONTOLOGY_INPUT_YAML_PATH,
    ingest_owl_path: Path = DEFAULT_INGEST_OUTPUT_OWL_PATH,
    ingest_ttl_path: Path = DEFAULT_INGEST_OUTPUT_TTL_PATH,
    reasoned_owl_path: Path = DEFAULT_REASON_OUTPUT_OWL_PATH,
    reasoned_ttl_path: Path = DEFAULT_REASON_OUTPUT_TTL_PATH,
    overwrite_ontology: bool = False,
    allow_inconsistent: bool = False,
    skip_query: bool = False,
    selected_queries: Optional[List[str]] = None,
    query_file: Optional[Path] = None,
    query_text: Optional[str] = None,
    query_name: str = "custom_query",
    output_format: str = "table",
    pause_between_stages: bool = False,
    check_java: bool = True,
) -> None:
    total_stages = 4

    if check_java:
        _stage_banner(0, total_stages, "Environment Check")
        version_text = configure_java().strip()
        first_line = version_text.splitlines()[0] if version_text else "Unknown Java version"
        print(f"Java: {first_line}")

    _stage_banner(1, total_stages, "Build Ontology (TBox)")
    onto = build_ontology(out_path=ontology_path, base_iri=BASE_IRI, overwrite=overwrite_ontology)
    print(f"Saved ontology schema: {ontology_path}")
    print(f"Classes: {len(list(onto.classes()))}")
    print(f"Object properties: {len(list(onto.object_properties()))}")
    print(f"Data properties: {len(list(onto.data_properties()))}")
    _maybe_pause(pause_between_stages)

    _stage_banner(2, total_stages, "Ingest Lore (ABox + Asserted Triples)")
    out_owl, out_ttl, count_individuals, count_triples = ingest_lore(
        yaml_path=yaml_path,
        ontology_path=ontology_path,
        output_owl_path=ingest_owl_path,
        output_ttl_path=ingest_ttl_path,
    )
    print(f"Individuals created/updated: {count_individuals}")
    print(f"Asserted triples: {count_triples}")
    print(f"Asserted OWL: {out_owl}")
    print(f"Asserted Turtle: {out_ttl}")
    _maybe_pause(pause_between_stages)

    _stage_banner(3, total_stages, "Run Reasoner (HermiT)")
    inferred_owl, inferred_ttl, triples_before, triples_after = reason_over_ontology(
        input_owl_path=out_owl,
        output_owl_path=reasoned_owl_path,
        output_ttl_path=reasoned_ttl_path,
        asserted_ttl_path=out_ttl,
        fail_on_inconsistency=not allow_inconsistent,
    )
    print(f"Triples before reasoning: {triples_before}")
    print(f"Triples after reasoning: {triples_after}")
    print(f"Inferred OWL: {inferred_owl}")
    print(f"Inferred Turtle: {inferred_ttl}")
    _maybe_pause(pause_between_stages)

    _stage_banner(4, total_stages, "Query Results")
    if skip_query:
        print("Query stage skipped. Use dndonto.query or rerun without --skip-query.")
        return

    custom_query_text = resolve_custom_query_text(query_file, query_text)

    execute_queries(
        ttl_path=inferred_ttl,
        selected_queries=selected_queries,
        custom_query_text=custom_query_text,
        custom_query_name=query_name,
        output_format=output_format,
    )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run full DnD ontology pipeline: build ontology, ingest lore, reason, and query."
        )
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        default=DEFAULT_ONTOLOGY_OUTPUT_OWL_PATH,
        help="Output path for base ontology schema",
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=DEFAULT_ONTOLOGY_INPUT_YAML_PATH,
        help="Path to lore YAML file",
    )
    parser.add_argument(
        "--out-asserted-owl",
        type=Path,
        default=DEFAULT_INGEST_OUTPUT_OWL_PATH,
        help="Output path for asserted OWL (after ingest)",
    )
    parser.add_argument(
        "--out-asserted-ttl",
        type=Path,
        default=DEFAULT_INGEST_OUTPUT_TTL_PATH,
        help="Output path for asserted Turtle graph",
    )
    parser.add_argument(
        "--out-inferred-owl",
        type=Path,
        default=DEFAULT_REASON_OUTPUT_OWL_PATH,
        help="Output path for inferred OWL (after reasoning)",
    )
    parser.add_argument(
        "--out-inferred-ttl",
        type=Path,
        default=DEFAULT_REASON_OUTPUT_TTL_PATH,
        help="Output path for inferred Turtle graph",
    )
    parser.add_argument(
        "--overwrite-ontology",
        action="store_true",
        help="Overwrite ontology file if it already exists",
    )
    parser.add_argument(
        "--allow-inconsistent",
        action="store_true",
        help="Continue and write outputs even when reasoner detects inconsistency",
    )
    parser.add_argument(
        "--skip-query",
        action="store_true",
        help="Skip the final query stage",
    )
    parser.add_argument(
        "--pause-between-stages",
        action="store_true",
        help="Pause after each stage so users can inspect generated files",
    )
    parser.add_argument(
        "--no-check-java",
        action="store_true",
        help="Skip Java availability check before running reasoner",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Query selector(s) for final stage (name or 1-based index)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format for final query stage",
    )
    parser.add_argument(
        "--query-file",
        type=Path,
        default=None,
        help="Path to a custom SPARQL query file for the final stage",
    )
    parser.add_argument(
        "--query-text",
        type=str,
        default=None,
        help="Custom SPARQL query text for the final stage",
    )
    parser.add_argument(
        "--query-name",
        type=str,
        default="custom_query",
        help="Display name for custom query output",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = make_parser()
    args = parser.parse_args(argv)

    run_pipeline(
        ontology_path=args.ontology,
        yaml_path=args.yaml,
        ingest_owl_path=args.out_asserted_owl,
        ingest_ttl_path=args.out_asserted_ttl,
        reasoned_owl_path=args.out_inferred_owl,
        reasoned_ttl_path=args.out_inferred_ttl,
        overwrite_ontology=args.overwrite_ontology,
        allow_inconsistent=args.allow_inconsistent,
        skip_query=args.skip_query,
        selected_queries=args.query,
        query_file=args.query_file,
        query_text=args.query_text,
        query_name=args.query_name,
        output_format=args.format,
        pause_between_stages=args.pause_between_stages,
        check_java=not args.no_check_java,
    )


if __name__ == "__main__":
    main()
