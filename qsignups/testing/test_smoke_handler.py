import os
import sys
from unittest.mock import MagicMock, patch

_PKG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qsignups"))
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)
os.environ.setdefault("DATABASE_SCHEMA", "f3ttown_test")
os.environ.setdefault("DB_ENCRYPTION_KEY", "ci-test-encryption-key-32chars!")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "signing-secret")


def _engine(row):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.execute.return_value.first.return_value = row
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


def _handler():
    with patch("slack_bolt.app.app.App._init_middleware_list", lambda *args, **kwargs: None):
        import app as app_mod

        return app_mod.handler


def test_smoke_returns_200_when_qsignups_regions_has_a_row():
    handler = _handler()
    with patch("database.get_engine", return_value=_engine((1,))):
        result = handler({"source": "smoke"}, None)
    assert result["statusCode"] == 200
    assert result["body"] == "ok"


def test_smoke_returns_500_when_qsignups_regions_is_empty():
    handler = _handler()
    with patch("database.get_engine", return_value=_engine(None)):
        result = handler({"source": "smoke"}, None)
    assert result["statusCode"] == 500


def test_smoke_returns_500_when_the_ping_fails():
    handler = _handler()
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("down")
    with patch("database.get_engine", return_value=engine):
        result = handler({"source": "smoke"}, None)
    assert result["statusCode"] == 500
