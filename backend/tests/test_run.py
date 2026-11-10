import run


def capture_run(monkeypatch):
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(run.app, "run", fake_run)
    return called


def test_run_uses_local_defaults(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    called = capture_run(monkeypatch)

    run.run_server()

    assert called == {"host": "127.0.0.1", "port": 5000, "debug": False}


def test_run_uses_host_environment_override(monkeypatch):
    monkeypatch.setenv("HOST", "localhost")
    monkeypatch.delenv("PORT", raising=False)
    called = capture_run(monkeypatch)

    run.run_server()

    assert called == {"host": "localhost", "port": 5000, "debug": False}


def test_run_uses_port_environment_override(monkeypatch):
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setenv("PORT", "5002")
    called = capture_run(monkeypatch)

    run.run_server()

    assert called == {"host": "127.0.0.1", "port": 5002, "debug": False}
