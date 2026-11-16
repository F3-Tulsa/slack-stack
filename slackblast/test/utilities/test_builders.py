import logging
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "slackblast"))
os.environ.setdefault("DB_ENCRYPTION_KEY", "ci-test-encryption-key-32chars!")
os.environ.setdefault("DATABASE_SCHEMA", "f3ttown_test")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "signing-secret")

from slack_sdk.errors import SlackApiError

from utilities.builders import send_error_response, user_facing_error
from utilities.routing import EVENT_MAPPER
from utilities.slack.actions import LOADING_ID


def _app():
    with patch("slack_bolt.app.app.App._init_middleware_list", lambda *a, **k: None):
        import app as app_mod

        return app_mod


def test_user_facing_error_names_the_failure_and_where_to_look():
    long_sql = "Duplicate entry " + ("x" * 500)
    notice = user_facing_error(
        RuntimeError(long_sql),
        {"view": {"callback_id": "backblast-id"}},
        ref="ab12cd34",
    )
    assert "Something went wrong: RuntimeError (backblast-id)." in notice
    assert "Tell an admin this code: ab12cd34." in notice
    assert "Slackblast CloudWatch logs" in notice
    assert long_sql not in notice
    labeled = user_facing_error(RuntimeError("db down"), {"view": {"callback_id": "backblast-id"}})
    assert labeled == "Something went wrong: db down (RuntimeError) (backblast-id)."
    slack_error = SlackApiError("fail", {"error": "channel_not_found"})
    assert user_facing_error(slack_error) == "Something went wrong: Slack error channel_not_found."


def test_debug_log_does_not_include_the_email_password():
    app_mod = _app()
    log = logging.getLogger("slackblast.secret-log-test")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    secret = "smtp-secret-password"
    try:
        with patch.object(app_mod, "get_region_record", return_value=MagicMock()):
            app_mod.main_response(
                {
                    "type": "block_actions",
                    "team_id": "T1",
                    "user": {"id": "U1"},
                    "channel_id": "C_DOWNRANGE",
                    "channel_name": "downrange",
                    "container": {"message_ts": "111.222"},
                    "actions": [{"action_id": "not-a-real-action"}],
                    "view": {
                        "id": "V_FORM",
                        "state": {"values": {"email_password": {"v": {"value": secret}}}},
                    },
                },
                log,
                MagicMock(),
                MagicMock(),
                {},
            )
    finally:
        log.removeHandler(handler)
    logged = " ".join(record.getMessage() for record in records)
    assert secret not in logged
    assert "user_id=U1" in logged
    assert "channel_id=C_DOWNRANGE" in logged
    assert "channel_name=downrange" in logged
    assert "message_ts=111.222" in logged
    assert "view_id=V_FORM" in logged
    assert "user_id=None" not in logged
    assert "channel_id=" not in logged.replace("channel_id=C_DOWNRANGE", "")


def test_event_error_does_not_dm_the_new_member():
    client = MagicMock()
    send_error_response(
        {
            "event_id": "Ev123",
            "team_id": "T123",
            "event": {"type": "team_join", "user": {"id": "U123"}},
        },
        client,
        "welcome failed",
    )
    client.chat_postMessage.assert_not_called()
    client.views_update.assert_not_called()


def test_interactive_error_still_dms_the_clicker():
    client = MagicMock()
    send_error_response({"user": {"id": "U9"}}, client, "form failed")
    client.chat_postMessage.assert_called_once()
    assert client.chat_postMessage.call_args.kwargs["channel"] == "U9"


def test_loading_modal_is_updated_and_the_clicker_is_told():
    client = MagicMock()
    send_error_response({LOADING_ID: "V1", "user": {"id": "U9"}}, client, "form failed")
    client.views_open.assert_not_called()
    client.views_update.assert_called_once()
    assert client.views_update.call_args.kwargs["view_id"] == "V1"
    client.chat_postMessage.assert_called_once()
    assert client.chat_postMessage.call_args.kwargs["channel"] == "U9"


def test_open_modal_is_updated_without_opening_another():
    client = MagicMock()
    send_error_response({"view": {"id": "V_FORM"}, "user": {"id": "U9"}}, client, "form failed")
    client.views_open.assert_not_called()
    client.views_update.assert_called_once()
    assert client.views_update.call_args.kwargs["view_id"] == "V_FORM"
    client.chat_postMessage.assert_called_once()


def test_handler_error_is_logged_when_the_error_response_fails():
    app_mod = _app()
    log = logging.getLogger("slackblast.welcome-error-test")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    log.addHandler(handler)
    log.setLevel(logging.ERROR)

    def boom(**_kwargs):
        raise ValueError("missing event_id")

    original = EVENT_MAPPER["team_join"]
    EVENT_MAPPER["team_join"] = (boom, False)
    region = MagicMock()
    region.log_channel = "CLOG"
    region.team_id = "T123"
    region.workspace_name = "Tulsa"
    client = MagicMock()
    try:
        with (
            patch.object(app_mod, "get_region_record", return_value=region),
            patch.object(app_mod, "send_error_response", side_effect=RuntimeError("notify failed")),
        ):
            app_mod.main_response(
                {
                    "type": "event_callback",
                    "team_id": "T123",
                    "event_id": "Ev123",
                    "event": {
                        "type": "team_join",
                        "channel": "C_WELCOME",
                        "user": {"id": "U123"},
                    },
                    "view": {"id": "V_WELCOME"},
                },
                log,
                client,
                MagicMock(),
                {},
            )
    finally:
        EVENT_MAPPER["team_join"] = original
        log.removeHandler(handler)

    logged = " ".join(
        f"{record.getMessage()} {record.exc_info[1] if record.exc_info and record.exc_info[1] else ''}"
        for record in records
    )
    assert "Handler error ref=" in logged
    assert "team_id=T123" in logged
    assert "user_id=U123" in logged
    assert "request_id=team_join" in logged
    assert "channel_id=C_WELCOME" in logged
    assert "view_id=V_WELCOME" in logged
    assert "user_id=None" not in logged
    assert "channel_id= " not in logged
    assert "missing event_id" in logged
    assert "notify failed" in logged
    log_posts = [call for call in client.chat_postMessage.call_args_list if call.kwargs.get("channel") == "CLOG"]
    assert len(log_posts) == 1
    log_text = log_posts[0].kwargs["text"]
    assert "Team: T123" in log_text
    assert "User: U123" in log_text
    assert "Channel: C_WELCOME" in log_text
    assert "User: \n" not in log_text
    assert "Channel: \n" not in log_text
