"""An offline stand-in for a project's chosen scaffold command."""
from pathlib import Path
import shutil
import sys

for source in Path(sys.argv[1]).iterdir():
    target = Path.cwd() / source.name
    if target.exists():
        raise SystemExit(f'Refusing to overwrite {source.name}')
    shutil.copy2(source, target)
