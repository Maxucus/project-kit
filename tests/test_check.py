"""No false ready from stale observations, missing context, or matching version labels."""
from dataclasses import replace
import json
from pathlib import Path
from datetime import datetime,timezone
import pytest

def test_status_precedence():
    from project_kit.check import aggregate
    from project_kit.models import Check
    assert aggregate([Check('a','drift',''),Check('b','incompatible','')])=='incompatible'
    assert aggregate([])=='incomplete'
    assert aggregate([Check('a','ready',''),Check('b','incomplete','')])=='incomplete'

def test_candidate_checked_before_lock_written(tmp_path,intent_data,bundle,ready_clients,monkeypatch):
    import project_kit.check as check
    from project_kit.init import initialize
    from project_kit.config import intent_from_data
    root=tmp_path/'project'; original=check.check_project
    calls=[]
    def inspect(project,runtime,expected=None):
        calls.append(expected)
        assert expected is not None
        assert not (root/'project-kit.lock.yaml').exists()
        return original(project,runtime,expected)
    monkeypatch.setattr(check,'check_project',inspect)
    result=initialize(root,intent_from_data(intent_data),bundle)
    assert result.status=='ready' and calls
    assert (root/'project-kit.lock.yaml').exists()

def test_same_version_wrong_digest_is_drift(ready_project):
    from project_kit.check import check_project
    catalog=json.loads((ready_project/'.agents/plugins/marketplace.json').read_text())
    root=ready_project/catalog['plugins'][0]['source']['path']
    (root/'core/entry.md').write_text('changed payload')
    assert check_project(ready_project,True).status=='drift'

def test_stale_observation_incomplete(ready_project,monkeypatch):
    from project_kit.adapters import codex,Observation
    from project_kit.models import Check
    from project_kit.check import check_project
    observation=Observation('/old/project','codex','old','old',{},(),{},datetime.now(timezone.utc).isoformat())
    monkeypatch.setattr(codex,'observe',lambda *args:(Check('agent:codex','ready',''),observation))
    assert check_project(ready_project,True).status=='incomplete'

def test_broken_context_link(ready_project):
    from project_kit.check import check_project
    with (ready_project/'docs/project.md').open('a') as f:f.write('\n[Missing](absent.md)\n')
    assert check_project(ready_project,True).status=='incomplete'

def test_required_context_missing(ready_project):
    from project_kit.check import check_project
    (ready_project/'docs/project.md').unlink()
    assert check_project(ready_project,True).status=='incomplete'

def test_check_without_runtime_is_read_only_and_incomplete(ready_project):
    from project_kit.check import check_project
    before={str(p):p.read_bytes() for p in ready_project.rglob('*') if p.is_file()}
    assert check_project(ready_project,False).status=='incomplete'
    assert {str(p):p.read_bytes() for p in ready_project.rglob('*') if p.is_file()}==before

def test_project_additions_are_not_managed_drift(ready_project):
    from project_kit.check import check_project
    with (ready_project/'AGENTS.md').open('a') as f:f.write('\nA project-specific addition.\n')
    with (ready_project/'.codex/config.toml').open('a') as f:f.write('\n[personal]\nkeep = true\n')
    assert check_project(ready_project,True).status=='ready'

def test_repeat_ready_init_never_repeats_generation(ready_project,bundle,intent_data):
    from project_kit.init import initialize
    from project_kit.config import intent_from_data
    original=(ready_project/'project-kit.lock.yaml').read_bytes()
    report=initialize(ready_project,intent_from_data(intent_data),bundle)
    assert report.status=='ready' and report.files==()
    assert (ready_project/'project-kit.lock.yaml').read_bytes()==original

def test_cli_check_json_and_exit(ready_project,capsys):
    from project_kit.cli import main
    assert main(['check','--project',str(ready_project),'--json'])==1
    output=json.loads(capsys.readouterr().out)
    assert output['project']==str(ready_project) and output['status']=='incomplete'
    assert main(['check','--project',str(ready_project),'--runtime','--json'])==0

def test_declared_hook_cannot_disappear_from_native_observation(tmp_path,bundle,ready_clients,monkeypatch):
    from project_kit.adapters import codex,marketplace_name
    from project_kit.sources import digest_tree
    package=bundle.packages[0]
    manifest=package.root/'.codex-plugin/plugin.json'
    data=json.loads(manifest.read_text()); data['hooks']={'SessionStart':[{'hooks':[{'type':'command','command':'echo ok'}]}]}
    manifest.write_text(json.dumps(data))
    changed=replace(bundle,profile={**bundle.profile,'hooks':'native'},packages=(replace(package,digest=digest_tree(package.root)),))
    snapshot={'packages':[{'id':'project-kit@'+marketplace_name(changed),'name':'project-kit','enabled':True,
                          'root':str(package.root),'skills':[str(p) for p in (package.root/'skills').glob('*/SKILL.md')],
                          'hooks':[],'mcp':[]}],'errors':[]}
    monkeypatch.setattr(ready_clients,'runtime',lambda *args:snapshot)
    check,_=codex.observe(tmp_path,changed,True)
    assert check.status=='incomplete'
