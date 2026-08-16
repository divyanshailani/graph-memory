# Conftest: ensures the project root stays on sys.path so the local
# graph_memory package (editable source) takes priority over any
# pip-installed copy in site-packages.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
