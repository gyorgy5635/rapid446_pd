#!/usr/bin/env python3
"""Embed events.json and layout.json into the player template -> one self-contained HTML file.

Usage:
    python3 -I tools/build_player.py --events protocols/<v>/viz/events.json --layout protocols/<v>/config/layout.json \
        --template tools/player_template.html --out protocols/<v>/viz/pd_run_map.html
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--layout", type=Path, required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    def compact(path):
        # "</" would end the inline <script>; escape it.
        return json.dumps(json.loads(path.read_text()), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    html = a.template.read_text()
    for marker, path in (("/*__EVENTS__*/null", a.events), ("/*__LAYOUT__*/null", a.layout)):
        if marker not in html:
            raise SystemExit(f"marker {marker} missing from template")
        html = html.replace(marker, compact(path))
    a.out.write_text(html)
    print(f"wrote {a.out} ({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
