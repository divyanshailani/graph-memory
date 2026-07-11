import os
import json
import time
import urllib.request
import urllib.error
from graph_memory.core.engine import get_connection, serialize_subgraph, get_or_create_node as add_node

def _call_gemini_api(prompt: str, api_key: str) -> str:
    """Calls Gemini 2.5 Flash via urllib."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                try:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    return text
                except (KeyError, IndexError):
                    return "Error: Unexpected response structure from Gemini API."
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt < max_retries - 1:
                    sleep_time = 2 ** attempt
                    print(f"[*] Rate limited (HTTP 429). Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue
            print(f"[!] HTTP Error calling Gemini API: {e}")
            return f"Error: {e}"
        except Exception as e:
            print(f"[!] Error calling Gemini API: {e}")
            return f"Error: {e}"
            
    return "Error: Max retries exceeded."

def _clean_markdown(text: str) -> str:
    """Safely strips markdown codeblock formatting if the LLM wrapped its response."""
    text = text.strip()
    if text.startswith("```"):
        # find the first newline to strip the ```markdown line
        newline_idx = text.find("\n")
        if newline_idx != -1:
            text = text[newline_idx+1:]
        else:
            text = text.lstrip("`").strip()
    if text.endswith("```"):
        text = text[:-3]
    return text.strip(" \n`")

def generate_moc_summaries(db_path: str):
    """Fetches all MOC hubs, generates summaries via LLM, and upserts them into the graph."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[!] GEMINI_API_KEY environment variable is not set. Cannot summarize MOCs.")
        return

    print("[*] Starting MOC summarization phase...")
    
    moc_nodes = []
    with get_connection(db_path) as conn:
        cursor = conn.execute("SELECT id, properties FROM Nodes WHERE label = 'MOC_Hub' AND is_deleted = 0")
        for row in cursor.fetchall():
            node_id = row[0]
            props = json.loads(row[1]) if row[1] else {}
            moc_nodes.append((node_id, props))
            
    if not moc_nodes:
        print("[*] No MOC_Hub nodes found in the database. Run `ingest-code` first.")
        return

    print(f"[*] Found {len(moc_nodes)} MOC nodes. Generating summaries...")

    for i, (node_id, props) in enumerate(moc_nodes):
        print(f"[{i+1}/{len(moc_nodes)}] Summarizing {node_id}...")
        
        # 1. Fetch structural skeleton (serialize_subgraph strictly enforces 1-hop depth)
        skeleton = serialize_subgraph(db_path, node_id)
        
        # 2. Prepare the prompt
        prompt = f"""
You are an expert software architect. Below is the structural skeleton of a Map of Content (MOC) module from a codebase.
Your job is to read the files, components, and dependencies listed in this cluster and write a concise, high-level summary (2-4 sentences) describing the business logic and purpose of this module.

Do NOT wrap your answer in markdown code blocks. Output ONLY plain text.

Structural Skeleton:
{skeleton}
"""
        # 3. Call the LLM
        summary_raw = _call_gemini_api(prompt, api_key)
        
        # 4. Strip markdown codeblock trap
        summary_clean = _clean_markdown(summary_raw)
        
        # 5. Upsert back into the graph
        if not summary_clean.startswith("Error:"):
            # Update the properties and use get_or_create_node (which merges properties via UPDATE)
            add_node(db_path, node_id, "MOC_Hub", {"summary": summary_clean})
        else:
            print(summary_clean)
        
        # Rate limit trap safety (implicit 1s sleep)
        time.sleep(1)

    print("[*] MOC summarization complete!")
