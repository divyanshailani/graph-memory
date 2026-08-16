import sqlite3
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

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
                    is_deleted INTEGER DEFAULT 0,
                    trust_score FLOAT DEFAULT 1.0,
                    verification_method TEXT DEFAULT 'unknown'
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
                    trust_score FLOAT DEFAULT 1.0,
                    verification_method TEXT DEFAULT 'unknown',
                    FOREIGN KEY(source_id) REFERENCES Nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_id) REFERENCES Nodes(id) ON DELETE CASCADE,
                    UNIQUE(source_id, target_id, relation_type)
                )
            """)
            
            # Decision_Ledger Table (First-Class Multi-Agent Audit Trail)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Decision_Ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(node_id) REFERENCES Nodes(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_agent ON Decision_Ledger(agent_name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_node ON Decision_Ledger(node_id);")

            # Session_Logs Table & FTS5 Index (Episodic Multi-Session Archive)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS Session_Logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON Session_Logs(session_id);")
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS Session_Logs_fts USING fts5(session_id, agent_name, role, content);")

            # Migration for existing databases
            try:
                conn.execute("ALTER TABLE Nodes ADD COLUMN trust_score FLOAT DEFAULT 1.0")
            except sqlite3.OperationalError:
                pass # Column already exists
            try:
                conn.execute("ALTER TABLE Edges ADD COLUMN trust_score FLOAT DEFAULT 1.0")
            except sqlite3.OperationalError:
                pass # Column already exists
            try:
                conn.execute("ALTER TABLE Nodes ADD COLUMN verification_method TEXT DEFAULT 'unknown'")
            except sqlite3.OperationalError:
                pass # Column already exists
            try:
                conn.execute("ALTER TABLE Edges ADD COLUMN verification_method TEXT DEFAULT 'unknown'")
            except sqlite3.OperationalError:
                pass # Column already exists
            
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

def calculate_effective_trust(base_trust: float, last_verified_at: str, half_life_days: float = 30.0) -> float:
    """
    Calculates time-decayed effective trust score based on Ebbinghaus forgetting curve half-life.
    Formula: base_trust * (0.5 ** (elapsed_days / half_life_days))
    """
    if not last_verified_at:
        return base_trust
    try:
        verified_dt = datetime.fromisoformat(last_verified_at)
        now = datetime.now(timezone.utc)
        if verified_dt.tzinfo is None:
            verified_dt = verified_dt.replace(tzinfo=timezone.utc)
        elapsed_days = (now - verified_dt).total_seconds() / 86400.0
        if elapsed_days <= 0:
            return base_trust
        decay_factor = 0.5 ** (elapsed_days / half_life_days)
        return round(base_trust * decay_factor, 4)
    except Exception:
        return base_trust

def get_effective_trust_for_node(db_path: str, node_id: str, half_life_days: float = 30.0) -> float:
    """Returns effective trust score for a node."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT trust_score, last_verified_at FROM Nodes WHERE id = ?", (node_id,)).fetchone()
        if not row:
            return 1.0
        return calculate_effective_trust(row[0] or 1.0, row[1], half_life_days)

def record_decision_ledger(db_path: str, node_id: str, agent_name: str, action: str, rationale: str):
    """Records an entry in the first-class Decision_Ledger table."""
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                INSERT INTO Decision_Ledger (node_id, agent_name, action, rationale, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (node_id, agent_name or "System", action, rationale or "N/A", now_iso()))

def query_decision_ledger(db_path: str, agent_name: str = None, node_id: str = None, days: int = None, limit: int = 50) -> list:
    """Queries historical decision entries across nodes by agent, node_id, or timeframe."""
    with get_connection(db_path) as conn:
        query = "SELECT id, node_id, agent_name, action, rationale, timestamp FROM Decision_Ledger WHERE 1=1"
        params = []
        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)
        if node_id:
            query += " AND node_id = ?"
            params.append(node_id)
        if days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            query += " AND timestamp >= ?"
            params.append(cutoff)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": r[0],
                "node_id": r[1],
                "agent_name": r[2],
                "action": r[3],
                "rationale": r[4],
                "timestamp": r[5]
            }
            for r in rows
        ]

