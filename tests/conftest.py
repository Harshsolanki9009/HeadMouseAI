"""Pytest configuration and test isolation fixtures for HeadMouseAI."""

import pytest
from config.settings import AppSettings
import config.settings


@pytest.fixture(autouse=True)
def isolate_test_settings():
    """Ensure test runs start and clean up without stale cached settings singleton."""
    config.settings._settings = None
    yield
    config.settings._settings = None


@pytest.fixture(scope="session")
def qapp():
    """Ensure a singleton QApplication instance exists for GUI tests."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def pytest_sessionfinish(session, exitstatus):
    """Ensure clean process shutdown on Windows with Python 3.14 and PySide6."""
    import gc
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()
    except Exception:
        pass
    gc.collect()
