"""Reject ambiguous inputs before they can produce project files."""
import pytest
import yaml

def test_missing_goal(tmp_path,intent_data):
    from project_kit.config import load_intent
    intent_data.pop('goal')
    path=tmp_path/'intent.yaml'; path.write_text(yaml.safe_dump(intent_data))
    with pytest.raises(ValueError,match='goal'): load_intent(path)

def test_unknown_schema(tmp_path):
    from project_kit.config import load_config
    path=tmp_path/'config.yaml'; path.write_text('schema: 2\nprofile: default\nagents: [codex]\n')
    with pytest.raises(ValueError,match='schema'): load_config(path)

@pytest.mark.parametrize('agents',['[codex, codex]','[unknown]','[]'])
def test_invalid_agents(tmp_path,agents):
    from project_kit.config import load_config
    path=tmp_path/'config.yaml'; path.write_text(f'schema: 1\nprofile: default\nagents: {agents}\n')
    with pytest.raises(ValueError,match='agents'): load_config(path)

def test_duplicate_yaml_key(tmp_path):
    from project_kit.config import load_config
    path=tmp_path/'config.yaml'; path.write_text('schema: 1\nschema: 1\n')
    with pytest.raises(ValueError,match='duplicate'): load_config(path)

def test_valid_intent_roundtrip(tmp_path,intent_data):
    from project_kit.config import load_intent
    path=tmp_path/'intent.yaml'; path.write_text(yaml.safe_dump(intent_data))
    result=load_intent(path)
    assert result.commands['test']==('python','app.py','input.csv')
    assert result.constraints==('UTF-8',)

def test_success_required(tmp_path,intent_data):
    from project_kit.config import load_intent
    intent_data['success']=[]
    path=tmp_path/'intent.yaml'; path.write_text(yaml.safe_dump(intent_data))
    with pytest.raises(ValueError,match='success'): load_intent(path)
