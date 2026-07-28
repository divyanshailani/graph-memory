import tree_sitter
import tree_sitter_python
from tree_sitter import Language, Parser, Query, QueryCursor

lang = Language(tree_sitter_python.language())
parser = Parser(lang)
tree = parser.parse(b"import os\nfrom datetime import datetime\ndef foo(): pass\nclass Bar: pass")

query = Query(lang, """
(import_statement (dotted_name) @import)
(import_from_statement module_name: (dotted_name) @import)
(function_definition name: (identifier) @func)
(class_definition name: (identifier) @class)
""")
cursor = QueryCursor(query)
matches = cursor.captures(tree.root_node)
for capture_name, nodes in matches.items():
    for node in nodes:
        print(f"{capture_name}: {node.text.decode('utf8')}")
