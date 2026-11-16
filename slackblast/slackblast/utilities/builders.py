import copy
import logging
from logging import Logger

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient

from utilities import constants
from utilities.database.orm import Region
from utilities.helper_functions import safe_get
from utilities.slack import actions, forms

# from pymysql.err import ProgrammingError

logger = logging.getLogger(__name__)


def add_loading_form(body: dict, client: WebClient) -> str:
    trigger_id = safe_get(body, "trigger_id")
    loading_form_response = forms.LOADING_FORM.post_modal(
        client=client,
        trigger_id=trigger_id,
        title_text="Loading...",
        submit_button_text="None",
        callback_id="loading-id",
    )
    return safe_get(loading_form_response, "view", "id")


def ignore_event(body: dict, client: WebClient, logger: Logger, context: dict, region_record: Region):
    logger.debug("Ignoring event")


_SECRET_WORDS = ("password", "token", "secret", "select ", "insert ", "update ", "delete ", "drop ")
_DATABASE_ERRORS = {"OperationalError", "DatabaseError", "DataError", "InternalError", "ProgrammingError"}


def _safe_clue(message: str) -> str:
    text = " ".join(message.split())
    if not text or len(text) > 80:
        return ""
    lowered = text.lower()
    if any(word in lowered for word in _SECRET_WORDS):
        return ""
    return text


def _failure_clue(error: BaseException) -> str:
    """A few words a person can repeat. Not the exception text when it may hold SQL or a secret."""
    name = type(error).__name__
    if isinstance(error, SlackApiError):
        response = error.response
        code = ""
        if response is not None and hasattr(response, "get"):
            code = str(response.get("error") or "").strip()
        return f"Slack error {code}" if code else "Slack error"
    if name == "IntegrityError":
        return "duplicate in the database (IntegrityError)"
    if name in _DATABASE_ERRORS:
        return f"database error ({name})"
    clue = _safe_clue(str(error))
    if clue and clue != name:
        return f"{clue} ({name})"
    return name


def user_facing_error(error: BaseException, body: dict | None = None, *, ref: str = "") -> str:
    """Notice a person can read to an admin. The exception text stays in the log.

    The notice does not depend on the process log level. It names the failure
    and a code that is also written on the Handler error log line.
    """
    actions = (body or {}).get("actions") or []
    action = actions[0] if actions and isinstance(actions[0], dict) else {}
    control = ((action.get("text") or {}).get("text") or "").strip() or (action.get("action_id") or "").strip()
    if not control:
        view = (body or {}).get("view") or {}
        control = (view.get("callback_id") or "").strip() if isinstance(view, dict) else ""
    where = f" ({control})" if control else ""
    lines = [f"Something went wrong: {_failure_clue(error)}{where}."]
    if ref:
        lines.append(f"Tell an admin this code: {ref}.")
        lines.append("Search the Slackblast CloudWatch logs for that code.")
    return " ".join(lines)


def send_error_response(body: dict, client: WebClient, error: str) -> None:
    error_form = copy.deepcopy(forms.ERROR_FORM)
    error_msg = constants.ERROR_FORM_MESSAGE_TEMPLATE.format(error=error)
    error_form.set_initial_values({actions.ERROR_FORM_MESSAGE: error_msg})

    view_id = safe_get(body, actions.LOADING_ID) or safe_get(body, "view", "id")
    user_id = safe_get(body, "user", "id")
    if not view_id and not user_id:
        logger.error("Slackblast error with no user to notify: %s", error)
        return
    if view_id:
        error_form.update_modal(
            client=client,
            view_id=view_id,
            title_text="Slackblast Error",
            submit_button_text="None",
            callback_id="error-id",
        )
    if user_id:
        blocks = [block.as_form_field() for block in error_form.blocks]
        client.chat_postMessage(channel=user_id, text=error, blocks=blocks)
