import sys
import json
import os
import argparse
from datetime import datetime, timezone
from db import init_db, add_node, add_relation, get_node, get_all_nodes, get_all_relations, delete_node

def cmd_add_node(args):
    attrs = json.loads(args.attributes) if args.attributes else {}
    try:
        add_node(args.id, args.type, args.verification_method, attrs)
        print(f"Added node: {args.id} (Type: {args.type}, Verification: {args.verification_method})")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def cmd_delete_node(args):
    delete_node(args.id)
    print(f"Deleted node: {args.id} and its relationships")

def cmd_add_relation(args):
    attrs = json.loads(args.attributes) if args.attributes else {}
    try:
        add_relation(args.source, args.relation, args.target, args.verification_method, attrs)
        print(f"Added relation: {args.source} -[{args.relation}]-> {args.target} (Verification: {args.verification_method})")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def cmd_get_node(args):
    data = get_node(args.id)
    if not data:
        print(f"Node {args.id} not found.")
        return
    print(json.dumps(data, indent=2))

def cmd_export_html(args):
    nodes = get_all_nodes()
    relations = get_all_relations()
    
    now_ts = datetime.now(timezone.utc).timestamp()
    
    vis_nodes = []
    for n in nodes:
        try:
            attrs = json.loads(n['attributes'])
        except:
            attrs = {}
            
        last_verified = attrs.get('last_verified_at')
        verification_method = attrs.get('verification_method', 'unknown')
        
        is_stale = False
        warning = ""
        
        if not last_verified:
            is_stale = True
            warning += "[UNVERIFIED / LEGACY NODE]\n"
        else:
            try:
                lv_dt = datetime.fromisoformat(last_verified)
                age_days = (now_ts - lv_dt.timestamp()) / 86400
                if age_days > 3:
                    is_stale = True
                    warning += f"[STALE] (Verified {age_days:.1f} days ago)\n"
            except:
                is_stale = True
                warning += "[INVALID TIMESTAMP]\n"
                
        if verification_method in ['agent_self_report', 'assumed', 'unknown']:
            warning += f"[WEAK VERIFICATION]: {verification_method}\n"
            is_stale = True # Treat weak verification as low trust/stale visually
            
        node_data = {
            "id": n["id"],
            "label": n["id"],
            "title": f"{warning}Type: {n['type']}\nVerified via: {verification_method}\n\n{json.dumps(attrs, indent=2)}",
            "group": n["type"]
        }
        
        if is_stale:
            # Override group color to vibrant alert orange/red for untrusted nodes
            node_data["color"] = {
                "background": "#ff6b6b",
                "border": "#ff0000",
                "highlight": { "background": "#ff8787", "border": "#ff0000" },
                "hover": { "background": "#ff8787", "border": "#ff0000" }
            }
            node_data["font"] = { "color": "#ffffff" }
            
        vis_nodes.append(node_data)
        
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
        <title>Trust-Weighted Graph Memory Visualization</title>
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
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(html_content)
    print(f"Exported HTML visualization to {out_path}")

def cmd_export_obsidian(args):
    # Obsidian export remains mostly unchanged, could also inject staleness tags if needed.
    nodes = get_all_nodes()
    relations = get_all_relations()
    
    export_dir = os.path.abspath(args.dir)
    os.makedirs(export_dir, exist_ok=True)
    
    for n in nodes:
        node_id = n["id"]
        safe_name = "".join([c for c in node_id if c.isalpha() or c.isdigit() or c==' ' or c=='_']).rstrip()
        filename = os.path.join(export_dir, f"{safe_name}.md")
        
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
    p_add_node.add_argument("verification_method", help="Required enum: 'source_read', 'test_executed', 'endpoint_tested', 'agent_self_report', 'assumed'")
    p_add_node.add_argument("attributes", nargs="?", default="{}")
    
    p_add_rel = subparsers.add_parser("add_relation")
    p_add_rel.add_argument("source")
    p_add_rel.add_argument("relation")
    p_add_rel.add_argument("target")
    p_add_rel.add_argument("verification_method", help="Required enum: 'source_read', 'test_executed', 'endpoint_tested', 'agent_self_report', 'assumed'")
    p_add_rel.add_argument("attributes", nargs="?", default="{}")
    
    p_get = subparsers.add_parser("get_node")
    p_get.add_argument("id")
    p_get.set_defaults(func=cmd_get_node)

    p_delete = subparsers.add_parser("delete_node")
    p_delete.add_argument("id")
    p_delete.set_defaults(func=cmd_delete_node)

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
    elif args.command == "delete_node":
        cmd_delete_node(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
