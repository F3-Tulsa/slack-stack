import logging
from typing import Optional

from sqlalchemy import text

from data import database_schema, site_q_user_id
from database import DbManager, get_engine
from database.orm import Weekly, Master, AO
from utilities import safe_get
from . import UpdateResponse

_LOG = logging.getLogger(__name__)


def _schema_ready() -> bool:
    try:
        database_schema()
    except RuntimeError:
        return False
    return True


def get_site_q(ao_channel_id: Optional[str]) -> Optional[str]:
    """Read site_q_user_id from aos in DATABASE_SCHEMA."""
    if not ao_channel_id or not _schema_ready():
        return None
    try:
        with get_engine().connect() as conn:
            return site_q_user_id(conn, ao_channel_id)
    except Exception:
        _LOG.exception("get_site_q failed channel_id=%s", ao_channel_id)
        return None


def set_site_q(ao_channel_id: Optional[str], site_q_user_id: Optional[str]) -> None:
    """Write site_q_user_id on aos; no-op if DATABASE_SCHEMA is unset or channel missing."""
    if not ao_channel_id or not _schema_ready():
        return
    sql = text("UPDATE aos SET site_q_user_id = :uid WHERE channel_id = :ch")
    try:
        with get_engine().begin() as conn:
            conn.execute(sql, {"uid": site_q_user_id, "ch": ao_channel_id})
    except Exception:
        _LOG.exception("set_site_q failed channel_id=%s", ao_channel_id)
        raise


def edit(client, user_id, team_id, logger, ao_channel_id, input_data) -> UpdateResponse:

    # Parse inputs
    ao_display_name = input_data["ao_display_name"]["ao_display_name"]["value"]
    ao_location_subtitle = input_data["ao_location_subtitle"]["ao_location_subtitle"][
        "value"
    ]
    site_q_user_id = safe_get(
        input_data, "site_q_user_id", "site_q_user_id", "selected_user"
    )

    # Attempt updates
    try:
        DbManager.update_records(
            cls=AO,
            filters=[AO.ao_channel_id == ao_channel_id],
            fields={
                AO.ao_display_name: ao_display_name,
                AO.ao_location_subtitle: ao_location_subtitle,
            },
        )
        set_site_q(ao_channel_id, site_q_user_id)
        return UpdateResponse(success=True, message=":white_check_mark: Locked in—the Weinke has been updated!")
    except Exception as e:
        logger.error(f"Error updating: {e}")
        return UpdateResponse(
            success=False,
            message=f"Uh-oh, something broke out in the Gloom! Please try again or contact your Weasel Shaker. Errors:\n{e}",
        )


def delete(client, user_id, team_id, logger, ao_channel_id) -> UpdateResponse:

    # Attempt deletion
    try:
        DbManager.delete_records(
            cls=AO, filters=[AO.ao_channel_id == ao_channel_id]
        )
        DbManager.delete_records(
            cls=Weekly, filters=[Weekly.ao_channel_id == ao_channel_id]
        )
        DbManager.delete_records(
            cls=Master, filters=[Master.ao_channel_id == ao_channel_id]
        )
        return UpdateResponse(success=True, message=":white_check_mark: Locked in—the Weinke has been updated!")
    except Exception as e:
        logger.error(f"Error deleting AO: {e}")
        return UpdateResponse(
            success=False,
            message=f"Uh-oh, something broke out in the Gloom! Please try again or contact your Weasel Shaker. Errors:\n{e}",
        )


def insert(client, user_id, team_id, logger, input_data) -> UpdateResponse:

    # Parse inputs
    ao_channel_id = safe_get(
        input_data, "add_ao_channel_select", "add_ao_channel_select", "selected_channel"
    )
    ao_display_name = safe_get(input_data, "ao_display_name", "ao_display_name", "value")
    ao_location_subtitle = safe_get(
        input_data, "ao_location_subtitle", "ao_location_subtitle", "value"
    )
    site_q_user_id = safe_get(
        input_data, "site_q_user_id", "site_q_user_id", "selected_user"
    )

    # replace double quotes with single quotes
    ao_display_name = ao_display_name.replace('"', "'")
    if ao_location_subtitle:
        ao_location_subtitle = ao_location_subtitle.replace('"', "'")
    else:
        ao_location_subtitle = ""  # TODO: I don't like this, but this field is currently non-nullable

    # Attempt insert
    try:
        DbManager.create_record(
            AO(
                ao_channel_id=ao_channel_id,
                ao_display_name=ao_display_name,
                ao_location_subtitle=ao_location_subtitle,
                team_id=team_id,
            )
        )
        set_site_q(ao_channel_id, site_q_user_id)
        return UpdateResponse(success=True, message=":white_check_mark: Locked in—the Weinke has been updated!")
    except Exception as e:
        logger.error(f"Error inserting: {e}")
        return UpdateResponse(
            success=False,
            message=f"Uh-oh, something broke out in the Gloom! Please try again or contact your Weasel Shaker. Errors:\n{e}",
        )
