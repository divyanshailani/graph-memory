import sqlite3
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------------

def get_db_path(workspace_dir: str = None) -> str:
    """
    Resolve the SQLite database path. Checks GRAPH_MEMORY_DB_PATH env var first,
    then falls back to workspace_dir/.agents/graph_memory.sqlite.
    """
    env_path = os.environ.get("GRAPH_MEMORY_DB_PATH")
    if env_path:
        return env_path
    
    if not workspace_dir:
        workspace_dir = os.getcwd()
        
    agents_dir = os.path.join(workspace_dir, ".agents")
    os.makedirs(agents_dir, exist_ok=True)
    return os.path.join(agents_dir, "graph_memory.sqlite")

# ---------------------------------------------------------------------------
# Concurrency & Transactions
# ---------------------------------------------------------------------------

@contextmanager
def get_connection(db_path: str):
    """
    Provides a base connection with required PRAGMAs for concurrency and integrity.
    """
    # check_same_thread=False allows multi-agent thread pools (like CrewAI) to share connections safely.
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
    # WAL mode for concurrent readers and a single writer
    conn.execute("PRAGMA journal_mode = WAL;")
    # Enforce foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON;")
    # Enable auto-vacuum to instantly reclaim space when nodes are pruned/soft-deleted
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL;")
    
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def write_transaction(conn: sqlite3.Connection):
    """
    Forces an immediate write-lock. 
    Prevents 'database is locked' deadlock errors when multiple agents try to write simultaneously in WAL mode.
    """
    conn.execute("BEGIN IMMEDIATE;")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

# ---------------------------------------------------------------------------
# Schema Initialization
# ---------------------------------------------------------------------------

def init_db(db_path: str):
    """
    Initialize the Trust-Weighted Epistemic Graph schema.
    """
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            # Nodes Table (Entities)
            # Includes tracking for memory decay and soft deletes.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    properties TEXT, -- JSON payload
                    created_at TEXT NOT NULL,
                    last_verified_at TEXT,
                    updated_at TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active', -- active, superseded
                    is_deleted INTEGER DEFAULT 0
                )
            """)
            
            # Edges Table (Relations)
            # Uses ON DELETE CASCADE and a UNIQUE composite key.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    properties TEXT, -- JSON payload
                    created_at TEXT NOT NULL,
                    last_verified_at TEXT,
                    status TEXT DEFAULT 'active', -- active, superseded
                    FOREIGN KEY(source_id) REFERENCES Nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES Nodes(id) ON DELETE CASCADE,
                    UNIQUE(source_id, target_id, relation_type)
                )
            """)
            
            # FTS5 Shadow Table for Full-Text Search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS NodesFTS USING fts5(
                    id, label, properties, content='Nodes', content_rowid='rowid'
                )
            """)
            
            # Triggers to keep FTS5 synchronized with the main Nodes table
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS tr_nodes_ai AFTER INSERT ON Nodes BEGIN
                    INSERT INTO NodesFTS(rowid, id, label, properties)
                    VALUES (new.rowid, new.id, new.label, new.properties);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS tr_nodes_ad AFTER DELETE ON Nodes BEGIN
                    INSERT INTO NodesFTS(NodesFTS, rowid, id, label, properties)
                    VALUES ('delete', old.rowid, old.id, old.label, old.properties);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS tr_nodes_au AFTER UPDATE ON Nodes BEGIN
                    INSERT INTO NodesFTS(NodesFTS, rowid, id, label, properties)
                    VALUES ('delete', old.rowid, old.id, old.label, old.properties);
                    INSERT INTO NodesFTS(rowid, id, label, properties)
                    VALUES (new.rowid, new.id, new.label, new.properties);
                END;
            """)
            
            # JSON Expression Index
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nodes_type
                ON Nodes(json_extract(properties, '$.type'))
            """)

# ---------------------------------------------------------------------------
# Core Operations
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def search_nodes(db_path: str, query: str) -> list:
    """
    Full-Text Search across the graph using FTS5. Excludes soft-deleted nodes.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT n.id, n.label, n.properties, n.status 
            FROM NodesFTS f
            JOIN Nodes n ON f.rowid = n.rowid
            WHERE NodesFTS MATCH ? AND n.is_deleted = 0
            ORDER BY rank
            LIMIT 20
        """, (query,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "label": row[1],
                "properties": json.loads(row[2]) if row[2] else {},
                "status": row[3]
            })
            
            # Update access count to prevent memory decay
            with write_transaction(conn):
                conn.execute("""
                    UPDATE Nodes 
                    SET access_count = access_count + 1, updated_at = ? 
                    WHERE id = ?
                """, (now_iso(), row[0]))
                
        return results

def get_or_create_node(db_path: str, node_id: str, label: str, properties: dict = None) -> str:
    """
    Creates a node, or returns an existing one to prevent fragmentation.
    Implements the "Supersession" problem solution.
    """
    init_db(db_path)
    props = properties or {}
    
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            # Check for exact match first
            row = conn.execute("SELECT id, properties FROM Nodes WHERE id = ? AND is_deleted = 0", (node_id,)).fetchone()
            
            if row:
                # Update properties (observations map into properties here)
                existing_props = json.loads(row[1]) if row[1] else {}
                existing_props.update(props)
                conn.execute("""
                    UPDATE Nodes 
                    SET properties = ?, updated_at = ?, access_count = access_count + 1
                    WHERE id = ?
                """, (json.dumps(existing_props), now_iso(), node_id))
                return node_id
            
            # Insert new node
            conn.execute("""
                INSERT INTO Nodes (id, label, properties, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (node_id, label, json.dumps(props), now_iso(), now_iso()))
            
            return node_id

