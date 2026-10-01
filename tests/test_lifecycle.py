"""Two application stacks through the public CLI, with bounded local servers."""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import urllib.request
import pytest
import yaml
from conftest import ROOT,commit,git

@pytest.mark.parametrize('kind',['cli','web-api'])
def test_lifecycle(kind,tmp_path,kit,ready_clients,capsys):
    from project_kit.cli import main
    fixture=ROOT/'tests/fixtures'/kind
    intent=yaml.safe_load((fixture/'brief.yaml').read_text())
    intent['generation']=[[sys.executable,str(ROOT/'tests/fixtures/materialize.py'),str(fixture/'starter')]]
    intent_path=tmp_path/'intent.yaml';intent_path.write_text(yaml.safe_dump(intent))
    config=tmp_path/'config.yaml';config.write_text('schema: 1\nprofile: default\nagents: [codex, claude-code]\noverrides: {}\n')
    project=tmp_path/'созданный проект'
    assert main(['init','--project',str(project),'--kit',str(kit),'--intent',str(intent_path),'--config',str(config),'--json'])==0
    first=json.loads(capsys.readouterr().out)
    entry='app.py' if kind=='cli' else 'server.mjs'
    assert entry in first['files']
    assert main(['init','--project',str(project),'--json'])==0
    assert json.loads(capsys.readouterr().out)['files']==[]
    initial=yaml.safe_load((project/'project-kit.lock.yaml').read_text())
    if kind=='cli':
        csv=project/'input with spaces.csv';csv.write_text('name,value\n"first\nrecord",1\nsecond,2\n')
        result=subprocess.run([sys.executable,'app.py',str(csv)],cwd=project,text=True,capture_output=True)
        assert result.returncode==0 and result.stdout.strip()=='2'
        assert subprocess.run([sys.executable,'app.py','missing.csv'],cwd=project,capture_output=True).returncode!=0
    else:
        process=subprocess.Popen(['node','server.mjs'],cwd=project,env={**os.environ,'PORT':'0'},stdout=subprocess.PIPE,text=True)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
        try:
            assert selector.select(5),'server did not start'
            port=int(process.stdout.readline())
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as response:
                assert response.status==200
                assert json.load(response)=={'status':'ok'}
        finally:
            selector.close();process.terminate();process.wait(timeout=5);process.stdout.close()
    # Every accepted field must remain available to a reader, including the stack reason.
    product=(project/'docs/project.md').read_text()
    for value in [intent['goal'],intent['scope'],*intent['constraints'],*intent['success']]:
        assert value in product
    for value in intent['decisions']:
        assert value in (project/'docs/decisions/0001-stack.md').read_text()
    (project/'README.md').write_text('Owned by the product\n'); commit(project)
    (kit/'core/quality.md').write_text((kit/'core/quality.md').read_text()+'\nOne new quality rule.\n');commit(kit,'upgrade fixture')
    assert main(['upgrade','--project',str(project),'--kit',str(kit),'--json'])==0
    upgraded=json.loads(capsys.readouterr().out);worktree=Path(upgraded['project'])
    applied=yaml.safe_load((worktree/'project-kit.lock.yaml').read_text())
    assert applied['kit_commit']!=initial['kit_commit']
    assert (worktree/'README.md').read_text()=='Owned by the product\n'
    commit(worktree,'apply upgrade');git(project,'merge','--ff-only',git(worktree,'branch','--show-current'))
    assert main(['init','--project',str(project),'--json'])==0
    capsys.readouterr()
    assert main(['check','--project',str(project),'--runtime','--json'])==0
    capsys.readouterr()

def test_installed_cli_works_outside_source_checkout(tmp_path):
    result=subprocess.run([sys.executable,'-m','project_kit','--help'],cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert 'init' in result.stdout and 'upgrade' in result.stdout
