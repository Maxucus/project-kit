"""Initialization preserves product files and never replays a completed generator."""
from dataclasses import replace
import json
import sys
import pytest

@pytest.fixture
def intent(intent_data):
    from project_kit.config import intent_from_data
    return intent_from_data(intent_data)

def test_init_preserves_readme(tmp_path,intent,bundle):
    from project_kit.init import initialize
    root=tmp_path/'project'; root.mkdir()
    (root/'README.md').write_bytes(b'My product\r\n')
    report=initialize(root,intent,bundle)
    assert (root/'README.md').read_bytes()==b'My product\r\n'
    assert (root/'docs/project.md').is_file()
    assert report.status=='incomplete'

def test_repeat_init_has_no_diff(tmp_path,intent,bundle):
    from project_kit.init import initialize
    root=tmp_path/'project'
    initialize(root,intent,bundle)
    assert initialize(root,intent,bundle).files==()

def test_unicode_space_path(tmp_path,intent,bundle):
    from project_kit.init import initialize
    root=tmp_path/'проект с пробелом'
    report=initialize(root,intent,bundle)
    assert report.project==str(root.resolve())
    assert (root/'AGENTS.md').exists()

def test_partial_write_keeps_lock(tmp_path,intent,bundle,monkeypatch):
    import project_kit.init as init
    root=tmp_path/'project'; (root/'.project-kit').mkdir(parents=True)
    lock=root/'project-kit.lock.yaml'; lock.write_bytes(b'applied-old-state')
    original=init.write_atomic
    def fail(path,data):
        if path.name=='AGENTS.md': raise OSError('write failure')
        original(path,data)
    monkeypatch.setattr(init,'write_atomic',fail)
    report=init.initialize(root,intent,bundle)
    assert report.status=='incomplete'
    assert lock.read_bytes()==b'applied-old-state'

def test_completed_generator_not_repeated(tmp_path,intent,bundle):
    from project_kit.init import initialize
    root=tmp_path/'project'
    code="from pathlib import Path; p=Path('runs'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"
    intent=replace(intent,generation=((sys.executable,'-c',code),))
    initialize(root,intent,bundle); initialize(root,intent,bundle)
    assert (root/'runs').read_text()=='1'

def test_preflight_symlink_leaves_project_untouched(tmp_path,intent,bundle):
    from project_kit.init import initialize
    root=tmp_path/'project'; root.mkdir()
    outside=tmp_path/'outside'; outside.mkdir()
    (root/'docs').symlink_to(outside,target_is_directory=True)
    report=initialize(root,intent,bundle)
    assert report.status!='ready'
    assert not (root/'AGENTS.md').exists()
    assert not list(outside.iterdir())

def test_changed_pending_intent_does_not_overwrite(tmp_path,intent,bundle):
    from project_kit.init import initialize
    root=tmp_path/'project'
    initialize(root,intent,bundle)
    report=initialize(root,replace(intent,goal='Different goal'),bundle)
    assert report.status=='incompatible'
    assert 'Count CSV records' in (root/'docs/project.md').read_text()

def test_restore_uses_lock_without_regenerating(tmp_path,intent,bundle):
    from project_kit.init import initialize, restore, make_lock, render_project
    from dataclasses import asdict
    import yaml
    root=tmp_path/'project'
    initialize(root,intent,bundle)
    (root/'project-kit.lock.yaml').write_text(yaml.safe_dump(asdict(make_lock(intent,bundle,render_project(intent,bundle)))))
    (root/'.project-kit/operation.json').unlink()
    (root/'README.md').write_text('Local README')
    report=restore(root)
    assert report.status=='incomplete'
    assert (root/'README.md').read_text()=='Local README'
    assert (root/'.project-kit/operation.json').is_file()
