import json
import logging
import re
from dataclasses import dataclass

_LOG = logging.getLogger(__name__)

# Same id check as slackblast.utilities.helper_functions.slack_request_context.
# The two apps package separately, so the helper lives in each one.
_CONTEXT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_CHANNEL_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SLACK_CHANNEL_ID = re.compile(r"^[CDG][A-Z0-9]{8,}$")
_METADATA_CHANNEL_KEYS = ("channel_id", "ao_channel_id", "strava-channel-id")
_METADATA_TS_KEYS = ("message_ts", "strava-ts")
_METADATA_EXTRA_KEYS = (
  ("event_id", "event_id"),
  ("strava-activity-id", "strava_activity_id"),
)
_CONTEXT_FIELD_ORDER = (
  "channel_id",
  "channel_name",
  "message_ts",
  "view_id",
  "event_id",
  "strava_activity_id",
)


def _context_id(value) -> str:
  if value is None or isinstance(value, (dict, list, bool)):
    return ""
  text = str(value).strip()
  return text if _CONTEXT_ID.fullmatch(text) else ""


def _json_object(value) -> dict:
  if isinstance(value, dict):
    return value
  if not isinstance(value, str) or not value or value[0] not in "{[":
    return {}
  try:
    parsed = json.loads(value)
  except (TypeError, ValueError):
    return {}
  return parsed if isinstance(parsed, dict) else {}


def slack_request_context(payload) -> dict:
  """Channel, post timestamp, and modal id. Skips form text and tokens."""
  if not isinstance(payload, dict):
    return {}
  channel = payload.get("channel")
  if isinstance(channel, dict):
    channel_id = _context_id(channel.get("id"))
  else:
    channel_id = _context_id(channel)
  container = payload.get("container") if isinstance(payload.get("container"), dict) else {}
  event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
  event_channel = event.get("channel")
  if isinstance(event_channel, dict):
    event_channel_id = _context_id(event_channel.get("id"))
  else:
    event_channel_id = _context_id(event_channel) or _context_id(event.get("channel_id"))
  view = payload.get("view") if isinstance(payload.get("view"), dict) else {}
  message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
  actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
  action = actions[0] if actions and isinstance(actions[0], dict) else {}
  blobs = (_json_object(view.get("private_metadata")), _json_object(action.get("value")))

  def from_blobs(keys) -> str:
    for blob in blobs:
      for key in keys:
        found = _context_id(blob.get(key))
        if found:
          return found
    return ""

  channel_id = (
    _context_id(payload.get("channel_id"))
    or channel_id
    or _context_id(container.get("channel_id"))
    or event_channel_id
    or from_blobs(_METADATA_CHANNEL_KEYS)
  )
  action_value = _context_id(action.get("value"))
  if not channel_id and _SLACK_CHANNEL_ID.fullmatch(action_value or ""):
    channel_id = action_value

  message_ts = (
    _context_id(container.get("message_ts"))
    or _context_id(message.get("ts"))
    or _context_id(payload.get("message_ts"))
    or from_blobs(_METADATA_TS_KEYS)
  )
  if not message_ts and event.get("type") in {"message", "app_mention"}:
    message_ts = _context_id(event.get("ts"))

  view_id = _context_id(view.get("id")) or _context_id(container.get("view_id"))
  fields = {
    "channel_id": channel_id,
    "message_ts": message_ts,
    "view_id": view_id,
  }
  for source_key, log_key in _METADATA_EXTRA_KEYS:
    fields[log_key] = from_blobs((source_key,))
  channel_name = payload.get("channel_name")
  if isinstance(channel_name, str) and _CHANNEL_NAME.fullmatch(channel_name):
    fields["channel_name"] = channel_name
  return {key: fields[key] for key in _CONTEXT_FIELD_ORDER if fields.get(key)}


def format_slack_request_context(payload) -> str:
  return " ".join(f"{key}={value}" for key, value in slack_request_context(payload).items())


def format_log_fields(fields) -> str:
  """key=value pairs. Skips missing values instead of printing blanks."""
  parts = []
  for key, value in fields.items():
    if value is None:
      continue
    text = str(value).strip()
    if text:
      parts.append(f"{key}={text}")
  return " ".join(parts)


