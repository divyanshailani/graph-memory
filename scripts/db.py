import sqlite3
import json
import os
from datetime import datetime, timezone

VERIFICATION_METHODS = {'source_read', 'test_executed', 'endpoint_tested', 'agent_self_report', 'assumed'}
STRONG_METHODS = {'source_read', 'test_executed', 'endpoint_tested'}

def get_db_path():
    # Store the DB in the .agents directory of the current workspace
    workspace_dir = os.environ.get("GRAPH_MEMORY_WORKSPACE", os.getcwd())
    agents_dir = os.path.join(workspace_dir, '.agents')
    os.makedirs(agents_dir, exist_ok=True)
    return os.path.join(agents_dir, 'graph_memory.sqlite')

def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            attributes TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id TEXT NOT NULL,
            target_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            attributes TEXT,
            FOREIGN KEY(source_id) REFERENCES nodes(id),
            FOREIGN KEY(target_id) REFERENCES nodes(id)
        )
    ''')
    conn.commit()
    conn.close()

def add_node(node_id, node_type, verification_method, attributes=None):
    if verification_method not in VERIFICATION_METHODS:
        raise ValueError(f"Invalid verification_method: {verification_method}. Must be one of: {VERIFICATION_METHODS}")
        
    if attributes is None:
        attributes = {}
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch existing node to preserve created_at
    cursor.execute('SELECT attributes FROM nodes WHERE id = ?', (node_id,))
    row = cursor.fetchone()
    
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if row:
        try:
            existing_attrs = json.loads(row['attributes'])
        except:
            existing_attrs = {}
            
        attributes['created_at'] = existing_attrs.get('created_at', now_iso)
        if verification_method in STRONG_METHODS:
            attributes['last_verified_at'] = now_iso
        else:
            if 'last_verified_at' in existing_attrs:
                attributes['last_verified_at'] = existing_attrs['last_verified_at']
    else:
        attributes['created_at'] = now_iso
        if verification_method in STRONG_METHODS:
            attributes['last_verified_at'] = now_iso
            
    attributes['verification_method'] = verification_method
            
    cursor.execute('''
        INSERT INTO nodes (id, type, attributes)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET type=excluded.type, attributes=excluded.attributes
    ''', (node_id, node_type, json.dumps(attributes)))
    conn.commit()
    conn.close()

def add_relation(source_id, relation_type, target_id, verification_method, attributes=None):
    if verification_method not in VERIFICATION_METHODS:
        raise ValueError(f"Invalid verification_method: {verification_method}. Must be one of: {VERIFICATION_METHODS}")
        
    if attributes is None:
        attributes = {}
        
    now_iso = datetime.now(timezone.utc).isoformat()
    attributes['created_at'] = now_iso
    if verification_method in STRONG_METHODS:
        attributes['last_verified_at'] = now_iso
    attributes['verification_method'] = verification_method
        
    conn = get_connection()
    cursor = conn.cursor()
    
    now_iso = datetime.now(timezone.utc).isoformat()
    dummy_attrs = json.dumps({"verification_method": "assumed", "created_at": now_iso})
    cursor.execute('INSERT OR IGNORE INTO nodes (id, type, attributes) VALUES (?, ?, ?)', (source_id, 'Unknown', dummy_attrs))
    cursor.execute('INSERT OR IGNORE INTO nodes (id, type, attributes) VALUES (?, ?, ?)', (target_id, 'Unknown', dummy_attrs))
    
    cursor.execute('''
        INSERT INTO relations (source_id, relation_type, target_id, attributes)
        VALUES (?, ?, ?, ?)
    ''', (source_id, relation_type, target_id, json.dumps(attributes)))
    conn.commit()
    conn.close()

def get_node(node_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM nodes WHERE id = ?', (node_id,))
    node = cursor.fetchone()
    if not node:
        conn.close()
        return None
        
    cursor.execute('SELECT * FROM relations WHERE source_id = ? OR target_id = ?', (node_id, node_id))
    relations = cursor.fetchall()
    conn.close()
    
    return {
        'node': dict(node),
        'relations': [dict(r) for r in relations]
    }

def get_all_nodes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM nodes')
    nodes = cursor.fetchall()
    conn.close()
    return [dict(n) for n in nodes]

def get_all_relations():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM relations')
    relations = cursor.fetchall()
    conn.close()
    return [dict(r) for r in relations]
