"""Achievement rule definitions and seed data for achievements_list."""

from __future__ import annotations

import json
from pathlib import Path

# Rule columns: metric, activity, period, threshold
# metric: posts | qs | distinct_aos | posts_at_single_ao
# activity (list varchar): qsource | rucking | any | a Slackblast Event Type.
# beatdown on the list row is a legacy any-event sentinel, not Bootcamp.
# The version JSON column is the filter: NULL or {"include":[],"exclude":[]} = any event.
# Seeds store {include, exclude}; the list varchar is a lossy mirror (any/qsource/vN).
# period: week | month | year

_DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "achievement_defaults.json"


def _load_achievement_seeds() -> list[dict]:
    with _DEFAULTS_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("achievement_defaults.json must be a list of seed objects")
    return data


ACHIEVEMENT_SEEDS: list[dict] = _load_achievement_seeds()


RULE_COLUMNS = ("metric", "activity", "period", "threshold")

AWARDED_PERIOD_COLUMNS = (
    "achievement_version_id",
    "period",
    "period_key",
    "period_start",
    "period_end",
    "qualifying_count",
)
