#!/usr/bin/env python3
"""Print image refs to docker-pull so a PAXMiner build can reuse layers.

The shared repository is empty on the first cutover, so the legacy
per-function repositories are checked too. Missing repositories are skipped.
"""

from __future__ import annotations

import json
import subprocess
import sys


def newest(repo: str, prefix: str, region: str) -> str | None:
    try:
        raw = subprocess.check_output(
            [
                "aws",
                "ecr",
                "describe-images",
                "--repository-name",
                repo,
                "--region",
                region,
                "--output",
                "json",
            ],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    best: tuple[str, str] | None = None
    for image in json.loads(raw).get("imageDetails") or []:
        tags = image.get("imageTags") or []
        match = next((tag for tag in tags if tag.startswith(prefix)), None)
        if not match:
            continue
        pushed = str(image.get("imagePushedAt") or "")
        if best is None or pushed > best[0]:
            best = (pushed, match)
    return None if best is None else best[1]


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: paxminer_warm_ecr_cache.py BASE STAGE REGION", file=sys.stderr)
        return 2
    base, stage, region = sys.argv[1], sys.argv[2], sys.argv[3]
    namespace = base.rsplit("/", 1)[-1]
    seen: set[str] = set()
    for repo, prefix, uri in (
        (f"{namespace}/paxminer", "syncfunction", f"{base}/paxminer"),
        (f"{namespace}/paxminer", "slackfunction", f"{base}/paxminer"),
        (f"{namespace}/paxminer-{stage}-sync", "syncfunction", f"{base}/paxminer-{stage}-sync"),
        (f"{namespace}/paxminer-{stage}-slack", "slackfunction", f"{base}/paxminer-{stage}-slack"),
    ):
        tag = newest(repo, prefix, region)
        if not tag:
            continue
        ref = f"{uri}:{tag}"
        if ref not in seen:
            seen.add(ref)
            print(ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
