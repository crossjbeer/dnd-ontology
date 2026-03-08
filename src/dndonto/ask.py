"""Natural-language Q&A over the knowledge graph using Claude to write and interpret SPARQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dndonto.config import DEFAULT_REASON_OUTPUT_TTL_PATH, DEFAULT_BASE_IRI
from dndonto.query import _load_graph_from_ttl, run_query, _namespace_iri

BASE_IRI = _namespace_iri(DEFAULT_BASE_IRI)
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Read ontology source to use as schema context for the LLM
# ---------------------------------------------------------------------------

_ONTOLOGY_SOURCE = (Path(__file__).parent / "ontology.py").read_text(encoding="utf-8")


def _build_generate_system() -> str:
    return (
        f"You are an expert SPARQL querier for an OWL knowledge graph about a D&D world.\n"
        f"\n"
        f"BASE IRI (namespace): {BASE_IRI}\n"
        f"Always declare: PREFIX dnd: <{BASE_IRI}>\n"
        f"\n"
        f"Below is the Python source that defines the ontology (classes, object properties, "
        f"data properties). Use it to understand the schema and write correct SPARQL queries.\n"
        f"\n"
        f"```python\n{_ONTOLOGY_SOURCE}\n```\n"
        f"\n"
        f"NOTES:\n"
        f"- Individual IRIs look like: dnd:stonegate_province, dnd:lord_nethergloom, etc.\n"
        f"- Use dnd:partOf* or dnd:partOf+ for transitive location queries.\n"
        f"- The reasoner has already run; inferred triples are present.\n"
        f"\n"
        f"Your task: given a natural-language question, return ONLY a single valid SPARQL SELECT "
        f"query and nothing else — no explanation, no markdown fences, no prose."
    )

_INTERPRET_SYSTEM = (
    "You are a helpful D&D game-master assistant bot. "
    "You will receive a natural-language question, the SPARQL query that was run, "
    "and the raw query results as JSON. "
    "Summarise the answer in a clear, concise manner suitable for a heads-up display." 
)


# ---------------------------------------------------------------------------
# Anthropic helpers
# ---------------------------------------------------------------------------

def _get_client(api_key: str):
    try:
        import anthropic  # type: ignore
    except ImportError:
        print(
            "ERROR: The 'anthropic' package is not installed.\n"
            "Install it with:  pip install dnd-ontology[llm]",
            file=sys.stderr,
        )
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def _chat(client, model: str, system: str, user: str) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[
            {"role": "user", "content": user},
        ],
        temperature=0,
    )

    if response.content and response.content[0].type == "text":
        return response.content[0].text.strip()

    raise RuntimeError("Anthropic response did not contain text output.")


# ---------------------------------------------------------------------------
# Core ask logic
# ---------------------------------------------------------------------------

def ask(
    question: str,
    ttl_path: Path,
    api_key: str,
    model: str = DEFAULT_ANTHROPIC_MODEL,
) -> None:
    """Run the full ask pipeline: generate SPARQL → execute → interpret."""
    if not ttl_path.exists():
        print(f"ERROR: Turtle graph not found: {ttl_path}", file=sys.stderr)
        sys.exit(1)

    client = _get_client(api_key)

    # --- Step 1: generate SPARQL ---
    print("Generating SPARQL query...")
    try:
        sparql = _chat(client, model, _build_generate_system(), question)
    except Exception as exc:
        print(f"ERROR: Query generation failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"\n--- Generated SPARQL ---\n{sparql}\n------------------------\n")

    # --- Step 2: execute ---
    print("Loading graph and running query...")
    graph = _load_graph_from_ttl(ttl_path)
    try:
        columns, rows = run_query(graph, "llm_generated", sparql)
    except Exception as exc:
        print(f"ERROR: SPARQL execution failed: {exc}", file=sys.stderr)
        sys.exit(1)

    results_payload = {
        "columns": columns,
        "rows": [dict(zip(columns, row)) for row in rows],
        "row_count": len(rows),
    }
    print(f"Query returned {len(rows)} row(s).\n")

    # --- Step 3: interpret ---
    print("Interpreting results...")
    interpret_user = (
        f"Question: {question}\n\n"
        f"SPARQL used:\n{sparql}\n\n"
        f"Results (JSON):\n{json.dumps(results_payload, indent=2)}"
    )
    try:
        answer = _chat(client, model, _INTERPRET_SYSTEM, interpret_user)
    except Exception as exc:
        print(f"ERROR: Result interpretation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Answer ===\n{answer}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dndonto-ask",
        description="Ask a natural-language question about your D&D world.",
    )
    parser.add_argument(
        "question",
        help="Natural-language question to answer (e.g. 'Who are the allies of the Iron Hand?')",
    )
    parser.add_argument(
        "--ttl",
        type=Path,
        default=DEFAULT_REASON_OUTPUT_TTL_PATH,
        metavar="PATH",
        help=f"Inferred Turtle graph (default: {DEFAULT_REASON_OUTPUT_TTL_PATH})",
    )
    parser.add_argument(
        "--anthropic-key",
        default=os.environ.get("ANTHROPIC_API_KEY"),
        metavar="KEY",
        help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_ANTHROPIC_MODEL,
        metavar="MODEL",
        help=f"Anthropic model to use (default: {DEFAULT_ANTHROPIC_MODEL})",
    )
    return parser


def main() -> None:
    parser = make_parser()
    args = parser.parse_args()

    if not args.anthropic_key:
        parser.error(
            "An Anthropic API key is required. Pass --anthropic-key or set ANTHROPIC_API_KEY."
        )

    ask(
        question=args.question,
        ttl_path=args.ttl,
        api_key=args.anthropic_key,
        model=args.model,
    )


if __name__ == "__main__":
    main()
