"""Real Git worktrees prove upgrades preserve product work and prior locks."""
from pathlib import Path
from dataclasses import replace
import pytest
from conftest import commit,git

@pytest.fixture
def target_kit(kit):
    (kit/'core/entry.md').write_text((kit/'core/entry.md').read_text()+'\nНовая версия процесса.\n')
    commit(kit,'next kit')
    return kit

def test_upgrade_keeps_project_edits(ready_project,target_kit):
    from project_kit.upgrade import prepare_upgrade
    (ready_project/'README.md').write_bytes(b'Product README\r\n')
    decision=ready_project/'docs/decisions/0001-stack.md';decision.write_text('Accepted local stack decision\n')
    with (ready_project/'AGENTS.md').open('a') as f:f.write('\nLocal convention.\n')
    commit(ready_project)
    original=(ready_project/'project-kit.lock.yaml').read_bytes()
    report=prepare_upgrade(ready_project,target_kit)
    assert report.status=='ready',report
    worktree=Path(report.project)
    assert worktree!=ready_project and (worktree/'README.md').read_bytes()==b'Product README\r\n'
    assert (worktree/'docs/decisions/0001-stack.md').read_text()=='Accepted local stack decision\n'
    assert (worktree/'AGENTS.md').read_text().endswith('Local convention.\n')
    assert (ready_project/'project-kit.lock.yaml').read_bytes()==original
    assert git(ready_project,'branch','--show-current')=='main'

def test_modified_managed_block_conflicts(ready_project,target_kit):
    from project_kit.upgrade import prepare_upgrade
    path=ready_project/'AGENTS.md'; original=path.read_text().replace('Начни','Моя версия: начни');path.write_text(original)
    commit(ready_project)
    report=prepare_upgrade(ready_project,target_kit)
    assert report.status=='drift'
    assert (Path(report.project)/'AGENTS.md').read_text()==original

def test_dirty_worktree_preserved(ready_project,target_kit):
    from project_kit.upgrade import prepare_upgrade
    commit(ready_project)
    (ready_project/'README.md').write_bytes(b'Uncommitted work')
    report=prepare_upgrade(ready_project,target_kit)
    assert report.status=='incomplete'
    assert (ready_project/'README.md').read_bytes()==b'Uncommitted work'
    assert report.project==str(ready_project)

def test_failed_runtime_keeps_old_lock(ready_project,target_kit,ready_clients,monkeypatch):
    from project_kit.upgrade import prepare_upgrade
    commit(ready_project)
    original=(ready_project/'project-kit.lock.yaml').read_bytes()
    monkeypatch.setattr(ready_clients,'runtime',lambda *args:{'packages':[],'errors':[]})
    report=prepare_upgrade(ready_project,target_kit)
    assert report.status=='incomplete'
    assert (Path(report.project)/'project-kit.lock.yaml').read_bytes()==original
    assert (ready_project/'project-kit.lock.yaml').read_bytes()==original

def test_rerun_upgrade_resumes(ready_project,target_kit):
    from project_kit.upgrade import prepare_upgrade
    commit(ready_project)
    first=prepare_upgrade(ready_project,target_kit)
    second=prepare_upgrade(ready_project,target_kit)
    assert first.status==second.status=='ready'
    assert second.project==first.project and second.files==()

def test_other_project_unaffected(ready_project,target_kit,bundle,intent_data,ready_clients,tmp_path):
    from project_kit.init import initialize
    from project_kit.config import intent_from_data
    from project_kit.upgrade import prepare_upgrade
    other=tmp_path/'other'; initialize(other,intent_from_data(intent_data),bundle)
    original=(other/'.codex/config.toml').read_bytes()
    original_lock=(other/'project-kit.lock.yaml').read_bytes()
    commit(ready_project)
    assert prepare_upgrade(ready_project,target_kit).status=='ready'
    assert (other/'.codex/config.toml').read_bytes()==original
    assert (other/'project-kit.lock.yaml').read_bytes()==original_lock

def test_init_reports_pending_upgrade(ready_project,target_kit):
    from project_kit.upgrade import prepare_upgrade
    from project_kit.init import restore
    commit(ready_project)
    prepare_upgrade(ready_project,target_kit)
    result=restore(ready_project)
    assert result.status=='incompatible'

def test_restore_after_merge_completes_upgrade(ready_project,target_kit):
    from project_kit.upgrade import prepare_upgrade
    from project_kit.init import restore
    commit(ready_project)
    report=prepare_upgrade(ready_project,target_kit)
    worktree=Path(report.project); commit(worktree,'apply kit upgrade')
    git(ready_project,'merge','--ff-only',git(worktree,'branch','--show-current'))
    restored=restore(ready_project)
    assert restored.status=='ready',restored
    assert not (ready_project/'.project-kit/operation.json').exists()

def test_upgrade_preserves_foreign_catalog_identity(ready_project,target_kit):
    import json
    from project_kit.check import check_project
    from project_kit.upgrade import prepare_upgrade
    from project_kit.init import restore
    catalog=ready_project/'.agents/plugins/marketplace.json'
    data=json.loads(catalog.read_text())
    namespace=data['name']
    foreign={'name':'foreign','source':{'source':'local','path':'./foreign'}}
    data['plugins'].append(foreign)
    data['interface']['custom']='Project-owned metadata'
    catalog.write_text(json.dumps(data))
    with (ready_project/'.codex/config.toml').open('a') as stream:
        stream.write(f'\n[plugins."foreign@{namespace}"]\nenabled = true\n')
    commit(ready_project)
    assert check_project(ready_project,True).status=='ready'
    report=prepare_upgrade(ready_project,target_kit)
    assert report.status=='ready',report
    worktree=Path(report.project)
    after=json.loads((worktree/'.agents/plugins/marketplace.json').read_text())
    assert after['name']==namespace
    assert foreign in after['plugins']
    assert after['interface']['custom']=='Project-owned metadata'
    assert f'foreign@{namespace}' in (worktree/'.codex/config.toml').read_text()
    commit(worktree,'apply upgrade')
    git(ready_project,'merge','--ff-only',git(worktree,'branch','--show-current'))
    restored=restore(ready_project)
    assert restored.status=='ready',restored
