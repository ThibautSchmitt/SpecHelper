import stat

from core.control import control_token


def test_internal_control_secret_is_generated_once_and_hidden_from_source(tmp_path, monkeypatch):
    path = tmp_path / "protected/runtime.token"
    monkeypatch.delenv("RUNTIME_TOKEN", raising=False)
    monkeypatch.setenv("CONTROL_TOKEN_FILE", str(path))
    assert control_token() == ""
    value = control_token(create=True)
    assert len(value) >= 64
    assert control_token() == value
    assert control_token(create=True) == value
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    monkeypatch.setenv("RUNTIME_TOKEN", "explicit-override")
    assert control_token() == "explicit-override"
