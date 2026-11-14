import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "slackblast"))

from utilities.slack import actions, forms


def test_slackblast_settings_has_no_paxminer_button_or_hint():
    labels = [
        getattr(element, "label", "")
        for block in forms.CONFIG_FORM.blocks
        for element in getattr(block, "elements", [])
    ]
    assert labels == [
        ":gear: General Settings",
        ":email: Email Settings",
        ":bar_chart: Custom Field Settings",
        ":speech_balloon: Welcomebot Settings",
    ]
    text = " ".join(
        str(getattr(getattr(block, "element", None), "initial_value", "") or "")
        for block in forms.CONFIG_FORM.blocks
    )
    assert "PAXMiner Settings" not in " ".join(labels)
    assert "/config-paxminer" not in text
    assert not hasattr(actions, "CONFIG_PAXMINER_SETTINGS")
