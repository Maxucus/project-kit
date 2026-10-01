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
    monkeypatch.setattr(native, 'runtime', unavailable)

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

@pytest.fixture
def ready_clients(monkeypatch):
    from project_kit.adapters import native
    monkeypatch.setattr(native,'version',lambda *args:'fixture-client-1')
    monkeypatch.setattr(native,'inventory',lambda *args:[])
    def observed(agent,project):
        if agent=='codex':
            catalogs=[(project,json.loads((project/'.agents/plugins/marketplace.json').read_text()))]
            enabled=None
        else:
            settings=json.loads((project/'.claude/settings.local.json').read_text())
            enabled=json.loads((project/'.claude/settings.json').read_text())['enabledPlugins']
            catalogs=[]
            for entry in settings['extraKnownMarketplaces'].values():
                base=Path(entry['source']['path'])
                catalogs.append((base,json.loads((base/'.claude-plugin/marketplace.json').read_text())))
        packages=[]
        for base,market in catalogs:
            for entry in market['plugins']:
                identifier=entry['name']+'@'+market['name']
                if enabled is not None and not enabled.get(identifier):continue
                source=entry['source']
                root=base/(source['path'] if isinstance(source,dict) else source)
                packages.append({'id':identifier,'name':entry['name'],'enabled':True,
                                 'root':str(root),'skills':[str(p) for p in (root/'skills').glob('*/SKILL.md')],
                                 'hooks':[],'mcp':[]})
        return {'packages':packages,'errors':[]}
    monkeypatch.setattr(native,'runtime',observed)
    return native

@pytest.fixture
def ready_project(tmp_path,intent_data,bundle,ready_clients):
    from project_kit.init import initialize
    from project_kit.config import intent_from_data
    root=tmp_path/'project'
    report=initialize(root,intent_from_data(intent_data),bundle)
    assert report.status=='ready',report
    return root
