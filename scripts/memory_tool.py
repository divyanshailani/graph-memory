import sys
import json
import os
import argparse
from db import init_db, add_node, add_relation, get_node, get_all_nodes, get_all_relations

def cmd_add_node(args):
    attrs = json.loads(args.attributes) if args.attributes else {}
    add_node(args.id, args.type, attrs)
    print(f"Added node: {args.id} (Type: {args.type})")

def cmd_add_relation(args):
    attrs = json.loads(args.attributes) if args.attributes else {}
    add_relation(args.source, args.relation, args.target, attrs)
    print(f"Added relation: {args.source} -[{args.relation}]-> {args.target}")

def cmd_get_node(args):
    data = get_node(args.id)
    if not data:
        print(f"Node {args.id} not found.")
        return
    print(json.dumps(data, indent=2))

def cmd_export_html(args):
    nodes = get_all_nodes()
    relations = get_all_relations()
    
    vis_nodes = []
    for n in nodes:
        vis_nodes.append({
            "id": n["id"],
            "label": n["id"],
            "title": f"Type: {n['type']}\n\n{n['attributes']}",
            "group": n["type"]
        })
        
    vis_edges = []
    for r in relations:
        vis_edges.append({
            "from": r["source_id"],
            "to": r["target_id"],
            "title": r["relation_type"]
        })
        
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Graph Memory Visualization</title>
        <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
        <style type="text/css">
            body {{ margin: 0; padding: 0; font-family: 'Inter', sans-serif; background-color: #121212; }}
            #mynetwork {{
                width: 100vw;
                height: 100vh;
                border: none;
            }}
        </style>
    </head>
    <body>
    <div id="mynetwork"></div>
    <script type="text/javascript">
        var nodes = new vis.DataSet({json.dumps(vis_nodes)});
        var edges = new vis.DataSet({json.dumps(vis_edges)});
        var container = document.getElementById('mynetwork');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            interaction: {{
                hover: true,
                zoomView: true
            }},
            nodes: {{
                shape: 'dot',
                size: 8,
                font: {{
                    size: 10,
                    color: 'rgba(255, 255, 255, 0.5)',
                    face: 'Inter, sans-serif',
                    strokeWidth: 0
                }},
                borderWidth: 0,
                shadow: {{
                    enabled: true,
                    color: 'rgba(0,0,0,0.8)',
                    size: 10,
                    x: 0,
                    y: 0
                }},
                color: {{
                    background: '#2B2B2B',
                    highlight: {{ background: '#ffffff', border: '#ffffff' }},
                    hover: {{ background: '#ffffff', border: '#ffffff' }}
                }}
            }},
            edges: {{
                width: 0.5,
                arrows: {{
                    to: {{ enabled: false }}
                }},
                color: {{
                    color: 'rgba(100, 100, 100, 0.4)',
                    highlight: 'rgba(255, 255, 255, 0.9)',
                    hover: 'rgba(255, 255, 255, 0.9)'
                }},
                smooth: {{
                    type: 'continuous'
                }}
            }},
            physics: {{
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {{
                    gravitationalConstant: -150,
                    centralGravity: 0.005,
                    springLength: 150,
                    springConstant: 0.05,
                    damping: 0.6,
                    avoidOverlap: 0.1
                }},
                stabilization: {{
                    enabled: true,
                    iterations: 300
                }}
            }},
            groups: {{
                "Project": {{ color: {{ background: '#4579e6' }} }},
                "Decision": {{ color: {{ background: '#e64553' }} }},
                "Feature": {{ color: {{ background: '#45e679' }} }},
                "Automation": {{ color: {{ background: '#b245e6' }} }},
                "Infrastructure": {{ color: {{ background: '#e6b245' }} }},
                "Task": {{ color: {{ background: '#45b2e6' }} }}
            }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
    </body>
    </html>
    """
    
    out_path = os.path.join(os.getcwd(), '.agents', 'graph_memory_vis.html')
    with open(out_path, 'w') as f:
        f.write(html_content)
    print(f"Exported HTML visualization to {out_path}")
    
    # Try to open it
    try:
        import webbrowser
        webbrowser.open('file://' + os.path.abspath(out_path))
    except Exception:
        pass

def cmd_export_obsidian(args):
    nodes = get_all_nodes()
    relations = get_all_relations()
    
    export_dir = os.path.abspath(args.dir)
    os.makedirs(export_dir, exist_ok=True)
    
    for n in nodes:
        node_id = n["id"]
        safe_name = "".join([c for c in node_id if c.isalpha() or c.isdigit() or c==' ' or c=='_']).rstrip()
        filename = os.path.join(export_dir, f"{safe_name}.md")
        
        # Find related
        outgoing = [r for r in relations if r["source_id"] == node_id]
        incoming = [r for r in relations if r["target_id"] == node_id]
        
        with open(filename, 'w') as f:
            f.write(f"---\n")
            f.write(f"type: {n['type']}\n")
            f.write(f"---\n\n")
            f.write(f"# {node_id}\n\n")
            f.write(f"**Type:** {n['type']}\n\n")
            f.write(f"## Attributes\n")
            try:
                attrs = json.loads(n['attributes'])
                for k, v in attrs.items():
                    f.write(f"- **{k}**: {v}\n")
            except:
                f.write(f"{n['attributes']}\n")
                
            f.write(f"\n## Outgoing Relationships\n")
            for r in outgoing:
                safe_target = "".join([c for c in r["target_id"] if c.isalpha() or c.isdigit() or c==' ' or c=='_']).rstrip()
                f.write(f"- [{r['relation_type']}] -> [[{safe_target}]]\n")
                
            f.write(f"\n## Incoming Relationships\n")
            for r in incoming:
                safe_source = "".join([c for c in r["source_id"] if c.isalpha() or c.isdigit() or c==' ' or c=='_']).rstrip()
                f.write(f"- [[{safe_source}]] -> [{r['relation_type']}]\n")
                
    print(f"Exported {len(nodes)} nodes to Obsidian format in {export_dir}")

def main():
    init_db() # Ensure schema exists
    
    parser = argparse.ArgumentParser(description="Graph Memory Tool for Antigravity")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    p_add_node = subparsers.add_parser("add_node")
    p_add_node.add_argument("id")
    p_add_node.add_argument("type")
    p_add_node.add_argument("attributes", nargs="?", default="{}")
    
    p_add_rel = subparsers.add_parser("add_relation")
    p_add_rel.add_argument("source")
    p_add_rel.add_argument("relation")
    p_add_rel.add_argument("target")
    p_add_rel.add_argument("attributes", nargs="?", default="{}")
    
    p_get = subparsers.add_parser("get_node")
    p_get.add_argument("id")
    
    p_html = subparsers.add_parser("export_html")
    
    p_obsidian = subparsers.add_parser("export_obsidian")
    p_obsidian.add_argument("dir", default=".agents/obsidian_export", nargs="?")
    
    args = parser.parse_args()
    
    if args.command == "add_node":
        cmd_add_node(args)
    elif args.command == "add_relation":
        cmd_add_relation(args)
    elif args.command == "get_node":
        cmd_get_node(args)
    elif args.command == "export_html":
        cmd_export_html(args)
    elif args.command == "export_obsidian":
        cmd_export_obsidian(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
