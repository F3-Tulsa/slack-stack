import logging
import os
import sys
from unittest.mock import MagicMock

_PKG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "qsignups"))
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from utilities import log_slack_request, report_unhandled_error, slack_request_context


def test_log_slack_request_includes_channel_post_and_modal_ids():
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    log = logging.getLogger("qsignups.log-context-test")
    handler = _Capture()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    secret = "form-secret-token"
    try:
        log_slack_request(
            log,
            {
                "type": "view_submission",
                "team_id": "T1",
                "user": {"id": "U1"},
                "token": "xoxb-should-not-log",
                "view": {
                    "id": "V_EDIT",
                    "callback_id": "edit-event",
                    "private_metadata": (
                        '{"ao_channel_id":"C0123456789","event_id":17,'
                        '"input_data":{"title":"secret workout"}}'
                    ),
                    "state": {"values": {"password": {"v": {"value": secret}}}},
                },
            },
        )
    finally:
        log.removeHandler(handler)

    logged = " ".join(record.getMessage() for record in records)
    assert "type=view_submission" in logged
    assert "team_id=T1" in logged
    assert "user_id=U1" in logged
    assert "callback_id=edit-event" in logged
    assert "channel_id=C0123456789" in logged
    assert "view_id=V_EDIT" in logged
    assert "event_id=17" in logged
    assert secret not in logged
    assert "secret workout" not in logged
    assert "xoxb-should-not-log" not in logged
    assert "input_data" not in logged


def test_log_slack_request_omits_blank_user_and_channel():
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    log = logging.getLogger("qsignups.log-blank-test")
    handler = _Capture()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log_slack_request(log, {"type": "event_callback", "team_id": "T1", "event": {"type": "team_join"}})
    finally:
        log.removeHandler(handler)
    logged = " ".join(record.getMessage() for record in records)
    assert "team_id=T1" in logged
    assert "event_type=team_join" in logged
    assert "user_id=" not in logged
    assert "channel_id=" not in logged
    assert "action_id=" not in logged
    assert "callback_id=" not in logged


def test_unhandled_error_posts_to_the_log_channel_without_blank_fields():
    log = MagicMock()
    client = MagicMock()
    report_unhandled_error(log, client, {"type": "event_callback", "event": {"type": "team_join"}}, RuntimeError("db down"))
    client.chat_postMessage.assert_called_once()
    assert client.chat_postMessage.call_args.kwargs["channel"] == "paxminer_logs"
    text = client.chat_postMessage.call_args.kwargs["text"]
    assert "RuntimeError" in text
    assert "User:" not in text
    assert "Channel:" not in text


def test_button_on_a_message_logs_the_channel_and_timestamp():
    context = slack_request_context(
        {
            "type": "block_actions",
            "container": {"channel_id": "C_POST", "message_ts": "111.222"},
            "message": {"text": "posted schedule"},
            "actions": [{"action_id": "signup", "value": "edit"}],
        }
    )
    assert context["channel_id"] == "C_POST"
    assert context["message_ts"] == "111.222"
    assert "posted schedule" not in str(context)
