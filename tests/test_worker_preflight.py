import app.cli.process_catalogue_ingestion_runs as proc


def test_process_stops_on_preflight_block(monkeypatch, capsys):
    # Make preflight report blocked
    monkeypatch.setattr(
        proc,
        "run_catalogue_preflight",
        lambda settings: {"status": "blocked", "checks": {}},
    )
    # Ensure kill switch is not active
    monkeypatch.setattr(proc, "kill_switch_active", lambda path: False)

    # Replace SystemSessionLocal with a no-op context manager
    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(proc, "SystemSessionLocal", lambda: DummySession())

    # Replace OperationalJobService to avoid DB interactions
    class DummyHealth:
        def __init__(self, session):
            pass

        def started(self, name):
            pass

        def completed(self, name, count):
            pass

        def failed(self, name, exc):
            pass

    monkeypatch.setattr(proc, "OperationalJobService", DummyHealth)

    # Replace CatalogueIngestionService with one that would fail if used
    class FakeService:
        def __init__(self, session, settings, **kwargs):
            pass

        def process_next_runs(self, *args, **kwargs):
            raise AssertionError("process_next_runs should not be called when preflight is blocked")

    monkeypatch.setattr(proc, "CatalogueIngestionService", FakeService)

    # Run main; it should not raise and should print preflight blocked message
    proc.main(["--limit", "1", "--batch-size", "1"])
    captured = capsys.readouterr()
    assert "preflight blocked" in captured.out.lower()


def test_process_stops_on_kill_switch(monkeypatch, capsys):
    # Kill switch active -> preflight must NOT run and processing must be skipped
    monkeypatch.setattr(proc, "kill_switch_active", lambda path: True)
    monkeypatch.setattr(
        proc,
        "run_catalogue_preflight",
        lambda settings: (_ for _ in ()).throw(
            AssertionError("preflight should not be called when kill switch active")
        ),
    )

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(proc, "SystemSessionLocal", lambda: DummySession())

    class DummyHealth:
        def __init__(self, session):
            pass

        def started(self, name):
            pass

        def completed(self, name, count):
            pass

        def failed(self, name, exc):
            pass

    monkeypatch.setattr(proc, "OperationalJobService", DummyHealth)

    class FakeService:
        def __init__(self, session, settings, **kwargs):
            pass

        def process_next_runs(self, *args, **kwargs):
            raise AssertionError("process_next_runs should not be called when kill switch active")

    monkeypatch.setattr(proc, "CatalogueIngestionService", FakeService)
    proc.main(["--limit", "1", "--batch-size", "1"])
    captured = capsys.readouterr()
    assert "paused" in captured.out.lower()


def test_process_handles_preflight_exception(monkeypatch, capsys):
    # Preflight raises -> fail closed and do not call process_next_runs
    monkeypatch.setattr(proc, "kill_switch_active", lambda path: False)
    monkeypatch.setattr(
        proc,
        "run_catalogue_preflight",
        lambda settings: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(proc, "SystemSessionLocal", lambda: DummySession())

    class DummyHealth:
        def __init__(self, session):
            pass

        def started(self, name):
            pass

        def completed(self, name, count):
            pass

        def failed(self, name, exc):
            pass

    monkeypatch.setattr(proc, "OperationalJobService", DummyHealth)

    class FakeService:
        def __init__(self, session, settings, **kwargs):
            pass

        def process_next_runs(self, *args, **kwargs):
            raise AssertionError("process_next_runs should not be called when preflight raises")

    monkeypatch.setattr(proc, "CatalogueIngestionService", FakeService)
    proc.main(["--limit", "1", "--batch-size", "1"])
    captured = capsys.readouterr()
    assert "preflight check failed" in captured.out.lower()
    assert "boom" not in captured.out.lower()


def test_process_allows_ready(monkeypatch, capsys):
    # Preflight ready -> process_next_runs should be called and results printed
    monkeypatch.setattr(proc, "kill_switch_active", lambda path: False)
    monkeypatch.setattr(
        proc, "run_catalogue_preflight", lambda settings: {"status": "ready", "checks": {}}
    )

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(proc, "SystemSessionLocal", lambda: DummySession())

    class DummyHealth:
        def __init__(self, session):
            pass

        def started(self, name):
            pass

        def completed(self, name, count):
            pass

        def failed(self, name, exc):
            pass

    monkeypatch.setattr(proc, "OperationalJobService", DummyHealth)

    class FakeResult:
        def __init__(self):
            self.id = 1
            from types import SimpleNamespace

            self.status = SimpleNamespace(value="done")
            self.stage = SimpleNamespace(value="complete")
            self.attempt_count = 0
            self.checkpoint_cursor = None

    class FakeService:
        def __init__(self, session, settings, **kwargs):
            pass

        def process_next_runs(self, *args, **kwargs):
            return [FakeResult()]

    monkeypatch.setattr(proc, "CatalogueIngestionService", FakeService)
    proc.main(["--limit", "1", "--batch-size", "1"])
    captured = capsys.readouterr()
    assert "catalogue ingestion run" in captured.out.lower()
