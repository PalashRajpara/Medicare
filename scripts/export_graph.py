"""Export compiled LangGraph topologies to Mermaid (.mmd) diagram files."""

from pathlib import Path

from medicare.medicare.graph.build import build_navigator_graph
from medicare.medicare.graph.policy_subgraph import build_policy_graph
from medicare.medicare.graph.sql_subgraph import build_sql_graph


def export_all_graphs(output_dir: str = "docs/graphs") -> None:
    """Compile and export Mermaid graphs to output directory."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Parent Navigator Graph
    parent_graph = build_navigator_graph()
    parent_mmd = parent_graph.get_graph().draw_mermaid()
    (out_path / "graph_parent.mmd").write_text(parent_mmd, encoding="utf-8")
    print(f"Exported parent graph to {out_path / 'graph_parent.mmd'}")

    # 2. Hospital SQL Sub-graph
    sql_graph = build_sql_graph()
    sql_mmd = sql_graph.get_graph().draw_mermaid()
    (out_path / "graph_sql.mmd").write_text(sql_mmd, encoding="utf-8")
    print(f"Exported SQL sub-graph to {out_path / 'graph_sql.mmd'}")

    # 3. Policy RAG Sub-graph
    policy_graph = build_policy_graph()
    policy_mmd = policy_graph.get_graph().draw_mermaid()
    (out_path / "graph_policy.mmd").write_text(policy_mmd, encoding="utf-8")
    print(f"Exported policy sub-graph to {out_path / 'graph_policy.mmd'}")


if __name__ == "__main__":
    export_all_graphs()
