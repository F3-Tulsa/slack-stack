import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "slackblast"))

from features import preblast
from utilities.slack import actions


def _preblast_data():
    return {
        actions.PREBLAST_TITLE: "Morning",
        actions.PREBLAST_DATE: "2026-05-18",
        actions.PREBLAST_TIME: "0530",
        actions.PREBLAST_AO: "C_AO",
        actions.PREBLAST_Q: "U_Q",
        actions.PREBLAST_WHY: None,
        actions.PREBLAST_FNGS: None,
        actions.PREBLAST_COUPONS: None,
        actions.PREBLAST_MOLESKIN: None,
        actions.PREBLAST_DESTINATION: "The_AO",
    }


def test_retried_preblast_create_posts_once():
    claimed = set()

    def claim(key, kind, team_id):
        token = (key, kind)
        if token in claimed:
            return False
        claimed.add(token)
        return True

    body = {
        "view": {"id": "V_PRE", "callback_id": actions.PREBLAST_CALLBACK_ID},
        "user": {"id": "U1"},
        "team": {"id": "T1"},
    }
    client = MagicMock()
    region = MagicMock()
    region.paxminer_schema = None
    region.workspace_name = "ws"

    form = MagicMock()
    form.get_selected_values.side_effect = lambda _body: _preblast_data()

    with (
        patch("features.preblast.forms.PREBLAST_FORM", form),
        patch("features.preblast.get_user_names", return_value=(["Q"], [""])),
        patch("features.preblast.DbManager.find_records", return_value=[]),
        patch("utilities.interaction_claims.claim_interaction", side_effect=claim),
    ):
        for _ in range(2):
            preblast.handle_preblast_post(body, client, MagicMock(), {}, region)

    assert client.chat_postMessage.call_count == 1


def _edit_click(*, payload=None, value="edit"):
    message = {"ts": "1.1"}
    if payload is not None:
        message["metadata"] = {"event_type": "preblast", "event_payload": payload}
    return {
        "user_id": "U_CLICK",
        "channel_id": "C1",
        "actions": [{"action_id": actions.PREBLAST_EDIT_BUTTON, "value": value}],
        "message": message,
        "loading_id": "V_LOAD",
    }


def _region(*, locked):
    return SimpleNamespace(editing_locked=locked, preblast_moleskin_template="")


def _client():
    client = MagicMock()
    client.users_info.return_value = {"user": {"is_admin": False}}
    return client


def test_locked_preblast_edit_allows_original_poster():
    client = _client()
    with patch("features.preblast.build_preblast_form") as build:
        preblast.handle_preblast_edit_button(
            _edit_click(payload={actions.PREBLAST_Q: "U_Q", actions.PREBLAST_OP: "U_CLICK"}),
            client,
            MagicMock(),
            {},
            _region(locked=1),
        )
    build.assert_called_once()


def test_locked_preblast_edit_without_metadata_does_not_parse_the_button_value():
    client = _client()
    with patch("features.preblast.build_preblast_form") as build:
        preblast.handle_preblast_edit_button(
            _edit_click(value="edit"),
            client,
            MagicMock(),
            {},
            _region(locked=1),
        )
    build.assert_not_called()
    client.chat_postEphemeral.assert_called_once()


def test_unlocked_preblast_edit_without_metadata_opens_the_form():
    client = _client()
    with patch("utilities.slack.orm.BlockView.update_modal") as update_modal:
        preblast.handle_preblast_edit_button(
            _edit_click(value="edit"),
            client,
            MagicMock(),
            {},
            _region(locked=0),
        )
    update_modal.assert_called_once()
