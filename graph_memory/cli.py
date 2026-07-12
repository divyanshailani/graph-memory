import argparse
import sys
import json
import os
import glob

from graph_memory.core import engine
from graph_memory.core.ingest import ingest_codebase

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
    add_node_parser.add_argument("--link-to", type=str, default=None, help="Optional parent node ID to link to atomically")
    add_node_parser.add_argument("--link-type", type=str, default="PART_OF", help="Relation type if --link-to is provided (default: PART_OF)")
    add_node_parser.add_argument("--method", type=str, default="unknown", help="Verification method for trust audit trail")

    # add_relation (Maps to create_relations)
    add_relation_parser = subparsers.add_parser("add_relation", help="Add a relationship between nodes")
    add_relation_parser.add_argument("source_id", type=str, help="Source node ID")
    add_relation_parser.add_argument("relation_type", type=str, help="Type of relationship")
    add_relation_parser.add_argument("target_id", type=str, help="Target node ID")
    add_relation_parser.add_argument("properties", type=str, nargs="?", default="{}", help="JSON properties (optional)")
    add_relation_parser.add_argument("--trust", type=float, default=1.0, help="Trust score for the relation (default: 1.0)")
    add_relation_parser.add_argument("--method", type=str, default="unknown", help="Verification method for trust audit trail")

    # search
    search_parser = subparsers.add_parser("search", help="Full-text search across nodes")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument("--min-trust", type=float, default=0.6, help="Minimum trust score filter (default: 0.6)")

    # sweep
    sweep_parser = subparsers.add_parser("sweep", help="Sweep and soft-delete orphaned nodes")
    sweep_parser.add_argument("--root", type=str, default="Project_Graph_Memory", help="Root node ID to protect from sweeping (default: Project_Graph_Memory)")

    # decay-trust
    decay_parser = subparsers.add_parser("decay-trust", help="Decay the trust score of stale nodes and edges")
    decay_parser.add_argument("--days", type=int, default=3, help="Threshold in days before trust decays (default: 3)")

    # Import
    import_parser = subparsers.add_parser("import", help="Import legacy Markdown files (.md) into the graph")
    import_parser.add_argument("directory", help="Directory containing .md files to import")
    
    # Ingest Code
    ingest_parser = subparsers.add_parser("ingest-code", help="Parse AST of a codebase and build structural MOC graph")
    ingest_parser.add_argument("directory", help="Directory containing code to ingest")
    
    # Summarize MOCs
    summarize_parser = subparsers.add_parser("summarize-mocs", help="Auto-generates semantic summaries for all MOCs")

    # Export HTML_html
    export_html_parser = subparsers.add_parser("export_html", help="Export the graph to an HTML visualization")
    export_html_parser.add_argument("output_file", type=str, help="Output HTML file path")

    # Export 3D WebGL
    export_3d_parser = subparsers.add_parser("export-3d", help="Export the graph into a GPU-accelerated WebGL 3D Viewer")
    export_3d_parser.add_argument("output_file", type=str, help="Output HTML file path")

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
            engine.get_or_create_node(
                db_path, 
                args.node_id, 
                args.label, 
                props, 
                trust_score=args.trust,
                verification_method=args.method,
                link_to=args.link_to,
                link_type=args.link_type
            )
            print(f"Node '{args.node_id}' added/updated successfully.")

        elif args.command == "add_relation":
            props = json.loads(args.properties)
            engine.create_relation(db_path, args.source_id, args.target_id, args.relation_type, props, trust_score=args.trust, verification_method=args.method)
            print(f"Relation created: {args.source_id} -[{args.relation_type}]-> {args.target_id}")

        elif args.command == "search":
            results = engine.search_nodes(db_path, args.query, min_trust=args.min_trust)
            print(json.dumps(results, indent=2))

        elif args.command == "sweep":
            count = engine.sweep_orphans(db_path, root_id=args.root)
            print(f"Sweep complete. Soft-deleted {count} orphaned node(s).")

        elif args.command == "decay-trust":
            with engine.get_connection(db_path) as conn:
                with engine.write_transaction(conn):
                    cursor = conn.execute(f"UPDATE Nodes SET trust_score = MAX(0.0, trust_score - 0.1) WHERE last_verified_at < date('now', '-{args.days} days') AND trust_score > 0.0 AND is_deleted = 0")
                    node_count = cursor.rowcount
                    cursor = conn.execute(f"UPDATE Edges SET trust_score = MAX(0.0, trust_score - 0.1) WHERE last_verified_at < date('now', '-{args.days} days') AND trust_score > 0.0")
                    edge_count = cursor.rowcount
            print(f"Decayed trust for {node_count} nodes and {edge_count} edges older than {args.days} days.")

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

        elif args.command == "ingest-code":
            from graph_memory.core.ingest import ingest_codebase
            ingest_codebase(db_path, args.directory)

        elif args.command == "summarize-mocs":
            from graph_memory.core.summarizer import generate_moc_summaries
            generate_moc_summaries(db_path)

        elif args.command == "export-3d":
            with engine.get_connection(db_path) as conn:
                nodes = []
                links = []
                
                db_nodes = conn.execute("SELECT id, label, trust_score, properties FROM Nodes WHERE is_deleted = 0").fetchall()
                for n_id, label, trust, props in db_nodes:
                    color = "#00ffa6" if trust >= 0.9 else "#ffbb00" if trust >= 0.6 else "#ff3366"
                    nodes.append({
                        "id": n_id,
                        "name": n_id,
                        "group": label,
                        "color": color,
                        "val": 1.5 if label == 'Domain' else 0.5
                    })
                    
                db_edges = conn.execute("SELECT e.source_id, e.target_id, e.relation_type FROM Edges e JOIN Nodes s ON s.id = e.source_id JOIN Nodes t ON t.id = e.target_id WHERE e.status = 'active' AND s.is_deleted = 0 AND t.is_deleted = 0").fetchall()
                for src, tgt, rel in db_edges:
                    links.append({
                        "source": src,
                        "target": tgt,
                        "name": rel
                    })

            graph_data = json.dumps({"nodes": nodes, "links": links}).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Epistemic Graph Memory - Fast 2D Canvas</title>
    <style> 
        body {{ margin: 0; overflow: hidden; background-color: #0b0d17; font-family: sans-serif; }}
        #legend {{
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(11, 13, 23, 0.85);
            padding: 15px;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.1);
            color: #ffffff;
            font-size: 14px;
            z-index: 1000;
        }}
        .legend-item {{ display: flex; align-items: center; margin-top: 8px; }}
        .color-box {{ width: 12px; height: 12px; margin-right: 8px; border-radius: 2px; }}
    </style>
    <script src="https://unpkg.com/force-graph@1.43.3/dist/force-graph.min.js"></script>
