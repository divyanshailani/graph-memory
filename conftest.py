# Root conftest: ensures the project root stays on sys.path when tests live in tests/.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
