"""Exercise ownership and real payload checks; only native client I/O is replaced."""
from dataclasses import replace
import json
from pathlib import Path
import pytest
from conftest import commit

@pytest.fixture
def native(monkeypatch):
    from project_kit.adapters import native
    monkeypatch.setattr(native,'inventory',lambda agent,project: [])
    monkeypatch.setattr(native,'version',lambda agent,project: 'test-client-1')
    return native

def loaded(bundle,project):
    from project_kit.adapters import marketplace_name
    market=marketplace_name(bundle)
    packages=[]
    for package in bundle.packages:
        packages.append({'id':f'{package.name}@{market}','name':package.name,'enabled':True,
                         'root':str(package.root),'skills':[str(p) for p in (package.root/'skills').glob('*/SKILL.md')],
                         'hooks':[],'mcp':[]})
    return {'packages':packages,'errors':[]}

def test_two_projects_keep_distinct_versions(tmp_path,kit,config,bundle,native,monkeypatch):
    from project_kit.adapters import configure,codex
    from project_kit.sources import prepare_bundle
    a=tmp_path/'a'; b=tmp_path/'b'; a.mkdir(); b.mkdir()
    configure(a,bundle)
    original=(a/'.codex/config.toml').read_bytes()
    (kit/'core/entry.md').write_text('Second revision\n'); commit(kit,'new kit')
    second=prepare_bundle(kit,config,tmp_path/'cache-2')
    configure(b,second)
    monkeypatch.setattr(native,'runtime',lambda agent,project: loaded(bundle if project==a else second,project))
    ca,oa=codex.observe(a,bundle,True); cb,ob=codex.observe(b,second,True)
    assert ca.status==cb.status=='ready'
    assert oa.observed_packages!=ob.observed_packages
    assert (a/'.codex/config.toml').read_bytes()==original

def test_unrelated_settings_unchanged(tmp_path,bundle,native):
    from project_kit.adapters import configure
    root=tmp_path/'project'; (root/'.codex').mkdir(parents=True); (root/'.claude').mkdir()
    (root/'.codex/config.toml').write_text('# personal\nmodel = "chosen"\n')
    (root/'.claude/settings.json').write_text('{"language":"russian","enabledPlugins":{"foreign@other":true}}')
    configure(root,bundle)
    assert (root/'.codex/config.toml').read_text().startswith('# personal\nmodel = "chosen"\n')
    data=json.loads((root/'.claude/settings.json').read_text())
    assert data['language']=='russian' and data['enabledPlugins']['foreign@other'] is True

@pytest.mark.parametrize('agent',['codex','claude-code'])
def test_missing_client_incomplete(tmp_path,bundle,agent,monkeypatch):
    from project_kit.adapters import adapter,native
    def missing(*args):raise FileNotFoundError('client missing')
    monkeypatch.setattr(native,'version',missing)
    check,observation=adapter(agent).observe(tmp_path,bundle,True)
    assert check.status=='incomplete' and observation is None

def test_unknown_capability_incompatible(tmp_path,bundle,native):
    from project_kit.adapters import codex
    unknown=replace(bundle,profile={**bundle.profile,'hooks':'telepathy'})
    check,_=codex.observe(tmp_path,unknown,True)
    assert check.status=='incompatible'

def test_native_paths_with_spaces(tmp_path,bundle,native):
    from project_kit.adapters import configure
    root=tmp_path/'мой проект'; root.mkdir()
    configure(root,bundle)
    data=json.loads((root/'.claude/settings.local.json').read_text())
    entry=next(iter(data['extraKnownMarketplaces'].values()))
    assert Path(entry['source']['path']).is_relative_to(root)
    assert Path(entry['source']['path']).exists()