</head>
<body>
    <div id="legend">
        <b>Trust Scores</b>
        <div class="legend-item"><div class="color-box" style="background:#00ffa6;"></div> High Trust (&gt;= 0.9)</div>
        <div class="legend-item"><div class="color-box" style="background:#ffbb00;"></div> Medium Trust (0.6 - 0.8)</div>
        <div class="legend-item"><div class="color-box" style="background:#ff3366;"></div> Low Trust (&lt; 0.6)</div>
    </div>
    <div id="2d-graph"></div>
    <script>
        const graphData = {graph_data};
        
        const highlightNodes = new Set();
        const highlightLinks = new Set();
        let hoverNode = null;

        const Graph = ForceGraph()
          (document.getElementById('2d-graph'))
            .graphData(graphData)
            .nodeCanvasObject((node, ctx, globalScale) => {{
                const isHighlighted = hoverNode === node || highlightNodes.has(node);
                const isDimmed = hoverNode && !isHighlighted;
                
                const label = node.name;
                const fontSize = isHighlighted ? 16 : 12;
                ctx.font = `bold ${{fontSize}}px Sans-Serif`;
                const textWidth = ctx.measureText(label).width;
                const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.8);

                ctx.fillStyle = isDimmed ? 'rgba(50, 50, 50, 0.2)' : node.color;
                ctx.beginPath();
                if (ctx.roundRect) {{
                    ctx.roundRect(
                        node.x - bckgDimensions[0] / 2, 
                        node.y - bckgDimensions[1] / 2, 
                        bckgDimensions[0], 
                        bckgDimensions[1], 
                        4
                    );
                }} else {{
                    ctx.rect(
                        node.x - bckgDimensions[0] / 2, 
                        node.y - bckgDimensions[1] / 2, 
                        bckgDimensions[0], 
                        bckgDimensions[1]
                    );
                }}
                ctx.fill();
                
                if (isHighlighted) {{
                    ctx.strokeStyle = '#ffffff';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }}

                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = isDimmed ? 'rgba(11, 13, 23, 0.5)' : '#0b0d17';
                ctx.fillText(label, node.x, node.y);

                node.__bckgDimensions = bckgDimensions;
            }})
            .nodePointerAreaPaint((node, color, ctx) => {{
                ctx.fillStyle = color;
                const bckgDimensions = node.__bckgDimensions;
                bckgDimensions && ctx.fillRect(node.x - bckgDimensions[0] / 2, node.y - bckgDimensions[1] / 2, bckgDimensions[0], bckgDimensions[1]);
            }})
            .linkColor(link => highlightLinks.has(link) ? '#00ffa6' : 'rgba(166, 172, 205, 0.2)')
            .linkWidth(link => highlightLinks.has(link) ? 2 : 0.5)
            .linkDirectionalArrowLength(link => highlightLinks.has(link) ? 6 : 4)
            .linkDirectionalArrowRelPos(1)
            .onNodeHover(node => {{
                highlightNodes.clear();
                highlightLinks.clear();
                
                if (node) {{
                    highlightNodes.add(node);
                    graphData.links.forEach(link => {{
                        const src = link.source.id || link.source;
                        const tgt = link.target.id || link.target;
                        const n_id = node.id || node;
                        if (src === n_id || tgt === n_id) {{
                            highlightLinks.add(link);
                            highlightNodes.add(src === n_id ? link.target : link.source);
                        }}
                    }});
                    // Enable particles only during hover so GPU can sleep otherwise
                    Graph.linkDirectionalParticles(link => highlightLinks.has(link) ? 4 : 0);
                    Graph.linkDirectionalParticleWidth(3);
                }} else {{
                    // Completely disable particles when idle to allow render loop to pause
                    Graph.linkDirectionalParticles(0);
                }}

                hoverNode = node || null;
                Graph.nodeCanvasObject(Graph.nodeCanvasObject());
            }})
            .onNodeClick(node => {{
                Graph.centerAt(node.x, node.y, 1000);
                Graph.zoom(3, 1000);
            }});
            
        // 2D Physics - Massive repulsion, longer links, and NO center gravity so it completely unclutters!
        // We set cooldownTicks so the engine fully powers down the GPU after 5 seconds of untangling.
        Graph.d3Force('charge').strength(-3000);
        Graph.d3Force('link').distance(200);
        Graph.d3Force('center', null);
        Graph.cooldownTicks(300);
        
        let initialZoom = false;
        Graph.onEngineStop(() => {{
            if (!initialZoom) {{
                Graph.zoomToFit(400, 50);
                initialZoom = true;
            }}
        }});
        
        // Ensure it always utilizes the full screen perfectly
        window.addEventListener('resize', () => {{
            Graph.width(window.innerWidth).height(window.innerHeight);
        }});
        
        // Set initial full screen
        Graph.width(window.innerWidth).height(window.innerHeight);
    </script>
