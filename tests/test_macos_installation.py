import json
import pytest
import paperbridge.app as app_module


@pytest.mark.parametrize('preferred,standard,precision,expected',[
    ('standard',True,True,'standard'),('precision',True,True,'precision'),
    ('precision',True,False,'standard'),('standard',False,True,'precision'),
    (None,True,False,'standard'),(None,False,True,'precision')])
def test_mac_installed_model_selection_survives_application_update(tmp_path,monkeypatch,preferred,standard,precision,expected):
    monkeypatch.setattr(app_module,'ROOT',tmp_path)
    monkeypatch.setattr(app_module,'WINDOWS',False)
    monkeypatch.setattr(app_module.translator,'installed',lambda:standard)
    monkeypatch.setattr(app_module,'precision_installed',lambda:precision)
    (tmp_path/'macos-installation.json').write_text(json.dumps({'default_profile':preferred,'models_managed_separately':True,'app_version':'1.8.0'}))
    state=app_module.status()
    assert state['default_profile']==expected
    assert state['managed_models'] is True
