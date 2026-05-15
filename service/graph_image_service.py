import os
import io
import uuid
from urllib.parse import quote

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib import font_manager

from config import PUBLIC_BASE_URL
from service.graph_service import run_cypher


# =========================
# Path / Font Config
# =========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FONT_PATH = os.path.join(
    BASE_DIR,
    "fonts",
    "NotoSansCJKtc-Regular.otf"
)

FONT_NAME = "DejaVu Sans"

try:
    if os.path.exists(FONT_PATH):
        font_manager.fontManager.addfont(FONT_PATH)
        FONT_NAME = font_manager.FontProperties(fname=FONT_PATH).get_name()
        print("[GRAPH IMAGE][FONT_NAME]", FONT_NAME)
    else:
        print("[GRAPH IMAGE][FONT_MISSING]", FONT_PATH)
except Exception as e:
    print("[GRAPH IMAGE][FONT_LOAD_ERROR]", str(e))


# =========================
# URL Builders
# =========================

def get_public_base_url():
    if not PUBLIC_BASE_URL:
        print("[ERROR][PUBLIC_BASE_URL] PUBLIC_BASE_URL is not set")
        return None

    return PUBLIC_BASE_URL.rstrip("/")


def build_node_graph_image_url(target):
    base_url = get_public_base_url()

    if not base_url or not target:
        return None

    return (
        f"{base_url}/graph/image"
        f"?target={quote(str(target))}"
        f"&v={uuid.uuid4().hex}"
    )


def build_node_graph_image_url_by_id(node_id):
    base_url = get_public_base_url()

    if not base_url or not node_id:
        return None

    return (
        f"{base_url}/graph/image"
        f"?node_id={quote(str(node_id))}"
        f"&v={uuid.uuid4().hex}"
    )


def build_relationship_graph_url(source, relation, target):
    base_url = get_public_base_url()

    if not base_url:
        return None

    if not source or not relation or not target:
        print("[GRAPH IMAGE][RELATION URL MISSING]", {
            "source": source,
            "relation": relation,
            "target": target
        })
        return None

    return (
        f"{base_url}/graph/relation-image"
        f"?source={quote(str(source))}"
        f"&relation={quote(str(relation))}"
        f"&target={quote(str(target))}"
        f"&v={uuid.uuid4().hex}"
    )


def build_graph_image_url_from_result(graph_result):
    """
    統一圖片 URL 入口。
    single_node      → /graph/image
    relation_query   → /graph/relation-image
    """

    if not graph_result:
        return None

    first = graph_result[0]

    if not first.get("found"):
        return None

    query_type = first.get("query_type")

    if query_type == "single_node":
        node = first.get("node") or {}

        node_name = (
            node.get("name")
            or first.get("name")
            or first.get("target")
        )

        if not node_name:
            print("[GRAPH IMAGE][SINGLE NODE MISSING]", first)
            return None

        return build_node_graph_image_url(node_name)

    if query_type == "relation_query":
        source = first.get("source")
        target = first.get("target")
        relation = first.get("relation_type")

        if not source or not target or not relation:
            print("[GRAPH IMAGE][RELATION DATA MISSING]", first)
            return None

        return build_relationship_graph_url(
            source=source,
            relation=relation,
            target=target
        )

    return None


# =========================
# Neo4j Data Loading
# =========================

def fetch_node_graph_data_by_name(target):
    q = """
    MATCH (center)
    WHERE coalesce(center.name, center.title) = $target
    OPTIONAL MATCH (center)-[r]-(neighbor)
    RETURN
        elementId(center) AS center_id,
        coalesce(center.name, center.title) AS center_name,
        labels(center) AS center_labels,
        elementId(neighbor) AS neighbor_id,
        coalesce(neighbor.name, neighbor.title) AS neighbor_name,
        labels(neighbor) AS neighbor_labels,
        type(r) AS relation_type,
        startNode(r) = center AS outgoing
    LIMIT 30
    """

    return run_cypher(q, {"target": target})


