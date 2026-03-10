"""Generate Plotly visualizations from asserted and inferred RDF graphs."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from rdflib import Graph, URIRef

from dndonto.config import (
    DEFAULT_BASE_IRI,
    DEFAULT_INGEST_OUTPUT_TTL_PATH,
    DEFAULT_REASON_OUTPUT_TTL_PATH,
)


def _namespace_iri(base_iri: str) -> str:
    if base_iri.endswith("#"):
        return base_iri
    if base_iri.endswith("/"):
        return base_iri[:-1] + "#"
    return f"{base_iri}#"


BASE_IRI = _namespace_iri(DEFAULT_BASE_IRI)
RDF_TYPE = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
RDF_FIRST = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#first")
RDF_REST = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#rest")
OWL_MEMBERS = URIRef("http://www.w3.org/2002/07/owl#members")

NOISY_EXTERNAL_PREDICATES = {
    str(RDF_FIRST),
    str(RDF_REST),
    str(OWL_MEMBERS),
}


LOCATION_CLASS_NAMES = {
    "Location",
    "World",
    "Continent",
    "Region",
    "City",
    "Dungeon",
}


FACTION_CLASS_NAMES = {
    "Faction",
    "AdventuringParty",
}


QUEST_RELATION_STYLES: Mapping[str, Tuple[str, str]] = {
    "questGiver": ("#0a6d92", "questGiver"),
    "targetsLocation": ("#2a9d8f", "targetsLocation"),
    "requiresItem": ("#e76f51", "requiresItem"),
    "rewardsItem": ("#f4a261", "rewardsItem"),
}


FACTION_RELATION_STYLES: Mapping[str, Tuple[str, str]] = {
    "allyOf": ("#2a9d8f", "allyOf"),
    "enemyOf": ("#c1121f", "enemyOf"),
    "rules": ("#1d3557", "rules"),
    "memberOf": ("#6d597a", "memberOf"),
}


NODE_COLORS: Mapping[str, str] = {
    "Quest": "#f4a261",
    "Faction": "#457b9d",
    "AdventuringParty": "#457b9d",
    "Character": "#6d597a",
    "NPC": "#6d597a",
    "PlayerCharacter": "#6d597a",
    "Location": "#2a9d8f",
    "World": "#2a9d8f",
    "Continent": "#2a9d8f",
    "Region": "#2a9d8f",
    "City": "#2a9d8f",
    "Dungeon": "#2a9d8f",
    "Item": "#e76f51",
    "Artifact": "#e76f51",
    "default": "#6c757d",
}


def _load_viz_dependencies() -> Tuple[Any, Any]:
    try:
        import networkx as nx_module
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: networkx. Install with `python -m pip install networkx`."
        ) from exc

    try:
        import plotly.graph_objects as go_module
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: plotly. Install with `python -m pip install plotly`."
        ) from exc

    return nx_module, go_module


def _is_local_uri(value) -> bool:
    return isinstance(value, URIRef) and str(value).startswith(BASE_IRI)


def _uri_to_local(uri: URIRef) -> str:
    text = str(uri)
    if "#" in text:
        return text.rsplit("#", 1)[1]
    return text


def _node_label(graph: Graph, node: URIRef) -> str:
    has_name = URIRef(BASE_IRI + "hasName")
    names = list(graph.objects(node, has_name))
    if names:
        return str(names[0])
    return _uri_to_local(node)


def _local_type_name(graph: Graph, node: URIRef) -> str:
    for obj in graph.objects(node, RDF_TYPE):
        if _is_local_uri(obj):
            return _uri_to_local(obj)
    return "Unknown"


def _local_predicate_name(predicate: URIRef) -> Optional[str]:
    if not _is_local_uri(predicate):
        return None
    return _uri_to_local(predicate)


def _load_graph(path: Path) -> Graph:
    graph = Graph()
    graph.parse(str(path), format="turtle")
    return graph


def _iter_local_entities(graph: Graph) -> Iterable[URIRef]:
    for subject in graph.subjects(predicate=RDF_TYPE, object=None):
        if _is_local_uri(subject):
            yield subject


def _location_nodes(graph: Graph) -> Set[URIRef]:
    nodes: Set[URIRef] = set()
    for node in _iter_local_entities(graph):
        if _local_type_name(graph, node) in LOCATION_CLASS_NAMES:
            nodes.add(node)
    return nodes


def _faction_nodes(graph: Graph) -> Set[URIRef]:
    nodes: Set[URIRef] = set()
    for node in _iter_local_entities(graph):
        if _local_type_name(graph, node) in FACTION_CLASS_NAMES:
            nodes.add(node)
    return nodes


def _tree_depths(children_by_parent: Mapping[str, Sequence[str]], roots: Sequence[str]) -> Dict[str, int]:
    depths: Dict[str, int] = {}
    queue: List[Tuple[str, int]] = [(root, 0) for root in roots]
    while queue:
        node, depth = queue.pop(0)
        if node in depths and depth >= depths[node]:
            continue
        depths[node] = depth
        for child in children_by_parent.get(node, []):
            queue.append((child, depth + 1))
    return depths


def _build_location_tree_figure(graph: Graph) -> Any:
    _, go = _load_viz_dependencies()
    part_of = URIRef(BASE_IRI + "partOf")
    located_in = URIRef(BASE_IRI + "locatedIn")
    location_nodes = _location_nodes(graph)

    parent_by_child: Dict[str, str] = {}
    children_by_parent: Dict[str, List[str]] = defaultdict(list)

    # Prefer explicit partOf assertions for the hierarchy backbone.
    for child, _, parent in graph.triples((None, part_of, None)):
        if not (_is_local_uri(child) and _is_local_uri(parent)):
            continue
        if child not in location_nodes or parent not in location_nodes:
            continue
        child_local = _uri_to_local(child)
        parent_local = _uri_to_local(parent)
        parent_by_child[child_local] = parent_local
        children_by_parent[parent_local].append(child_local)

    # Some location subtypes (for example Dungeon) may be connected via locatedIn.
    # Use locatedIn as a fallback parent only when partOf is absent.
    for child, _, parent in graph.triples((None, located_in, None)):
        if not (_is_local_uri(child) and _is_local_uri(parent)):
            continue
        if child not in location_nodes or parent not in location_nodes:
            continue

        child_local = _uri_to_local(child)
        if child_local in parent_by_child:
            continue
        parent_local = _uri_to_local(parent)
        parent_by_child[child_local] = parent_local
        children_by_parent[parent_local].append(child_local)

    all_nodes = sorted({_uri_to_local(n) for n in location_nodes})
    roots = [node for node in all_nodes if node not in parent_by_child]
    if not roots:
        roots = ["Location Root"]

    synthetic_root = "Location Root"
    labels: List[str] = []
    ids: List[str] = []
    parents: List[str] = []
    values: List[int] = []
    colors: List[str] = []

    labels.append(synthetic_root)
    ids.append(synthetic_root)
    parents.append("")
    values.append(1)
    colors.append("#264653")

    depths = _tree_depths(children_by_parent, roots)

    for local_id in all_nodes:
        node_ref = URIRef(BASE_IRI + local_id)
        labels.append(_node_label(graph, node_ref))
        ids.append(local_id)
        parent_id = parent_by_child.get(local_id, synthetic_root)
        parents.append(parent_id)

        values.append(1)

        type_name = _local_type_name(graph, node_ref)
        colors.append(NODE_COLORS.get(type_name, NODE_COLORS["default"]))

    figure = go.Figure(
        go.Treemap(
            labels=labels,
            ids=ids,
            parents=parents,
            values=values,
            branchvalues="remainder",
            marker={"colors": colors},
            customdata=[depths.get(node_id, 0) for node_id in ids],
            hovertemplate="<b>%{label}</b><br>Depth: %{customdata}<br>Size: %{value}<extra></extra>",
            textinfo="label+value",
        )
    )
    figure.update_layout(
        title="Location Containment Tree",
        template="plotly_white",
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return figure


def _build_edge_trace(
    go: Any,
    positions: Mapping[str, Tuple[float, float]],
    edges: Sequence[Tuple[str, str]],
    color: str,
    name: str,
) -> Any:
    x_values: List[float] = []
    y_values: List[float] = []
    for left, right in edges:
        x_values.extend([positions[left][0], positions[right][0], None])
        y_values.extend([positions[left][1], positions[right][1], None])

    return go.Scatter(
        x=x_values,
        y=y_values,
        mode="lines",
        line={"width": 2, "color": color},
        hoverinfo="none",
        name=name,
    )


def _build_node_trace(
    go: Any,
    graph: Graph,
    positions: Mapping[str, Tuple[float, float]],
    local_ids: Sequence[str],
) -> Any:
    x_values: List[float] = []
    y_values: List[float] = []
    labels: List[str] = []
    type_names: List[str] = []
    colors: List[str] = []

    for local_id in local_ids:
        node_ref = URIRef(BASE_IRI + local_id)
        x_values.append(positions[local_id][0])
        y_values.append(positions[local_id][1])
        labels.append(_node_label(graph, node_ref))
        type_name = _local_type_name(graph, node_ref)
        type_names.append(type_name)
        colors.append(NODE_COLORS.get(type_name, NODE_COLORS["default"]))

    return go.Scatter(
        x=x_values,
        y=y_values,
        mode="markers+text",
        text=labels,
        textposition="top center",
        hovertemplate="<b>%{text}</b><br>Type: %{customdata}<extra></extra>",
        customdata=type_names,
        marker={"size": 18, "color": colors, "line": {"width": 1, "color": "#1f2933"}},
        name="Nodes",
    )


def _build_network_figure(
    graph: Graph,
    triples: Sequence[Tuple[str, str, str]],
    relation_styles: Mapping[str, Tuple[str, str]],
    title: str,
    layout_k: float = 0.9,
) -> Any:
    nx, go = _load_viz_dependencies()
    network = nx.Graph()
    edges_by_relation: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    for source, relation, target in triples:
        network.add_node(source)
        network.add_node(target)
        network.add_edge(source, target, relation=relation)
        edges_by_relation[relation].append((source, target))

    if network.number_of_nodes() == 0:
        figure = go.Figure()
        figure.update_layout(title=f"{title} (No Data)", template="plotly_white")
        return figure

    positions = nx.spring_layout(network, seed=42, k=layout_k)
    traces: List[Any] = []

    for relation_name, edge_list in edges_by_relation.items():
        color, legend_name = relation_styles[relation_name]
        traces.append(_build_edge_trace(go, positions, edge_list, color, legend_name))

    traces.append(_build_node_trace(go, graph, positions, list(network.nodes())))

    figure = go.Figure(data=traces)
    figure.update_layout(
        title=title,
        template="plotly_white",
        showlegend=True,
        xaxis={"visible": False},
        yaxis={"visible": False},
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return figure


def _build_quest_graph_figure(graph: Graph) -> Any:
    quest_type = URIRef(BASE_IRI + "Quest")

    triples: List[Tuple[str, str, str]] = []
    for quest in graph.subjects(RDF_TYPE, quest_type):
        if not _is_local_uri(quest):
            continue

        source = _uri_to_local(quest)
        for relation_name in QUEST_RELATION_STYLES:
            predicate = URIRef(BASE_IRI + relation_name)
            for target in graph.objects(quest, predicate):
                if _is_local_uri(target):
                    triples.append((source, relation_name, _uri_to_local(target)))

    return _build_network_figure(
        graph,
        triples,
        QUEST_RELATION_STYLES,
        title="Quest Dependency Graph",
        layout_k=0.4,
    )


def _build_faction_graph_figure(graph: Graph) -> Any:
    tracked_predicates = {name: URIRef(BASE_IRI + name) for name in FACTION_RELATION_STYLES}
    faction_nodes = _faction_nodes(graph)

    triples: List[Tuple[str, str, str]] = []
    for subject, predicate, obj in graph.triples((None, None, None)):
        relation_name = _local_predicate_name(predicate)
        if relation_name not in tracked_predicates:
            continue
        if not (_is_local_uri(subject) and _is_local_uri(obj)):
            continue

        if relation_name in {"allyOf", "enemyOf"}:
            if subject not in faction_nodes or obj not in faction_nodes:
                continue
        triples.append((_uri_to_local(subject), relation_name, _uri_to_local(obj)))

    return _build_network_figure(
        graph,
        triples,
        FACTION_RELATION_STYLES,
        title="Faction Relationship Network",
    )


def _build_reasoning_delta_figure(
    asserted_graph: Graph,
    inferred_graph: Graph,
    include_external_predicates: bool = False,
) -> Any:
    _, go = _load_viz_dependencies()
    asserted_triples = set(asserted_graph)
    inferred_triples = set(inferred_graph)
    added_triples = inferred_triples - asserted_triples

    predicate_counts: Counter[str] = Counter()
    hidden_external_count = 0
    for _, predicate, _ in added_triples:
        if _is_local_uri(predicate):
            predicate_counts[_uri_to_local(predicate)] += 1
        else:
            predicate_text = str(predicate)
            if not include_external_predicates:
                hidden_external_count += 1
                continue
            if predicate_text in NOISY_EXTERNAL_PREDICATES:
                hidden_external_count += 1
                continue
            predicate_counts[predicate_text] += 1

    if predicate_counts:
        top_items = predicate_counts.most_common(12)
        labels = [item[0] for item in top_items]
        values = [item[1] for item in top_items]
    else:
        labels = ["No inferred delta"]
        values = [0]

    summary_labels = ["Asserted triples", "Inferred triples", "New inferred triples"]
    summary_values = [len(asserted_triples), len(inferred_triples), len(added_triples)]

    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=summary_labels,
            y=summary_values,
            marker_color=["#457b9d", "#2a9d8f", "#e76f51"],
            name="Summary",
        )
    )
    figure.add_trace(
        go.Bar(
            x=labels,
            y=values,
            marker_color="#1d3557",
            name="Top New Predicates",
            xaxis="x2",
            yaxis="y2",
        )
    )

    title = "Reasoning Delta (Asserted vs Inferred)"
    if hidden_external_count:
        title += f" - Hidden external predicate triples: {hidden_external_count}"

    figure.update_layout(
        title=title,
        template="plotly_white",
        barmode="group",
        grid={"rows": 1, "columns": 2, "pattern": "independent"},
        xaxis={"domain": [0.0, 0.45], "anchor": "y"},
        yaxis={"domain": [0.0, 1.0], "anchor": "x", "title": "Triple Count"},
        xaxis2={"domain": [0.55, 1.0], "anchor": "y2", "title": "Predicate"},
        yaxis2={"domain": [0.0, 1.0], "anchor": "x2", "title": "New Triples"},
        margin={"l": 20, "r": 20, "t": 60, "b": 60},
        legend={"orientation": "h", "y": 1.08},
    )
    return figure


def _write_html(figure: Any, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(destination), include_plotlyjs="cdn", full_html=True)


def build_visualizations(
    inferred_ttl_path: Path = DEFAULT_REASON_OUTPUT_TTL_PATH,
    asserted_ttl_path: Path = DEFAULT_INGEST_OUTPUT_TTL_PATH,
    out_dir: Path = Path("out/viz"),
    include_external_delta_predicates: bool = False,
) -> Dict[str, Path]:
    inferred_ttl_path = Path(inferred_ttl_path)
    asserted_ttl_path = Path(asserted_ttl_path)
    out_dir = Path(out_dir)

    if not inferred_ttl_path.exists():
        raise FileNotFoundError(
            f"Inferred Turtle graph not found: {inferred_ttl_path}. "
            "Run reasoning first (e.g. dndonto-pipeline)."
        )
    if not asserted_ttl_path.exists():
        raise FileNotFoundError(
            f"Asserted Turtle graph not found: {asserted_ttl_path}. "
            "Run ingest first (e.g. dndonto-pipeline)."
        )

    inferred_graph = _load_graph(inferred_ttl_path)
    asserted_graph = _load_graph(asserted_ttl_path)

    outputs: Dict[str, Path] = {
        "location_tree": out_dir / "location_tree.html",
        "quest_graph": out_dir / "quest_graph.html",
        "faction_graph": out_dir / "faction_graph.html",
        "reasoning_delta": out_dir / "reasoning_delta.html",
    }

    # Use asserted graph for location tree to avoid transitive partOf closure flattening.
    _write_html(_build_location_tree_figure(asserted_graph), outputs["location_tree"])
    _write_html(_build_quest_graph_figure(inferred_graph), outputs["quest_graph"])
    _write_html(_build_faction_graph_figure(inferred_graph), outputs["faction_graph"])
    _write_html(
        _build_reasoning_delta_figure(
            asserted_graph,
            inferred_graph,
            include_external_predicates=include_external_delta_predicates,
        ),
        outputs["reasoning_delta"],
    )

    return outputs


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Plotly visualizations from asserted and inferred Turtle graphs."
    )
    parser.add_argument(
        "--inferred-ttl",
        type=Path,
        default=DEFAULT_REASON_OUTPUT_TTL_PATH,
        help="Path to inferred Turtle graph",
    )
    parser.add_argument(
        "--asserted-ttl",
        type=Path,
        default=DEFAULT_INGEST_OUTPUT_TTL_PATH,
        help="Path to asserted Turtle graph",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out/viz"),
        help="Output directory for generated HTML files",
    )
    parser.add_argument(
        "--delta-include-external",
        action="store_true",
        help="Include non-domain external predicates in reasoning delta (RDF/OWL internals)",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = make_parser()
    args = parser.parse_args(argv)

    outputs = build_visualizations(
        inferred_ttl_path=args.inferred_ttl,
        asserted_ttl_path=args.asserted_ttl,
        out_dir=args.out_dir,
        include_external_delta_predicates=args.delta_include_external,
    )

    print("Visualization build complete")
    for key, path in outputs.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()
