import os
import uuid
import networkx as nx
import matplotlib.pyplot as plt


STATIC_DIR = "/content/test/static"


def ensure_static_dir():
    os.makedirs(STATIC_DIR, exist_ok=True)


def generate_relation_graph_image(source, target, relation_type):
    """
    產生兩節點一關係的 PNG 圖片
    回傳圖片檔名
    """
    ensure_static_dir()

    filename = f"graph_{uuid.uuid4().hex}.png"
    filepath = os.path.join(STATIC_DIR, filename)

    G = nx.DiGraph()
    G.add_node(source)
    G.add_node(target)
    G.add_edge(source, target, label=relation_type)

    pos = {
        source: (0, 0),
        target: (2.8, 0)
    }

    plt.figure(figsize=(7, 3))
    ax = plt.gca()
    ax.set_axis_off()

    nx.draw_networkx_nodes(
        G,
        pos,
        node_size=3600,
        node_color=["#31DDE8", "#A9A97A"],
        edgecolors=["#31DDE8", "#31DDE8"],
        linewidths=3
    )

    nx.draw_networkx_labels(
        G,
        pos,
        font_size=13,
        font_family="sans-serif"
    )

    nx.draw_networkx_edges(
        G,
        pos,
        arrows=True,
        arrowsize=20,
        width=2,
        edge_color="#888888",
        connectionstyle="arc3,rad=0.0"
    )

    edge_labels = {
        (source, target): relation_type
    }

    nx.draw_networkx_edge_labels(
        G,
        pos,
        edge_labels=edge_labels,
        font_size=10,
        font_color="#666666",
        rotate=True
    )

    plt.tight_layout()
    plt.savefig(filepath, format="png", dpi=180, bbox_inches="tight", transparent=False)
    plt.close()

    return filename