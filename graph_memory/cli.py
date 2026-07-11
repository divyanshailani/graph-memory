import argparse
import sys
import json
import os
import glob

from graph_memory.core import engine

def main():
    parser = argparse.ArgumentParser(description="Graph-Memory CLI Tool")
    parser.add_argument("--db", type=str, help="Path to the SQLite database (defaults to workspace/.agents/graph_memory.sqlite)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # get_node
    get_node_parser = subparsers.add_parser("get_node", help="Get a node and its relationships")
    get_node_parser.add_argument("node_id", type=str, help="The ID of the node to retrieve")
    get_node_parser.add_argument("--min-trust", type=float, default=0.6, help="Minimum trust score filter (default: 0.6)")

    # delete_node
    delete_node_parser = subparsers.add_parser("delete_node", help="Soft-delete a node")
    delete_node_parser.add_argument("node_id", type=str, help="The ID of the node to soft-delete")

    # add_node (Maps to create_entities / add_observation)
    add_node_parser = subparsers.add_parser("add_node", help="Add or update a node")
    add_node_parser.add_argument("node_id", type=str, help="The unique identifier for the node")
    add_node_parser.add_argument("label", type=str, help="The label/type for the node")
    add_node_parser.add_argument("properties", type=str, nargs="?", default="{}", help="JSON properties (optional)")
    add_node_parser.add_argument("--trust", type=float, default=1.0, help="Trust score for the node (default: 1.0)")

    # add_relation (Maps to create_relations)
    add_relation_parser = subparsers.add_parser("add_relation", help="Add a relationship between nodes")
    add_relation_parser.add_argument("source_id", type=str, help="Source node ID")
    add_relation_parser.add_argument("relation_type", type=str, help="Type of relationship")
    add_relation_parser.add_argument("target_id", type=str, help="Target node ID")
    add_relation_parser.add_argument("properties", type=str, nargs="?", default="{}", help="JSON properties (optional)")
    add_relation_parser.add_argument("--trust", type=float, default=1.0, help="Trust score for the relation (default: 1.0)")

    # search
    search_parser = subparsers.add_parser("search", help="Full-text search across nodes")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument("--min-trust", type=float, default=0.6, help="Minimum trust score filter (default: 0.6)")

    # import_md
    import_md_parser = subparsers.add_parser("import", help="Import legacy markdown files into the graph")
    import_md_parser.add_argument("directory", type=str, help="Directory containing .md files")

    # export_html
    export_html_parser = subparsers.add_parser("export_html", help="Export the graph to an HTML visualization")
    export_html_parser.add_argument("output_file", type=str, help="Output HTML file path")

    args = parser.parse_args()
    
    db_path = args.db or engine.get_db_path()
    engine.init_db(db_path)

    try:
        if args.command == "get_node":
            result = engine.serialize_subgraph(db_path, args.node_id, min_trust=args.min_trust)
            print(result)

        elif args.command == "delete_node":
            engine.soft_delete_entity(db_path, args.node_id)
            print(f"Node '{args.node_id}' soft-deleted successfully.")

        elif args.command == "add_node":
            props = json.loads(args.properties)
            engine.get_or_create_node(db_path, args.node_id, args.label, props, trust_score=args.trust)
            print(f"Node '{args.node_id}' added/updated successfully.")

        elif args.command == "add_relation":
            props = json.loads(args.properties)
            engine.create_relation(db_path, args.source_id, args.target_id, args.relation_type, props, trust_score=args.trust)
            print(f"Relation created: {args.source_id} -[{args.relation_type}]-> {args.target_id}")

        elif args.command == "search":
            results = engine.search_nodes(db_path, args.query, min_trust=args.min_trust)
            print(json.dumps(results, indent=2))

        elif args.command == "import":
            md_files = glob.glob(os.path.join(args.directory, "**/*.md"), recursive=True)
            for fpath in md_files:
                basename = os.path.basename(fpath)
                node_id = os.path.splitext(basename)[0]
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    # Create node
                    engine.get_or_create_node(db_path, node_id, "Document", {"type": "legacy_markdown"})
                    # Add content as observation
                    engine.add_observation(db_path, node_id, f"Content snippet: {content[:500]}")
                    print(f"Imported: {node_id}")
                except Exception as e:
                    print(f"Error importing {fpath}: {e}")

        elif args.command == "export_html":
            graph = engine.read_graph(db_path)
            
            # Simple HTML generator using vis.js
            nodes_js = []
            for n in graph["nodes"]:
                trust = n.get("trust_score", 1.0)
                if trust >= 0.9:
                    bg_color = "#2ecc71" # Green
                elif trust >= 0.6:
                    bg_color = "#f39c12" # Orange
                else:
                    bg_color = "#e74c3c" # Red
                    
                nodes_js.append({
                    "id": n["id"],
                    "label": f"{n['id']}\\n({n['label']})",
                    "title": json.dumps(n["properties"], indent=2),
                    "color": {
                        "background": bg_color,
                        "border": "#ffffff",
                        "highlight": {"background": bg_color, "border": "#ffffff"}
                    },
                    "font": {"color": "#ffffff", "face": "system-ui"}
                })
            
            edges_js = []
            for e in graph["edges"]:
                edges_js.append({
                    "from": e["source_id"],
                    "to": e["target_id"],
                    "label": e["relation_type"],
                    "title": json.dumps(e["properties"], indent=2),
                    "arrows": "to",
                    "color": {"color": "#a6accd"},
                    "font": {
                        "align": "middle", 
                        "color": "#ffffff", 
                        "strokeWidth": 3, 
                        "strokeColor": "#1e1e2e",
                        "face": "system-ui"
                    }
                })
                
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Graph Memory Visualization</title>
                <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
                <style type="text/css">
                    body {{ background-color: #1e1e2e; margin: 0; padding: 0; overflow: hidden; font-family: system-ui; }}
                    #mynetwork {{ width: 100vw; height: 100vh; border: none; }}
                    #legend {{ position: absolute; top: 10px; left: 10px; color: white; background: rgba(0,0,0,0.5); padding: 10px; border-radius: 8px; }}
                </style>
            </head>
            <body>
            <div id="legend">
                <h3>Trust Scores</h3>
                <div><span style="color:#2ecc71;">■</span> High Trust (>= 0.9)</div>
                <div><span style="color:#f39c12;">■</span> Medium Trust (0.6 - 0.8)</div>
                <div><span style="color:#e74c3c;">■</span> Low Trust (< 0.6)</div>
            </div>
            <div id="mynetwork"></div>
            <script type="text/javascript">
                var nodes = new vis.DataSet({json.dumps(nodes_js)});
                var edges = new vis.DataSet({json.dumps(edges_js)});
                var container = document.getElementById('mynetwork');
                var data = {{ nodes: nodes, edges: edges }};
                var options = {{
                    physics: {{
                        forceAtlas2Based: {{
                            gravitationalConstant: -50,
                            centralGravity: 0.01,
                            springLength: 100,
                            springConstant: 0.08
                        }},
                        maxVelocity: 50,
                        solver: 'forceAtlas2Based',
                        timestep: 0.35,
                        stabilization: {{ iterations: 150 }}
                    }},
                    edges: {{ smooth: {{ type: 'continuous' }} }},
                    interaction: {{ hover: true }}
                }};
                var network = new vis.Network(container, data, options);
            </script>
            </body>
            </html>
            """
            
            with open(args.output_file, "w") as f:
                f.write(html_content)
            print(f"Exported HTML visualization to {args.output_file}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