def test_runtime_payload_mismatch_is_drift(tmp_path,bundle,native,monkeypatch):
    from project_kit.adapters import codex
    snapshot=loaded(bundle,tmp_path)
    (bundle.packages[0].root/'core/entry.md').write_text('tampered')
    monkeypatch.setattr(native,'runtime',lambda *args:snapshot)
    check,_=codex.observe(tmp_path,bundle,True)
    assert check.status=='drift'

def test_native_absent_package_not_ready(tmp_path,bundle,native,monkeypatch):
    from project_kit.adapters import codex
    monkeypatch.setattr(native,'runtime',lambda *args:{'packages':[],'errors':[]})
    check,_=codex.observe(tmp_path,bundle,True)
    assert check.status=='incomplete'

def test_foreign_marketplace_preserved(tmp_path,bundle,native):
    from project_kit.adapters import configure
    from project_kit.files import MergeConflict
    path=tmp_path/'.agents/plugins/marketplace.json';path.parent.mkdir(parents=True)
    original=b'{"name":"my-market","plugins":[{"name":"foreign"}]}'
    path.write_bytes(original)
    with pytest.raises(MergeConflict):configure(tmp_path,bundle)
    assert path.read_bytes()==original

def test_enabled_duplicate_version_is_drift(tmp_path,bundle,native,monkeypatch):
    from project_kit.adapters import codex
    snapshot=loaded(bundle,tmp_path)
    snapshot['packages'].append({**snapshot['packages'][0],'id':'project-kit@other'})
    monkeypatch.setattr(native,'runtime',lambda *args:snapshot)
    check,_=codex.observe(tmp_path,bundle,True)
    assert check.status=='drift'

def test_initialize_connects_both_adapters(tmp_path,intent_data,bundle,native):
    from project_kit.config import intent_from_data
    from project_kit.init import initialize
    root=tmp_path/'project'
    initialize(root,intent_from_data(intent_data),bundle)
    assert (root/'.codex/config.toml').exists()
    assert (root/'.claude/settings.json').exists()
    state=json.loads((root/'.project-kit/operation.json').read_text())
    assert '.codex/config.toml' in state['candidate']['owned_settings']

def test_native_probe_does_not_inspect_unrelated_plugins(tmp_path,bundle,native,monkeypatch):
    from project_kit.adapters import configure,marketplace_name
    configure(tmp_path,bundle)
    identifier='project-kit@'+marketplace_name(bundle)
    paths=[str(p) for p in (bundle.packages[0].root/'skills').glob('*/SKILL.md')]
    rows=[{'id':identifier,'name':'project-kit','enabled':True,'installed':True},
          {'id':'foreign@other','name':'foreign','enabled':True,'installed':True}]
    monkeypatch.setattr(native,'inventory',lambda *args:rows)
    class Transport:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def call(self,method,params):
            if method=='config/read':return {'layers':[]}
            if method=='skills/list':
                return {'data':[{'skills':[{'path':p,'pluginId':r['id'],'enabled':True} for r in rows for p in paths],'errors':[]}]}
            if method=='hooks/list':return {'data':[{'hooks':[],'errors':[]}]}
            if method=='plugin/list':return {'marketplaces':[{'path':'catalog','plugins':rows}]}
            if method=='plugin/read':return {'plugin':{'mcpServers':[]}}
            raise AssertionError('unexpected native method')
    monkeypatch.setattr(native,'CodexRPC',Transport)
    assert [p['id'] for p in native._codex_runtime(tmp_path)['packages']]==[identifier]

def test_untrusted_codex_project_reports_required_action(tmp_path,native,monkeypatch):
    class Transport:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def call(self,method,params):
            if method=='config/read':
                return {'layers':[{'name':{'type':'project'},'disabledReason':'project is not trusted'}]}
            return {'data':[],'marketplaces':[]}
    monkeypatch.setattr(native,'CodexRPC',Transport)
    with pytest.raises(native.NativeError,match='trust'):
        native._codex_runtime(tmp_path)

