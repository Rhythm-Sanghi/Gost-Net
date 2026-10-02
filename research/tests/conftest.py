import sys
import os

research_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_dir = os.path.join(os.path.dirname(research_dir), 'src')

if research_dir not in sys.path:
    sys.path.insert(0, research_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
