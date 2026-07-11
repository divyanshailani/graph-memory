import tree_sitter
import tree_sitter_python
from tree_sitter import Language, Parser
lang = Language(tree_sitter_python.language())
parser = Parser(lang)
tree = parser.parse(b"def foo():\n    pass")
print(tree.root_node)
