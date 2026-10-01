"""Pins, tracked snapshots and payload checks cannot be replaced by version labels."""
import pytest
from conftest import git,commit

def test_dirty_source_rejected(kit,config,tmp_path):
    from project_kit.sources import prepare_bundle
    (kit/'core/entry.md').write_text('changed')
    with pytest.raises(ValueError,match='dirty'): prepare_bundle(kit,config,tmp_path/'cache')

def test_changed_payload_same_version(bundle):
    from project_kit.sources import verify_bundle
    (bundle.packages[0].root/'core/entry.md').write_text('tampered')
    assert any(c.status=='drift' for c in verify_bundle(bundle))

def test_uninitialized_submodule(kit,config,tmp_path):
    from project_kit.sources import prepare_bundle
    git(kit,'update-index','--add','--cacheinfo',f'160000,{git(kit,"rev-parse","HEAD")},upstream/missing')
    git(kit,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','submodule')
    with pytest.raises(ValueError,match='submodule'): prepare_bundle(kit,config,tmp_path/'cache')

def test_snapshot_is_reproducible_and_excludes_ignored_files(kit,config,tmp_path):
    from project_kit.sources import prepare_bundle
    (kit/'.git/info/exclude').write_text('ignored.txt\n')
    (kit/'ignored.txt').write_text('local')
    a=prepare_bundle(kit,config,tmp_path/'a')
    b=prepare_bundle(kit,config,tmp_path/'b')
    assert a.digest==b.digest
    assert not (a.packages[0].root/'ignored.txt').exists()
    assert not (a.packages[0].root/'.git').exists()

def test_symlink_escape_rejected(kit,config,tmp_path):
    from project_kit.sources import prepare_bundle
    (kit/'escape').symlink_to(tmp_path/'outside'); commit(kit)
    with pytest.raises(ValueError,match='symlink'): prepare_bundle(kit,config,tmp_path/'cache')

def test_internal_symlink_retained(kit,config,tmp_path):
    from project_kit.sources import prepare_bundle
    (kit/'alias.md').symlink_to('core/entry.md'); commit(kit)
    bundle=prepare_bundle(kit,config,tmp_path/'cache')
    assert (bundle.packages[0].root/'alias.md').is_symlink()

def test_unknown_override_rejected(kit,config,tmp_path):
    from dataclasses import replace
    from project_kit.sources import prepare_bundle
    with pytest.raises(ValueError,match='overrides'):
        prepare_bundle(kit,replace(config,overrides={'typo':True}),tmp_path/'cache')
