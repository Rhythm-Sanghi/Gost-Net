import sys
import os

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_dir = os.path.join(root_dir, 'src')
research_dir = os.path.join(root_dir, 'research')

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if research_dir not in sys.path:
    sys.path.insert(0, research_dir)

os.environ["GOSTNET_TEST_MODE"] = "1"