def fetch_node_graph_data_by_id(node_id):
    q = """
    MATCH (center)
    WHERE elementId(center) = $node_id
    OPTIONAL MATCH (center)-[r]-(neighbor)
    RETURN
        elementId(center) AS center_id,
        coalesce(center.name, center.title) AS center_name,
        labels(center) AS center_labels,
        elementId(neighbor) AS neighbor_id,
        coalesce(neighbor.name, neighbor.title) AS neighbor_name,
        labels(neighbor) AS neighbor_labels,
        type(r) AS relation_type,
        startNode(r) = center AS outgoing
    LIMIT 30
    """

    return run_cypher(q, {"node_id": node_id})


# =========================
# Image Generation Helpers
# =========================

def draw_graph_to_bytes(graph, pos, edge_labels=None, figsize=(9, 6)):
    plt.figure(figsize=figsize)

    nx.draw_networkx_nodes(
        graph,
        pos,
        node_size=3600
    )

    nx.draw_networkx_edges(
        graph,
        pos,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=18,
        width=1.5
    )

    nx.draw_networkx_labels(
        graph,
        pos,
        font_size=10,
        font_family=FONT_NAME
    )

    if edge_labels:
        nx.draw_networkx_edge_labels(
            graph,
            pos,
            edge_labels=edge_labels,
            font_size=9,
            font_family=FONT_NAME
        )

    plt.axis("off")

    image_io = io.BytesIO()

    plt.savefig(
        image_io,
        format="png",
        bbox_inches="tight",
        dpi=150
    )

    plt.close()
    image_io.seek(0)

    return image_io


# =========================
# Single Node Graph
# =========================

def generate_node_graph_image_bytes(target):
    try:
        rows = fetch_node_graph_data_by_name(target)
        return generate_node_graph_from_rows(rows)

    except Exception as e:
        print("[ERROR][NODE_GRAPH_BY_NAME]", str(e))
        return None


def generate_node_graph_image_bytes_by_id(node_id):
    try:
        rows = fetch_node_graph_data_by_id(node_id)
        return generate_node_graph_from_rows(rows)

    except Exception as e:
        print("[ERROR][NODE_GRAPH_BY_ID]", str(e))
        return None


def generate_node_graph_from_rows(rows):
    if not rows:
        return None

    center_name = rows[0].get("center_name")

    if not center_name:
        return None

    graph = nx.DiGraph()
    edge_labels = {}

    graph.add_node(center_name)

    for row in rows:
        neighbor_name = row.get("neighbor_name")
        relation_type = row.get("relation_type")
        outgoing = row.get("outgoing")

        if not neighbor_name or not relation_type:
            continue

        graph.add_node(neighbor_name)

        if outgoing:
            graph.add_edge(center_name, neighbor_name)
            edge_labels[(center_name, neighbor_name)] = relation_type
        else:
            graph.add_edge(neighbor_name, center_name)
            edge_labels[(neighbor_name, center_name)] = relation_type

    if graph.number_of_nodes() == 1:
        pos = {center_name: (0, 0)}
    else:
        pos = nx.spring_layout(
            graph,
            seed=42,
            k=1.5
        )

    return draw_graph_to_bytes(
        graph=graph,
        pos=pos,
        edge_labels=edge_labels,
        figsize=(10, 7)
    )


# =========================
# Two-Node Relationship Graph
# =========================

def generate_relationship_graph_image(source, relation, target):
    try:
        graph = nx.DiGraph()

        graph.add_node(source)
        graph.add_node(target)
        graph.add_edge(source, target)

        pos = {
            source: (-1.5, 0),
            target: (1.5, 0)
        }

        edge_labels = {
            (source, target): relation
        }

        return draw_graph_to_bytes(
            graph=graph,
            pos=pos,
            edge_labels=edge_labels,
            figsize=(8, 3)
        )

    except Exception as e:
        print("[ERROR][RELATION_GRAPH]", str(e))
        return None