</body>
</html>
"""

            with open(args.output_file, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"✅ GPU-Accelerated Graph exported to {args.output_file}")

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
                    "label": f"{n['id']}\n({n['label']})",
                    "shape": "box",
                    "margin": 12,
                    "title": json.dumps(n["properties"], indent=2),
                    "color": {
                        "background": bg_color,
                        "border": bg_color,
                        "highlight": {"background": bg_color, "border": "#ffffff"}
                    },
                    "font": {"color": "#1e1e2e", "face": "system-ui", "bold": True}
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
                
            nodes_json = json.dumps(nodes_js).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            edges_json = json.dumps(edges_js).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
                
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
                var nodes = new vis.DataSet({nodes_json});
                var edges = new vis.DataSet({edges_json});
                var container = document.getElementById('mynetwork');
                var data = {{ nodes: nodes, edges: edges }};
                var options = {{
                    physics: {{
                        forceAtlas2Based: {{
                            gravitationalConstant: -150,
                            centralGravity: 0.005,
                            springLength: 250,
                            springConstant: 0.04
                        }},
                        maxVelocity: 50,
                        solver: 'forceAtlas2Based',
                        timestep: 0.35,
                        stabilization: {{ iterations: 150 }}
                    }},
                    edges: {{ 
                        smooth: {{ type: 'continuous' }},
                        color: {{ opacity: 0.5 }}
                    }},
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