def test_codex_checks_each_mcp_server_individually(tmp_path,bundle,native,monkeypatch):
    from project_kit.adapters import configure,marketplace_name
    configure(tmp_path,bundle)
    identifier='project-kit@'+marketplace_name(bundle)
    path=str(next((bundle.packages[0].root/'skills').glob('*/SKILL.md')))
    rows=[{'id':identifier,'name':'project-kit','enabled':True,'installed':True}]
    monkeypatch.setattr(native,'inventory',lambda *args:rows)
    class Transport:
        def __init__(self,*args):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def call(self,method,params):
            if method=='config/read':return {'layers':[]}
            if method=='skills/list':return {'data':[{'skills':[{'path':path,'pluginId':identifier,'enabled':True}],'errors':[]}]}
            if method=='hooks/list':return {'data':[{'hooks':[],'errors':[]}]}
            if method=='plugin/list':return {'marketplaces':[{'path':'catalog','plugins':rows}]}
            if method=='plugin/read':return {'plugin':{'mcpServers':['first','second']}}
            if method=='mcpServerStatus/list':return {'data':[
                {'name':'first','pluginId':identifier,'serverInfo':{'name':'one'},'runtimeStatus':'connected'},
                {'name':'second','pluginId':identifier,'serverInfo':None,'toolsError':'unavailable','runtimeStatus':'failed'}]}
            raise AssertionError(method)
    monkeypatch.setattr(native,'CodexRPC',Transport)
    assert native._codex_runtime(tmp_path)['packages'][0]['mcp']==[{'ready':True},{'ready':False}]

def test_claude_only_profile_discovers_native_skills(tmp_path,bundle,native,monkeypatch):
    import sys
    from project_kit.adapters import configure,marketplace_name,claude_code
    single=replace(bundle,profile={**bundle.profile,'agents':['claude-code']})
    configure(tmp_path,single)
    assert not (tmp_path/'.agents/plugins/marketplace.json').exists()
    package=single.packages[0]
    identifier='project-kit@'+marketplace_name(single)
    monkeypatch.setattr(native,'inventory',lambda *args:[{'id':identifier,'name':'project-kit','enabled':True,'root':str(package.root)}])
    monkeypatch.setattr(native,'run',lambda *args:'validated')
    event={'type':'system','subtype':'init','plugins':[{'name':identifier}],
           'skills':['project-kit:'+p.parent.name for p in (package.root/'skills').glob('*/SKILL.md')], 'mcp_servers':[]}
    popen=native.subprocess.Popen
    def spawn(argv,**kwargs):
        return popen([sys.executable,'-u','-c','import sys,time; print(sys.argv[1],flush=True); time.sleep(5)',json.dumps(event)],**kwargs)
    monkeypatch.setattr(native.subprocess,'Popen',spawn)
    monkeypatch.setattr(native,'runtime',lambda agent,project:native._claude_runtime(project))
    check,observation=claude_code.observe(tmp_path,single,True)
    assert check.status=='ready',check
    assert observation.loaded_skills

def test_codex_consumes_response_buffered_after_notification(tmp_path,native,monkeypatch):
    import sys
    popen=native.subprocess.Popen
    server='import sys,time; sys.stdin.readline(); sys.stdout.write(\'{{"method":"notice"}}\\n{{"id":1,"result":{{}}}}\\n\'); sys.stdout.flush(); time.sleep(5)'.replace('{{','{').replace('}}','}')
    def spawn(argv,**kwargs):
        return popen([sys.executable,'-u','-c',server],**kwargs)
    monkeypatch.setattr(native.subprocess,'Popen',spawn)
    factory=native.selectors.DefaultSelector
    class BoundedSelector:
        def __init__(self):self.selector=factory()
        def register(self,*args):return self.selector.register(*args)
        def select(self,timeout):return self.selector.select(min(timeout,0.2))
        def close(self):self.selector.close()
    monkeypatch.setattr(native.selectors,'DefaultSelector',BoundedSelector)
    with native.CodexRPC(tmp_path):
        pass
