"""Run business-oriented SPARQL queries against inferred ontology triples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from rdflib import Graph

from dndonto.config import DEFAULT_REASON_OUTPUT_TTL_PATH, DEFAULT_BASE_IRI


def _namespace_iri(base_iri: str) -> str:
    """Return a namespace IRI suitable for PREFIX declarations."""
    if base_iri.endswith(("#")):
        return base_iri
    if(base_iri.endswith("/")):
        # Replace with # for consistency
        return base_iri[:-1] + "#"
    return f"{base_iri}#"

BASE_IRI = _namespace_iri(DEFAULT_BASE_IRI)

def _build_queries() -> Dict[str, str]:
    return {
        "entities_in_stonegate": f"""
PREFIX dnd: <{BASE_IRI}>
SELECT ?entity ?name WHERE {{
  ?entity dnd:locatedIn/(dnd:partOf)* dnd:stonegate_province .
  OPTIONAL {{ ?entity dnd:hasName ?name . }}
}}
ORDER BY ?name ?entity
""",
        "contains_relations": f"""
PREFIX dnd: <{BASE_IRI}>
SELECT ?container ?contained WHERE {{
  ?container dnd:contains ?contained .
}}
ORDER BY ?container ?contained
""",
        "quest_board": f"""
PREFIX dnd: <{BASE_IRI}>
SELECT ?quest ?questName ?giver ?target ?required ?reward WHERE {{
  ?quest a dnd:Quest .
  OPTIONAL {{ ?quest dnd:hasName ?questName . }}
  OPTIONAL {{ ?quest dnd:questGiver ?giver . }}
  OPTIONAL {{ ?quest dnd:targetsLocation ?target . }}
  OPTIONAL {{ ?quest dnd:requiresItem ?required . }}
  OPTIONAL {{ ?quest dnd:rewardsItem ?reward . }}
}}
ORDER BY ?questName ?quest
""",
        "faction_relationships": f"""
PREFIX dnd: <{BASE_IRI}>
SELECT ?left ?relation ?right WHERE {{
  {{ ?left dnd:allyOf ?right . BIND("allyOf" AS ?relation) }}
  UNION
  {{ ?left dnd:enemyOf ?right . BIND("enemyOf" AS ?relation) }}
}}
ORDER BY ?relation ?left ?right
""",
        "potential_type_conflicts": f"""
PREFIX dnd: <{BASE_IRI}>
SELECT ?entity WHERE {{
  ?entity a dnd:Character .
  ?entity a dnd:Faction .
}}
ORDER BY ?entity
""",
    }

def _ordered_query_names(queries: Dict[str, str]) -> List[str]:
    return list(queries.keys())

def _resolve_query_tokens(tokens: List[str], queries: Dict[str, str]) -> List[str]:
    ordered = _ordered_query_names(queries)
    resolved: List[str] = []

    for token in tokens:
        name: Optional[str] = None
        if token.isdigit():
            index = int(token)
            if index < 1 or index > len(ordered):
                raise ValueError(
                    f"Query index out of range: {token}. Valid range is 1-{len(ordered)}"
                )
            name = ordered[index - 1]
        elif token in queries:
            name = token
        else:
            raise ValueError(
                f"Unknown query selector '{token}'. Use a query name or an index from --list."
            )

        if name not in resolved:
            resolved.append(name)

    return resolved

def _uri_to_local(value: str) -> str:
    return value.split("#", 1)[1]

def _format_cell(value) -> str:
    text = str(value)
    if text.startswith(BASE_IRI):
        return _uri_to_local(text)
    return text

def _load_graph_from_ttl(ttl_path: Path) -> Graph:
    graph = Graph()
    graph.parse(str(ttl_path), format="turtle")
    return graph

def run_query(graph: Graph, query_name: str, query_text: str) -> Tuple[List[str], List[List[str]]]:
    result = graph.query(query_text)
    columns = [str(col) for col in result.vars]
    rows: List[List[str]] = []

    for row in result:
        rows.append([_format_cell(cell) for cell in row])

    return columns, rows

def _print_table(query_name: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    print(f"\n=== {query_name} ===")
    if not rows:
        print("No rows")
        return

    widths = [len(col) for col in columns]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    header = " | ".join(col.ljust(widths[idx]) for idx, col in enumerate(columns))
    divider = "-+-".join("-" * width for width in widths)
    print(header)
    print(divider)
    for row in rows:
        print(" | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))

def _print_json(query_name: str, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    payload = {
        "query": query_name,
        "columns": list(columns),
        "rows": [dict(zip(columns, row)) for row in rows],
    }
    print(json.dumps(payload, indent=2))


def execute_queries(
    ttl_path: Union[str, Path] = DEFAULT_REASON_OUTPUT_TTL_PATH,
    selected_queries: Optional[List[str]] = None,
    custom_query_text: Optional[str] = None,
    custom_query_name: str = "custom_query",
    output_format: str = "table",
) -> None:
    ttl_path = Path(ttl_path)
    if not ttl_path.exists():
        raise FileNotFoundError(f"Input Turtle graph not found: {ttl_path}")

    queries = _build_queries()
    names = selected_queries or []
    if not names and custom_query_text is None:
        names = _ordered_query_names(queries)

    if names:
        names = _resolve_query_tokens(names, queries)

    graph = _load_graph_from_ttl(ttl_path)

    for name in names:
        columns, rows = run_query(graph, name, queries[name])
        if output_format == "json":
            _print_json(name, columns, rows)
        else:
            _print_table(name, columns, rows)

    if custom_query_text is not None:
        columns, rows = run_query(graph, custom_query_name, custom_query_text)
        if output_format == "json":
            _print_json(custom_query_name, columns, rows)
        else:
            _print_table(custom_query_name, columns, rows)


def make_parser() -> argparse.ArgumentParser:
    queries = _build_queries()
    parser = argparse.ArgumentParser(
        description="Run predefined SPARQL business queries on inferred ontology triples."
    )
    parser.add_argument(
        "--ttl",
        type=Path,
        default=DEFAULT_REASON_OUTPUT_TTL_PATH,
        help="Path to Turtle graph for query execution (default: inferred output)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available query names and exit",
    )
    parser.add_argument(
        "--query",
        action="append",
        help=(
            "Query selector to run (repeatable). "
            "Accepts query name or 1-based index from --list."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format",
    )
    parser.add_argument(
        "--query-file",
        type=Path,
        default=None,
        help="Path to a .rq/.sparql file containing a custom SPARQL query",
    )
    parser.add_argument(
        "--query-text",
        type=str,
        default=None,
        help="Custom SPARQL query text (useful for quick ad-hoc queries)",
    )
    parser.add_argument(
        "--query-name",
        type=str,
        default="custom_query",
        help="Display name for the custom query result",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = make_parser()
    args = parser.parse_args(argv)

    queries = _build_queries()
    if args.list:
        print("Available queries:")
        for index, name in enumerate(_ordered_query_names(queries), start=1):
            print(f"{index}. {name}")
        return

    if args.query_file and args.query_text:
        raise ValueError("Provide only one of --query-file or --query-text")

    custom_query_text: Optional[str] = None
    if args.query_file is not None:
        if not args.query_file.exists():
            raise FileNotFoundError(f"Custom query file not found: {args.query_file}")
        custom_query_text = args.query_file.read_text(encoding="utf-8")
    elif args.query_text:
        custom_query_text = args.query_text

    execute_queries(
        ttl_path=args.ttl,
        selected_queries=args.query,
        custom_query_text=custom_query_text,
        custom_query_name=args.query_name,
        output_format=args.format,
    )


if __name__ == "__main__":
    main()
