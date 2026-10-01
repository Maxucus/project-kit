"""A failed update cannot destroy user bytes or escape the target directory."""
import os
import pytest

def test_symlink_escape_no_write(tmp_path):
    from project_kit.files import contained_path
    root=tmp_path/'project'; root.mkdir()
    outside=tmp_path/'outside'; outside.mkdir()
    (root/'docs').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='outside'):
        contained_path(root,'docs/project.md')
    assert not (outside/'project.md').exists()

@pytest.mark.parametrize('relative',['../outside','/tmp/outside','.git/config'])
def test_unsafe_paths_rejected(tmp_path,relative):
    from project_kit.files import contained_path
    with pytest.raises(ValueError): contained_path(tmp_path,relative)

def test_atomic_write_preserves_mode_and_original_on_failure(tmp_path,monkeypatch):
    from project_kit.files import write_atomic
    path=tmp_path/'script'; path.write_bytes(b'old'); path.chmod(0o755)
    def fail(*args): raise OSError('injected replace failure')
    with monkeypatch.context() as m:
        m.setattr(os,'replace',fail)
        with pytest.raises(OSError): write_atomic(path,b'new')
    assert path.read_bytes()==b'old'
    write_atomic(path,b'new')
    assert path.read_bytes()==b'new'
    assert path.stat().st_mode & 0o777 == 0o755

def test_markdown_merge_preserves_unowned_bytes():
    from project_kit.files import merge_owned
    base=b'<!-- BEGIN PROJECT-KIT -->\nold\n<!-- END PROJECT-KIT -->\n'
    desired=base.replace(b'old',b'new')
    current=b'Personal introduction\n\n'+base+b'\nMy additions\n'
    assert merge_owned(current,base,desired,'markdown',(('PROJECT-KIT',),)) == current.replace(b'old',b'new')

def test_modified_owned_block_conflicts():
    from project_kit.files import merge_owned,MergeConflict
    base=b'<!-- BEGIN PROJECT-KIT -->\nold\n<!-- END PROJECT-KIT -->\n'
    with pytest.raises(MergeConflict):
        merge_owned(base.replace(b'old',b'local'),base,base.replace(b'old',b'new'),'markdown',(('PROJECT-KIT',),))

def test_json_merge_preserves_foreign_keys():
    from project_kit.files import merge_owned
    import json
    merged=merge_owned(b'{"foreign":{"keep":true},"plugins":{"a":true}}',b'{"plugins":{"a":true}}',b'{"plugins":{"a":false}}','json',(('plugins','a'),))
    assert json.loads(merged)=={'foreign':{'keep':True},'plugins':{'a':False}}

def test_toml_merge_preserves_comments_and_dotted_keys():
    from project_kit.files import merge_owned
    import tomllib
    original=b'# Keep this\nmodel = "local"\n[plugins."a.b@kit"]\nenabled = true\n'
    merged=merge_owned(original,b'[plugins."a.b@kit"]\nenabled = true\n',b'[plugins."a.b@kit"]\nenabled = false\n','toml',(('plugins','a.b@kit','enabled'),))
    assert merged.startswith(b'# Keep this\nmodel = "local"\n')
    assert tomllib.loads(merged.decode())['plugins']['a.b@kit']['enabled'] is False
