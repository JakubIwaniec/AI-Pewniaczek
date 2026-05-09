"""Back-fill df_li (lineup) feeds for every `(dataset_label, event_id)` in league_manifest."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "data_integrity_flashscore.py"
    # Same RAW layout as audits; covers domestic + UEFA + cups (not just static LEAGUES list).
    subprocess.run(
        [sys.executable, str(script), "--repair", "--repair-feeds", "li"],
        cwd=str(root),
        check=True,
    )


if __name__ == "__main__":
    main()
