import sqlite3
import json
import os

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

def add_node(node_id, node_type, attributes=None):
    if attributes is None:
        attributes = {}
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO nodes (id, type, attributes)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET type=excluded.type, attributes=excluded.attributes
    ''', (node_id, node_type, json.dumps(attributes)))
    conn.commit()
    conn.close()

def add_relation(source_id, relation_type, target_id, attributes=None):
    if attributes is None:
        attributes = {}
    conn = get_connection()
    cursor = conn.cursor()
    
    # Ensure source and target nodes exist minimally
    cursor.execute('INSERT OR IGNORE INTO nodes (id, type, attributes) VALUES (?, ?, ?)', (source_id, 'Unknown', '{}'))
    cursor.execute('INSERT OR IGNORE INTO nodes (id, type, attributes) VALUES (?, ?, ?)', (target_id, 'Unknown', '{}'))
    
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