def log_session_message(db_path: str, session_id: str, agent_name: str, role: str, content: str) -> int:
    """Logs a conversation message into Session_Logs and updates FTS5 index."""
    init_db(db_path)
    ts = now_iso()
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            cursor = conn.execute("""
                INSERT INTO Session_Logs (session_id, agent_name, role, content, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, agent_name, role, content, ts))
            row_id = cursor.lastrowid
            try:
                conn.execute("""
                    INSERT INTO Session_Logs_fts (rowid, session_id, agent_name, role, content)
                    VALUES (?, ?, ?, ?, ?)
                """, (row_id, session_id, agent_name, role, content))
            except sqlite3.OperationalError:
                pass
            return row_id

def search_session_logs(db_path: str, query_str: str, session_id: str = None, limit: int = 20) -> list:
    """Performs FTS5 search across historic session logs."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        formatted_query = ' OR '.join(query_str.split()) if '"' not in query_str else query_str
        sql = """
            SELECT s.id, s.session_id, s.agent_name, s.role, s.content, s.timestamp
            FROM Session_Logs s
            JOIN Session_Logs_fts fts ON s.id = fts.rowid
            WHERE Session_Logs_fts MATCH ?
        """
        params = [formatted_query]
        if session_id:
            sql += " AND s.session_id = ?"
            params.append(session_id)
        sql += " ORDER BY s.id DESC LIMIT ?"
        params.append(limit)
        
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # Fallback to LIKE if FTS expression fails
            sql_fallback = "SELECT id, session_id, agent_name, role, content, timestamp FROM Session_Logs WHERE content LIKE ? ORDER BY id DESC LIMIT ?"
            rows = conn.execute(sql_fallback, (f"%{query_str}%", limit)).fetchall()
            
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "agent_name": r[2],
                "role": r[3],
                "content": r[4],
                "timestamp": r[5]
            }
            for r in rows
        ]

# ---------------------------------------------------------------------------
# Core Operations
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def search_nodes(db_path: str, query: str, min_trust: float = 0.6, half_life_days: float = 30.0) -> list:
    """
    Full-Text Search across the graph using FTS5. Excludes soft-deleted nodes and those below effective trust threshold.
    Calculates time-decayed effective trust score dynamically based on last_verified_at.
    Access-count bumps for all matched nodes are batched into a single write transaction.
    """
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.execute("""
            SELECT n.id, n.label, n.properties, n.status, n.trust_score, n.last_verified_at 
            FROM NodesFTS f
            JOIN Nodes n ON f.rowid = n.rowid
            WHERE NodesFTS MATCH ? AND n.is_deleted = 0
            ORDER BY rank
            LIMIT 50
        """, (query,))
        
        results = []
        matched_ids = []
        for row in cursor.fetchall():
            node_id, label, props_json, status, base_trust, last_verified_at = row
            eff_trust = calculate_effective_trust(base_trust or 1.0, last_verified_at, half_life_days)
            
            if eff_trust < min_trust:
                continue
                
            props = json.loads(props_json) if props_json else {}
            results.append({
                "id": node_id,
                "label": label,
                "properties": props,
                "status": status,
                "effective_trust": eff_trust
            })
            matched_ids.append(node_id)
            
            if len(results) >= 20:
                break
                
        # Batched read-feedback: one write transaction for the whole result set
        # instead of one transaction per row (prevents write amplification on the read path).
        if matched_ids:
            placeholders = ",".join("?" * len(matched_ids))
            with write_transaction(conn):
                conn.execute(f"""
                    UPDATE Nodes 
                    SET access_count = access_count + 1, updated_at = ? 
                    WHERE id IN ({placeholders})
                """, (now_iso(), *matched_ids))
                
        return results

MAX_NODE_HISTORY = 10  # retained entries per node; older mechanical entries are pruned on upsert