def create_relation(db_path: str, source_id: str, target_id: str, relation_type: str, properties: dict = None):
    """
    Draw an edge. Composite UNIQUE constraint prevents identical duplicates.
    """
    init_db(db_path)
    props = properties or {}
    
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                INSERT INTO Edges (source_id, target_id, relation_type, properties, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                    properties = excluded.properties,
                    last_verified_at = ?
            """, (source_id, target_id, relation_type, json.dumps(props), now_iso(), now_iso()))

def add_observation(db_path: str, node_id: str, observation: str):
    """
    Appends an observation directly into the 'observations' array in the properties JSON payload.
    """
    init_db(db_path)
    
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            row = conn.execute("SELECT properties FROM Nodes WHERE id = ? AND is_deleted = 0", (node_id,)).fetchone()
            if not row:
                raise ValueError(f"Node '{node_id}' not found or is deleted.")
            
            props = json.loads(row[0]) if row[0] else {}
            observations = props.get("observations", [])
            observations.append(observation)
            props["observations"] = observations
            
            conn.execute("""
                UPDATE Nodes 
                SET properties = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(props), now_iso(), node_id))

def soft_delete_entity(db_path: str, node_id: str):
    """
    Soft-deletes a node by setting is_deleted=1.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("UPDATE Nodes SET is_deleted = 1, updated_at = ? WHERE id = ?", (now_iso(), node_id))

def delete_relation(db_path: str, source_id: str, target_id: str, relation_type: str):
    """
    Hard-deletes an edge.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                DELETE FROM Edges 
                WHERE source_id = ? AND target_id = ? AND relation_type = ?
            """, (source_id, target_id, relation_type))

def read_graph(db_path: str) -> dict:
    """
    Exports the entire active graph topology.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        nodes = []
        for row in conn.execute("SELECT id, label, properties FROM Nodes WHERE is_deleted = 0").fetchall():
            nodes.append({
                "id": row[0],
                "label": row[1],
                "properties": json.loads(row[2]) if row[2] else {}
            })
            
        edges = []
        for row in conn.execute("SELECT source_id, target_id, relation_type, properties FROM Edges").fetchall():
            edges.append({
                "source_id": row[0],
                "target_id": row[1],
                "relation_type": row[2],
                "properties": json.loads(row[3]) if row[3] else {}
            })
            
        return {"nodes": nodes, "edges": edges}

# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize_subgraph(db_path: str, central_node_id: str) -> str:
    """
    Converts a node's immediate neighborhood into an LLM-readable format.
    Maximizes attention while minimizing token bloat.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        node = conn.execute("""
            SELECT label, properties, status, updated_at 
            FROM Nodes 
            WHERE id = ? AND is_deleted = 0
        """, (central_node_id,)).fetchone()
        
        if not node:
            return f"Node '{central_node_id}' not found or deleted."
            
        label, props_json, status, updated_at = node
        props = json.loads(props_json) if props_json else {}
        
        output = [
            f"Entity: {central_node_id} ({label})",
            f"Status: {status} | Last Updated: {updated_at}",
            f"Metadata: {json.dumps(props, indent=2)}",
            "Relationships:"
        ]
        
        edges = conn.execute("""
            SELECT relation_type, target_id, properties 
            FROM Edges 
            WHERE source_id = ?
        """, (central_node_id,)).fetchall()
        
        if not edges:
            output.append("  (None)")
        else:
            for rel_type, target, e_props in edges:
                output.append(f"  -[{rel_type}]-> {target} (Context: {e_props})")
                
        # Also show incoming edges
        incoming_edges = conn.execute("""
            SELECT source_id, relation_type, properties 
            FROM Edges 
            WHERE target_id = ?
        """, (central_node_id,)).fetchall()
        
        if incoming_edges:
            output.append("Incoming Relationships:")
            for source, rel_type, e_props in incoming_edges:
                output.append(f"  {source} -[{rel_type}]-> (this) (Context: {e_props})")
                
        return "\n".join(output)
