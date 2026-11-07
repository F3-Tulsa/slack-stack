import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "slackblast"))
os.environ.setdefault("DB_ENCRYPTION_KEY", "ci-test-encryption-key-32chars!")
os.environ.setdefault("DATABASE_SCHEMA", "f3ttown_test")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "signing-secret")

def _handler():
    with patch("slack_bolt.app.app.App._init_middleware_list", lambda *args, **kwargs: None):
        import app as app_mod

        return app_mod.handler


def _engine(row):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.execute.return_value.first.return_value = row
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


def test_smoke_returns_200_when_the_region_has_a_team():
    handler = _handler()
    with patch("utilities.database.get_engine", return_value=_engine(("T1",))):
        result = handler({"source": "smoke"}, None)
    assert result["statusCode"] == 200
    assert result["body"] == "ok"
    assert "T1" not in result["body"]


def test_smoke_returns_500_when_team_id_is_empty():
    handler = _handler()
    with patch("utilities.database.get_engine", return_value=_engine((None,))):
        result = handler({"source": "smoke"}, None)
    assert result["statusCode"] == 500


def test_smoke_returns_500_when_the_ping_fails():
    handler = _handler()
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("down")
    with patch("utilities.database.get_engine", return_value=engine):
        result = handler({"source": "smoke"}, None)
    assert result["statusCode"] == 500