def get_or_create_node(
    db_path: str, 
    node_id: str, 
    label: str, 
    properties: dict = None, 
    trust_score: float = 1.0, 
    verification_method: str = "unknown", 
    link_to: str = None, 
    link_type: str = "PART_OF",
    agent_name: str = "Tree-sitter",
    rationale: str = None,
    design_intent: str = None,
    log_ledger: bool = True
) -> str:
    """
    Creates a node, or returns an existing one to prevent fragmentation.
    Implements agent provenance attribution and decision history tracking.
    History is capped at MAX_NODE_HISTORY entries and consecutive identical entries are
    collapsed, so repeated mechanical re-verifications never grow the JSON payload.
    Set log_ledger=False for deterministic bulk operations (e.g. AST re-parsing) that
    are not agent decisions — provenance for those still lives in node properties.
    """
    init_db(db_path)
    node_id = resolve_canonical_id(db_path, node_id)
    if link_to:
        link_to = resolve_canonical_id(db_path, link_to)
    props = properties or {}
    
    if "author_agent" not in props:
        props["author_agent"] = agent_name
    props["last_modified_by"] = agent_name
    if rationale:
        props["rationale"] = rationale
    if design_intent:
        props["design_intent"] = design_intent
        
    history_entry = {
        "timestamp": now_iso(),
        "agent": agent_name,
        "action": "upsert_node",
        "rationale": rationale or "Node created or updated"
    }

    with get_connection(db_path) as conn:
        with write_transaction(conn):
            row = conn.execute("SELECT id, properties FROM Nodes WHERE id = ?", (node_id,)).fetchone()
            
            if row:
                existing_props = json.loads(row[1]) if row[1] else {}
                hist = existing_props.get("history", [])
                last = hist[-1] if hist else None
                is_repeat = (
                    last
                    and last.get("agent") == history_entry["agent"]
                    and last.get("action") == history_entry["action"]
                    and last.get("rationale") == history_entry["rationale"]
                )
                if not is_repeat:
                    hist.append(history_entry)
                existing_props["history"] = hist[-MAX_NODE_HISTORY:]
                
                existing_obs = existing_props.get("observations", [])
                new_obs = props.get("observations", [])
                combined_obs = list(dict.fromkeys(existing_obs + new_obs))
                
                existing_props.update(props)
                existing_props["observations"] = combined_obs
                
                conn.execute("""
                    UPDATE Nodes 
                    SET properties = ?, is_deleted = 0, status = 'active', updated_at = ?, last_verified_at = ?, access_count = access_count + 1, trust_score = MAX(trust_score, ?), verification_method = ?
                    WHERE id = ?
                """, (json.dumps(existing_props), now_iso(), now_iso(), trust_score, verification_method, node_id))
            else:
                props["history"] = [history_entry]
                conn.execute("""
                    INSERT INTO Nodes (id, label, properties, created_at, last_verified_at, updated_at, trust_score, verification_method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (node_id, label, json.dumps(props), now_iso(), now_iso(), now_iso(), trust_score, verification_method))
                
            if link_to:
                conn.execute("""
                    INSERT INTO Nodes (id, label, properties, created_at, last_verified_at, updated_at, trust_score, verification_method)
                    VALUES (?, 'Fact_Node', '{}', ?, ?, ?, 1.0, 'auto')
                    ON CONFLICT(id) DO NOTHING
                """, (link_to, now_iso(), now_iso(), now_iso()))
                
                conn.execute("""
                    INSERT INTO Edges (source_id, target_id, relation_type, properties, created_at, last_verified_at, trust_score, verification_method)
                    VALUES (?, ?, ?, '{}', ?, ?, ?, ?)
                    ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                        last_verified_at = excluded.last_verified_at,
                        verification_method = excluded.verification_method,
                        trust_score = MAX(trust_score, excluded.trust_score)
                """, (node_id, link_to, link_type, now_iso(), now_iso(), trust_score, verification_method))
            
            if log_ledger:
                conn.execute("""
                    INSERT INTO Decision_Ledger (node_id, agent_name, action, rationale, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (node_id, agent_name or "System", "upsert_node", rationale or "Node created or updated", now_iso()))
            
            return node_id

def sweep_orphans(db_path: str, root_id: str = None) -> int:
    """Soft-deletes all nodes that have 0 edges, excluding the root node if provided. Returns rows affected."""
    init_db(db_path)
    
    if root_id is None:
        root_id = os.environ.get("GRAPH_MEMORY_ROOT_ID", "Project_Graph_Memory")
        
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            cursor = conn.execute("""
                UPDATE Nodes 
                SET is_deleted = 1, updated_at = ?
                WHERE id != ? 
                  AND is_deleted = 0
                  AND NOT EXISTS (SELECT 1 FROM Edges WHERE source_id = Nodes.id)
                  AND NOT EXISTS (SELECT 1 FROM Edges WHERE target_id = Nodes.id)
            """, (now_iso(), root_id))
            return cursor.rowcount

def create_relation(
    db_path: str, 
    source_id: str, 
    target_id: str, 
    relation_type: str, 
    props: dict = None,
    trust_score: float = 1.0,
    verification_method: str = "unknown"
):
    """
    Creates a directional edge between source_id and target_id with ON CONFLICT UPDATE semantics.
    Resolves canonical pointers automatically.
    """
    init_db(db_path)
    source_id = resolve_canonical_id(db_path, source_id)
    target_id = resolve_canonical_id(db_path, target_id)
    
    if props is None:
        props = {}
        
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            conn.execute("""
                INSERT INTO Nodes (id, label, properties, created_at, last_verified_at, updated_at, trust_score, verification_method)
                VALUES (?, 'Fact_Node', '{}', ?, ?, ?, 1.0, 'auto')
                ON CONFLICT(id) DO NOTHING
            """, (source_id, now_iso(), now_iso(), now_iso()))
            conn.execute("""
                INSERT INTO Nodes (id, label, properties, created_at, last_verified_at, updated_at, trust_score, verification_method)
                VALUES (?, 'Fact_Node', '{}', ?, ?, ?, 1.0, 'auto')
                ON CONFLICT(id) DO NOTHING
            """, (target_id, now_iso(), now_iso(), now_iso()))

            conn.execute("""
                INSERT INTO Edges (source_id, target_id, relation_type, properties, created_at, last_verified_at, trust_score, verification_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                    properties = excluded.properties,
                    last_verified_at = excluded.last_verified_at,
                    verification_method = excluded.verification_method,
                    trust_score = MAX(trust_score, excluded.trust_score)
            """, (source_id, target_id, relation_type, json.dumps(props), now_iso(), now_iso(), trust_score, verification_method))

def add_observation(
    db_path: str, 
    node_id: str, 
    observation: str,
    agent_name: str = "AI-Agent",
    rationale: str = None
):
    """
    Appends an observation and logs decision rationale in history and Decision_Ledger.
    """
    init_db(db_path)
    node_id = resolve_canonical_id(db_path, node_id)
    
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            row = conn.execute("SELECT properties FROM Nodes WHERE id = ? AND is_deleted = 0", (node_id,)).fetchone()
            if not row:
                raise ValueError(f"Node '{node_id}' not found or is deleted.")
            
            props = json.loads(row[0]) if row[0] else {}
            obs_list = props.get("observations", [])
            if observation not in obs_list:
                obs_list.append(observation)
            props["observations"] = obs_list
            props["last_modified_by"] = agent_name
            
            hist = props.get("history", [])
            hist.append({
                "timestamp": now_iso(),
                "agent": agent_name,
                "action": "add_observation",
                "observation": observation,
                "rationale": rationale or "Added observation"
            })
            props["history"] = hist
            
            conn.execute("""
                UPDATE Nodes 
                SET properties = ?, updated_at = ?, last_verified_at = ?
                WHERE id = ?
            """, (json.dumps(props), now_iso(), now_iso(), node_id))
            
            conn.execute("""
                INSERT INTO Decision_Ledger (node_id, agent_name, action, rationale, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (node_id, agent_name or "System", "add_observation", rationale or f"Observation: {observation[:100]}", now_iso()))

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
        for row in conn.execute("SELECT id, label, properties, trust_score, created_at, last_verified_at FROM Nodes WHERE is_deleted = 0").fetchall():
            nodes.append({
                "id": row[0],
                "label": row[1],
                "properties": json.loads(row[2]) if row[2] else {},
                "trust_score": row[3],
                "created_at": row[4],
                "last_verified_at": row[5]
            })
            
        edges = []
        for row in conn.execute("SELECT e.source_id, e.target_id, e.relation_type, e.properties, e.trust_score, e.verification_method, e.created_at, e.last_verified_at FROM Edges e JOIN Nodes s ON s.id = e.source_id JOIN Nodes t ON t.id = e.target_id WHERE s.is_deleted = 0 AND t.is_deleted = 0").fetchall():
            edges.append({
                "source_id": row[0],
                "target_id": row[1],
                "relation_type": row[2],
                "properties": json.loads(row[3]) if row[3] else {},
                "trust_score": row[4],
                "verification_method": row[5],
                "created_at": row[6],
                "last_verified_at": row[7]
            })
            
        return {"nodes": nodes, "edges": edges}

# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize_subgraph(db_path: str, central_node_id: str, min_trust: float = 0.0, half_life_days: float = 30.0) -> str:
    """
    Converts a node's immediate neighborhood into an LLM-readable format.
    Maximizes attention while minimizing token bloat. Automatically follows alias redirects.
    Computes time-decayed effective trust score dynamically based on last_verified_at.
    """
    init_db(db_path)
    canon_id = resolve_canonical_id(db_path, central_node_id)
    is_redirected = (canon_id != central_node_id)
    original_requested_id = central_node_id
    central_node_id = canon_id

    with get_connection(db_path) as conn:
        node = conn.execute("""
            SELECT label, properties, status, updated_at, created_at, last_verified_at, trust_score 
            FROM Nodes 
            WHERE id = ? AND is_deleted = 0
        """, (central_node_id,)).fetchone()
        
        if not node:
            return f"Node '{original_requested_id}' not found or deleted."
            
        label, props_json, status, updated_at, created_at, last_verified_at, base_trust = node
        base_t = base_trust if base_trust is not None else 1.0
        eff_t = calculate_effective_trust(base_t, last_verified_at, half_life_days)
        
        if eff_t < min_trust:
            return f"Node '{original_requested_id}' is below trust threshold (Effective Trust: {eff_t:.2f} < {min_trust:.2f})."
            
        props = json.loads(props_json) if props_json else {}
        
        output = []
        if is_redirected:
            output.append(f"[Alias Redirect: '{original_requested_id}' was merged into canonical entity '{central_node_id}']")

        author = props.get("author_agent", "Unknown")
        last_mod = props.get("last_modified_by", author)
        rationale = props.get("rationale")
        intent = props.get("design_intent")
        signature = props.get("signature")
        docstring = props.get("docstring")
        start_line = props.get("start_line")
        end_line = props.get("end_line")
        snippet = props.get("snippet")
        history = props.get("history", [])

        pct_decay = round((1.0 - (eff_t / base_t)) * 100) if base_t > 0 else 0

        output.extend([
            f"Entity: {central_node_id} ({label})",
            f"Author Agent: {author} | Last Modified By: {last_mod}",
            f"Effective Trust: {eff_t:.2f} (Base: {base_t:.2f}, {pct_decay}% decay over {half_life_days}d half-life)",
            f"Status: {status} | Created: {created_at} | Last Verified: {last_verified_at} | Last Updated: {updated_at}",
        ])

        if signature:
            output.append(f"Signature: {signature}")
        if start_line and end_line:
            output.append(f"Line Range: L{start_line}-L{end_line}")
        if docstring:
            output.append(f"Docstring: {docstring}")
        if rationale:
            output.append(f"Rationale: {rationale}")
        if intent:
            output.append(f"Design Intent: {intent}")

        output.append(f"Metadata: {json.dumps(props, indent=2)}")

        if history:
            output.append("Decision History:")
            for h in history[-5:]:
                ts = h.get("timestamp", "")
                ag = h.get("agent", "Agent")
                rat = h.get("rationale") or h.get("action", "")
                output.append(f"  • [{ts}] ({ag}): {rat}")

        if snippet:
            output.append(f"Code Snippet Preview:\n```\n{snippet}\n```")

        output.append("Relationships:")
        
        edges = conn.execute("""
            SELECT relation_type, target_id, properties, created_at, last_verified_at, trust_score 
            FROM Edges 
            WHERE source_id = ?
        """, (central_node_id,)).fetchall()
        
        valid_edges = []
        for rel_type, target, e_props, c_at, v_at, e_trust in edges:
            e_eff_t = calculate_effective_trust(e_trust or 1.0, v_at, half_life_days)
            if e_eff_t >= min_trust:
                valid_edges.append((rel_type, target, e_props, c_at, v_at, e_eff_t))
                
        if not valid_edges:
            output.append("  (None)")
        else:
            for rel_type, target, e_props, c_at, v_at, e_eff_t in valid_edges:
                output.append(f"  -[{rel_type}]-> {target} (Effective Trust: {e_eff_t:.2f}, Context: {e_props}, Created: {c_at}, Verified: {v_at})")
                
        # Also show incoming edges
        incoming_edges = conn.execute("""
            SELECT source_id, relation_type, properties, created_at, last_verified_at, trust_score 
            FROM Edges 
            WHERE target_id = ?
        """, (central_node_id,)).fetchall()
        
        valid_incoming = []
        for source, rel_type, e_props, c_at, v_at, e_trust in incoming_edges:
            e_eff_t = calculate_effective_trust(e_trust or 1.0, v_at, half_life_days)
            if e_eff_t >= min_trust:
                valid_incoming.append((source, rel_type, e_props, c_at, v_at, e_eff_t))
        
        if valid_incoming:
            output.append("Incoming Relationships:")
            for source, rel_type, e_props, c_at, v_at, e_eff_t in valid_incoming:
                output.append(f"  {source} -[{rel_type}]-> (this) (Effective Trust: {e_eff_t:.2f}, Context: {e_props}, Created: {c_at}, Verified: {v_at})")
                
        return "\n".join(output)

# ---------------------------------------------------------------------------
# Seed Memory, Graph Hygiene & Maintenance (Understory Upgrades)
# ---------------------------------------------------------------------------

def get_seed_memory(db_path: str, max_items: int = 10) -> str:
    """
    Solves AI cold-start amnesia by summarizing top-level memory hubs and active entities.
    Returns a compact summary string intended for MCP tool descriptions / initialization.
    """
    if not os.path.exists(db_path):
        return "Knowledge graph is currently empty."
        
    with get_connection(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM Nodes WHERE is_deleted = 0 AND status = 'active'").fetchone()[0]
        if count == 0:
            return "Knowledge graph is empty (0 active nodes)."
            
        rows = conn.execute("""
            SELECT id, label, properties FROM Nodes 
            WHERE is_deleted = 0 AND status = 'active'
            ORDER BY access_count DESC, updated_at DESC LIMIT ?
        """, (max_items,)).fetchall()
        
        items = []
        for r_id, r_label, r_props in rows:
            props = json.loads(r_props) if r_props else {}
            entity_type = props.get("entity_type") or r_label
            items.append(f"{r_id} ({entity_type})")
            
        return f"Active Graph Memory Context ({count} total nodes). Key Hubs: " + ", ".join(items)

def lint_graph(db_path: str, fix: bool = False) -> dict:
    """
    Performs deterministic graph hygiene checks:
    - Finds orphan nodes (no incoming or outgoing edges)
    - Finds dangling edges (source or target node deleted/missing)
    If fix=True, removes dangling edges and soft-deletes orphan nodes.
    """
    init_db(db_path)
    results = {
        "orphans": [],
        "dangling_edges": [],
        "fixed_orphans": 0,
        "fixed_edges": 0
    }
    
    with get_connection(db_path) as conn:
        # 1. Detect Orphan Nodes
        orphan_rows = conn.execute("""
            SELECT id, label FROM Nodes 
            WHERE is_deleted = 0 AND status = 'active'
            AND id NOT IN (SELECT source_id FROM Edges UNION SELECT target_id FROM Edges)
        """).fetchall()
        results["orphans"] = [{"id": r[0], "label": r[1]} for r in orphan_rows]
        
        # 2. Detect Dangling Edges
        dangling_rows = conn.execute("""
            SELECT source_id, target_id, relation_type FROM Edges
            WHERE source_id NOT IN (SELECT id FROM Nodes WHERE is_deleted = 0)
               OR target_id NOT IN (SELECT id FROM Nodes WHERE is_deleted = 0)
        """).fetchall()
        results["dangling_edges"] = [{"source": r[0], "target": r[1], "relation": r[2]} for r in dangling_rows]
        
        # 3. Apply fixes if requested
        if fix:
            with write_transaction(conn):
                if results["dangling_edges"]:
                    conn.execute("""
                        DELETE FROM Edges
                        WHERE source_id NOT IN (SELECT id FROM Nodes WHERE is_deleted = 0)
                           OR target_id NOT IN (SELECT id FROM Nodes WHERE is_deleted = 0)
                    """)
                    results["fixed_edges"] = len(results["dangling_edges"])
                    
                if results["orphans"]:
                    for orphan in results["orphans"]:
                        conn.execute("UPDATE Nodes SET is_deleted = 1, updated_at = ? WHERE id = ?", (now_iso(), orphan["id"]))
                    results["fixed_orphans"] = len(results["orphans"])
                    
    return results

def consolidate_graph(db_path: str) -> dict:
    """
    Performs database housekeeping ("Dreaming"):
    - Cleans dangling edges
    - Reclaims SQLite disk space via PRAGMA incremental_vacuum
    """
    init_db(db_path)
    stats = {"cleaned_edges": 0, "vacuumed": True}
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            cursor = conn.execute("""
                DELETE FROM Edges 
                WHERE source_id NOT IN (SELECT id FROM Nodes WHERE is_deleted = 0) 
                   OR target_id NOT IN (SELECT id FROM Nodes WHERE is_deleted = 0)
            """)
            stats["cleaned_edges"] = cursor.rowcount
            conn.execute("PRAGMA incremental_vacuum;")
    return stats

def resolve_canonical_id(db_path: str, node_id: str, max_depth: int = 10) -> str:
    """
    Recursively follows 'merged_into' pointers with a visited set and depth cap
    to resolve to the active canonical node ID.
    """
    if not db_path:
        return node_id
    init_db(db_path)
        
    visited = set()
    curr_id = node_id
    
    with get_connection(db_path) as conn:
        while curr_id and curr_id not in visited and len(visited) < max_depth:
            visited.add(curr_id)
            row = conn.execute("SELECT is_deleted, status, properties FROM Nodes WHERE id = ?", (curr_id,)).fetchone()
            if not row:
                break
            is_deleted, status, props_json = row
            if is_deleted == 1 and status == 'merged':
                props = json.loads(props_json) if props_json else {}
                target = props.get("merged_into")
                if target:
                    curr_id = target
                else:
                    break
            else:
                break
                
    return curr_id

def merge_nodes(db_path: str, source_id: str, target_id: str) -> dict:
    """
    Safely merges source_id into target_id:
    1. Resolves canonical targets.
    2. Combines observations & metadata, recording source_id in target_id's 'aliases' list.
    3. Prevents self-loops by removing direct edges between source_id and target_id.
    4. Rewires all incoming/outgoing edges using ON CONFLICT to prevent UNIQUE constraint crashes.
    5. Soft-deletes source_id with is_deleted=1, status='merged', merged_into=target_id.
    6. Reclaims SQLite disk space via PRAGMA incremental_vacuum.
    """
    init_db(db_path)
    
    if source_id == target_id:
        return {"status": "error", "message": "Cannot merge a node into itself."}
        
    canon_source = resolve_canonical_id(db_path, source_id)
    canon_target = resolve_canonical_id(db_path, target_id)
    
    if canon_source == canon_target:
        return {"status": "error", "message": "Source and Target already resolve to the same canonical entity."}
        
    with get_connection(db_path) as conn:
        with write_transaction(conn):
            s_row = conn.execute("SELECT label, properties FROM Nodes WHERE id = ? AND is_deleted = 0", (canon_source,)).fetchone()
            t_row = conn.execute("SELECT label, properties FROM Nodes WHERE id = ? AND is_deleted = 0", (canon_target,)).fetchone()
            
            if not s_row:
                return {"status": "error", "message": f"Source node '{canon_source}' not found or deleted."}
            if not t_row:
                return {"status": "error", "message": f"Target node '{canon_target}' not found or deleted."}
                
            s_props = json.loads(s_row[1]) if s_row[1] else {}
            t_props = json.loads(t_row[1]) if t_row[1] else {}
            
            # Combine observations
            s_obs = s_props.get("observations", [])
            t_obs = t_props.get("observations", [])
            combined_obs = list(dict.fromkeys(t_obs + s_obs)) # Deduplicate preserving order
            
            # Combine aliases
            aliases = t_props.get("aliases", [])
            if canon_source not in aliases:
                aliases.append(canon_source)
            s_aliases = s_props.get("aliases", [])
            for sa in s_aliases:
                if sa not in aliases:
                    aliases.append(sa)
                    
            t_props.update(s_props)
            t_props["observations"] = combined_obs
            t_props["aliases"] = aliases
            
            # Update target node properties
            conn.execute("""
                UPDATE Nodes 
                SET properties = ?, updated_at = ?, last_verified_at = ?, access_count = access_count + 1
                WHERE id = ?
            """, (json.dumps(t_props), now_iso(), now_iso(), canon_target))
            
            # 1. Remove direct edges between source and target (prevents self-loops)
            conn.execute("DELETE FROM Edges WHERE (source_id = ? AND target_id = ?) OR (source_id = ? AND target_id = ?)", 
                         (canon_source, canon_target, canon_target, canon_source))
                         
            # 2. Rewire Outgoing Edges: source_id -> X => target_id -> X
            outgoing_edges = conn.execute("SELECT target_id, relation_type, properties, trust_score, verification_method FROM Edges WHERE source_id = ?", (canon_source,)).fetchall()
            for tgt, rel_type, e_props, trust, v_method in outgoing_edges:
                if tgt != canon_target:
                    conn.execute("""
                        INSERT INTO Edges (source_id, target_id, relation_type, properties, created_at, last_verified_at, trust_score, verification_method)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                            trust_score = MAX(trust_score, excluded.trust_score),
                            last_verified_at = excluded.last_verified_at
                    """, (canon_target, tgt, rel_type, e_props, now_iso(), now_iso(), trust, v_method))
            conn.execute("DELETE FROM Edges WHERE source_id = ?", (canon_source,))
            
            # 3. Rewire Incoming Edges: X -> source_id => X -> target_id
            incoming_edges = conn.execute("SELECT source_id, relation_type, properties, trust_score, verification_method FROM Edges WHERE target_id = ?", (canon_source,)).fetchall()
            for src, rel_type, e_props, trust, v_method in incoming_edges:
                if src != canon_target:
                    conn.execute("""
                        INSERT INTO Edges (source_id, target_id, relation_type, properties, created_at, last_verified_at, trust_score, verification_method)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                            trust_score = MAX(trust_score, excluded.trust_score),
                            last_verified_at = excluded.last_verified_at
                    """, (src, canon_target, rel_type, e_props, now_iso(), now_iso(), trust, v_method))
            conn.execute("DELETE FROM Edges WHERE target_id = ?", (canon_source,))
            
            # 4. Soft-delete source_id with merged status
            s_props["merged_into"] = canon_target
            conn.execute("""
                UPDATE Nodes 
                SET is_deleted = 1, status = 'merged', properties = ?, updated_at = ?
                WHERE id = ?
            """, (json.dumps(s_props), now_iso(), canon_source))
            
            # 5. Vacuum
            conn.execute("PRAGMA incremental_vacuum;")
            
    return {"status": "success", "source": canon_source, "target": canon_target}