def _actor_id(payload) -> str:
  if not isinstance(payload, dict):
    return ""
  user = payload.get("user")
  if isinstance(user, dict):
    found = user.get("id") or ""
  elif isinstance(user, str):
    found = user
  else:
    found = ""
  event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
  event_user = event.get("user")
  if isinstance(event_user, dict):
    event_user = event_user.get("id") or ""
  elif not isinstance(event_user, str):
    event_user = ""
  return str(payload.get("user_id") or found or event_user or "").strip()


def log_slack_request(logger, payload):
  """Log who did what, plus channel, post, and modal ids. Never the request body."""
  if not isinstance(payload, dict):
    logger.info("slack request")
    return
  event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
  actions = payload.get("actions") or []
  action = actions[0] if actions and isinstance(actions[0], dict) else {}
  view = payload.get("view") if isinstance(payload.get("view"), dict) else {}
  context = format_slack_request_context(payload)
  fields = format_log_fields(
    {
      "type": payload.get("type") or event.get("type") or "",
      "team_id": payload.get("team_id") or "",
      "user_id": _actor_id(payload),
      "action_id": action.get("action_id") or "",
      "callback_id": view.get("callback_id") or "",
      "event_type": event.get("type") or "",
    }
  )
  logger.info("%s", " ".join(part for part in ("slack request", fields, context) if part))


def report_unhandled_error(logger, client, body, error) -> None:
  """CloudWatch line plus a short PAXMiner log-channel note. Never raises."""
  payload = body if isinstance(body, dict) else {}
  context = format_slack_request_context(payload)
  fields = format_log_fields({"user_id": _actor_id(payload)})
  detail = " ".join(part for part in (fields, context) if part)
  logger.error(
    "Unhandled QSignups error%s: %s",
    f" {detail}" if detail else "",
    error,
    exc_info=True,
  )
  clue = type(error).__name__
  rows = [f"What: {clue}"]
  if fields:
    for piece in fields.split():
      if "=" in piece:
        key, value = piece.split("=", 1)
        if key == "user_id" and value:
          rows.append(f"User: {value}")
  for piece in context.split():
    if piece.startswith("channel_id=") and piece.split("=", 1)[1]:
      rows.append(f"Channel: {piece.split('=', 1)[1]}")
    elif piece.startswith("view_id=") and piece.split("=", 1)[1]:
      rows.append(f"View: {piece.split('=', 1)[1]}")
  text = "*QSignups* error.\n```\n" + "\n".join(rows) + "\n```"
  try:
    client.chat_postMessage(channel="paxminer_logs", text=text)
  except Exception:
    logger.warning("PAXMiner log channel post failed")


def safe_get(data, *keys):
  try:
    result = data
    for k in keys:
      if result.get(k):
        result = result[k]
      else:
        return None
    return result
  except KeyError:
    return None

def list_to_dict(l, fn):
  result = {}
  for i in (l or []):
    key = fn(i)
    if not result.get(key): result[key] = []
    result[key].append(i)
  return result

@dataclass
class User:
  id: str
  name: str
  email: str | None = None
  is_admin: bool = False

def get_user(user_id, client) -> User | None:
  user_info_dict = client.users_info(user=user_id)
  _LOG.debug("users_info user_id=%s ok=%s", user_id, user_info_dict.get("ok") if isinstance(user_info_dict, dict) else None)
  if not safe_get(user_info_dict, "user"):
    return None
  u = user_info_dict.get("user") or {}
  user_name = safe_get(user_info_dict, 'user', 'profile', 'display_name') or \
              safe_get(user_info_dict, 'user', 'profile', 'real_name') or None
  display = user_name if user_name else user_id
  is_admin = bool(
      u.get("is_admin") or u.get("is_owner") or u.get("is_primary_owner")
  )
  return User(
      id=user_id,
      name=display,
      email=safe_get(user_info_dict, 'user', 'profile', 'email'),
      is_admin=is_admin,
  )
