import os
import uuid
import math
import matplotlib.pyplot as plt
import networkx as nx

from graph_service import run_cypher
from config import PUBLIC_BASE_URL

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)


def shorten_text(text, max_len=18):
    if not text:
        return ""
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def query_node_graph_rows(target, limit=50):
    safe_target = target.strip()

    q = """
    MATCH (n)
    WHERE toLower(coalesce(n.name, n.title, n.issue_id, "")) = toLower($target)
       OR toLower(coalesce(n.name, n.title, n.issue_id, "")) CONTAINS toLower($target)
    WITH n
    LIMIT 1
    MATCH (n)-[r]-(m)
    RETURN
        coalesce(n.name, n.title, n.issue_id) AS source,
        labels(n)[0] AS source_label,
        type(r) AS relation,
        coalesce(m.name, m.title, m.issue_id) AS target,
        labels(m)[0] AS target_label
    LIMIT $limit
    """

    return run_cypher(q, {
        "target": safe_target,
        "limit": limit
    })


def generate_node_graph_image(target, limit=50):
    rows = query_node_graph_rows(target, limit=limit)

    if not rows:
        return None

    G = nx.DiGraph()

    center = rows[0].get("source") or target
    G.add_node(center, label=rows[0].get("source_label", "Center"))

    for row in rows:
        source = row.get("source")
        target_node = row.get("target")
        relation = row.get("relation")

        if not source or not target_node:
            continue

        G.add_node(source, label=row.get("source_label", "Unknown"))
        G.add_node(target_node, label=row.get("target_label", "Unknown"))
        G.add_edge(source, target_node, label=relation)

    if len(G.nodes) == 0:
        return None

    # ===== 手動做放射狀 layout =====
    pos = {}
    pos[center] = (0, 0)

    neighbors = [n for n in G.nodes if n != center]
    count = len(neighbors)

    radius = 4.0
    for i, node in enumerate(neighbors):
        angle = 2 * math.pi * i / max(count, 1)
        pos[node] = (
            radius * math.cos(angle),
            radius * math.sin(angle)
        )

    plt.figure(figsize=(12, 9))
    ax = plt.gca()
    ax.set_facecolor("#f7f7f7")

    label_color_map = {
        "Project": "#00D9E9",
        "Component": "#CDEFC2",
        "Material": "#B7B78D",
        "Process": "#D9F5C7",
        "Certification": "#A9A9A9",
        "Department": "#74B9FF",
        "Partner": "#FF7675",
        "Lesson_Learned": "#00D9E9"
    }

    node_colors = []
    node_sizes = []

    for node in G.nodes:
        node_label = G.nodes[node].get("label", "Unknown")
        node_colors.append(label_color_map.get(node_label, "#CCCCCC"))

        if node == center:
            node_sizes.append(3000)
        else:
            node_sizes.append(1800)

    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="#ffffff",
        linewidths=2
    )

    nx.draw_networkx_edges(
        G,
        pos,
        arrows=True,
        arrowstyle="-|>",
        arrowsize=16,
        width=1.5,
        edge_color="#999999",
        connectionstyle="arc3,rad=0.08"
    )

    node_labels = {
        node: shorten_text(node, 18 if node != center else 24)
        for node in G.nodes
    }

    nx.draw_networkx_labels(
        G,
        pos,
        labels=node_labels,
        font_size=10,
        font_color="black",
        font_weight="bold"
    )

    edge_labels = {
        (u, v): data.get("label", "")
        for u, v, data in G.edges(data=True)
    }

    nx.draw_networkx_edge_labels(
        G,
        pos,
        edge_labels=edge_labels,
        font_size=8,
        font_color="#555555",
        rotate=True
    )

    plt.title(f"{center} 關係圖", fontsize=18, fontweight="bold")
    plt.axis("off")
    plt.tight_layout()

    filename = f"node_graph_{uuid.uuid4().hex}.png"
    filepath = os.path.join(STATIC_DIR, filename)

    plt.savefig(filepath, dpi=180, bbox_inches="tight")
    plt.close()

    return filename


def build_node_graph_image_url(target):
    filename = generate_node_graph_image(target)

    if not filename:
        return None

    return f"{PUBLIC_BASE_URL}/static/{filename}"
