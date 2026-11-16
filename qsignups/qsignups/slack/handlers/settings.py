from database import DbManager
from database.orm import Region
from slack import inputs
from . import UpdateResponse

def update(client, user_id, team_id, logger, input_data) -> UpdateResponse:
    updates = {
        Region.weekly_weinke_channel: inputs.WEINKIE_INPUT.get_selected_value(input_data),
        Region.signup_reminders: inputs.Q_REMINDER_RADIO.get_selected_value(input_data) == inputs.Q_REMINDER_ENABLED.value,
        Region.weekly_ao_reminders:  inputs.AO_REMINDER_RADIO.get_selected_value(input_data) == inputs.AO_REMINDER_ENABLED.value,
        Region.google_calendar_id: inputs.GOOGLE_CALENDAR_SELECT.get_selected_value(input_data),
        Region.timezone: inputs.TIMEZONE_SELECT.get_selected_value(input_data)
    }
    try:
        DbManager.update_record(Region, team_id, updates)
        return UpdateResponse(success = True)
    except Exception:
        logger.exception("Error writing settings")
        return UpdateResponse(
            success=False,
            message="Uh-oh, something broke out in the Gloom! Please try again or contact your Weasel Shaker.",
        )

