"""Real temporary repositories; fake native processes are defined in adapter tests."""
from pathlib import Path
import json
import subprocess
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(autouse=True)
def no_live_clients(monkeypatch):
    from project_kit.adapters import native
    def unavailable(*args, **kwargs):
        raise FileNotFoundError('Native clients are exercised separately from offline tests')
    monkeypatch.setattr(native, 'run', unavailable)

def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True).stdout.strip()

def commit(root, message='fixture'):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', message)
    return git(root, 'rev-parse', 'HEAD')

@pytest.fixture
def intent_data():
    return dict(name='CSV', goal='Count CSV records', users=['Analyst'], scope='One local CSV; no network',
                constraints=['UTF-8'], decisions=['Python: csv handles quoted records'], success=['Two rows produce 2'],
                task_source='GitHub Issues', commands={'test':['python','app.py','input.csv']}, generation=[])

@pytest.fixture
def kit(tmp_path):
    import shutil
    root=tmp_path/'kit'
    root.mkdir()
    git(root,'init','-q','-b','main')
    for directory in ('core','templates','skills'):
        shutil.copytree(ROOT/directory, root/directory)
    for agent in ('codex','claude'):
        directory=root/f'.{agent}-plugin'
        directory.mkdir()
        (directory/'plugin.json').write_text(json.dumps({'name':'project-kit','version':'0.1.0','skills':'./skills/'}))
    (root/'profiles').mkdir()
    (root/'profiles/default.yaml').write_text(yaml.safe_dump(dict(schema=1, packages=['project-kit'],
        agents=['codex','claude-code'], workflows={}, hooks=False, mcp=False)))
    commit(root)
    return root

@pytest.fixture
def config():
    from project_kit.models import KitConfig
    return KitConfig(1,'default',('codex','claude-code'),{})

@pytest.fixture
def bundle(kit,config,tmp_path):
    from project_kit.sources import prepare_bundle
    return prepare_bundle(kit,config,tmp_path/'cache')
