#!/usr/bin/env python3
"""Run a built player's JavaScript against a stub DOM and fail if it breaks.

Parsing a page only proves it is syntactically valid. This actually executes it, so a runtime
error part-way through start-up - which leaves the browser showing a half-built page and no
message - fails here instead. It also checks that the panels that should have content do.

Needs a Python with py-mini-racer (a V8 binding), not a browser:

    /tmp/otenv/bin/pip install py-mini-racer
    /tmp/otenv/bin/python tools/check_player.py                    # every version
    /tmp/otenv/bin/python tools/check_player.py --version full_protocol_24_3round

Exit status is non-zero if any page throws or comes up empty.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Enough of a browser for the page to start up: the point is to catch the page's own errors, so
# anything missing here is a gap in the stub, not a bug in the page.
STUB = """
const _els = {};
function _mk(id){ return { id, innerHTML:"", textContent:"", value:0, max:0, hidden:true,
  style:{ setProperty(){} }, dataset:{},
  classList:{ toggle(){}, add(){}, remove(){}, contains(){ return false; } },
  children:[], firstChild:{ textContent:"" },
  appendChild(c){ this.children.push(c); return c; },
  addEventListener(){}, querySelector(sel){ return _mk(sel); }, querySelectorAll(){ return []; },
  setAttribute(){}, getAttribute(){ return null; }, closest(){ return null; },
  matches(){ return false; }, scrollIntoView(){}, insertAdjacentHTML(){}, remove(){}, focus(){},
  cloneNode(){ return _mk(this.id); },
  getBoundingClientRect(){ return { width:100, height:100, left:0, top:0 }; } }; }
const document = { title:"", body:_mk("body"), documentElement:_mk("html"),
  getElementById:(id)=> _els[id] = _els[id] || _mk(id),
  createElement:(t)=> _mk(t), createElementNS:(ns,t)=> _mk(t),
  querySelector:(sel)=> _mk(sel), querySelectorAll:()=> [], addEventListener(){} };
const matchMedia = () => ({ matches:false, addEventListener(){}, addListener(){} });
const window = { matchMedia, addEventListener(){}, location:{ hash:"" }, devicePixelRatio:1 };
const location = { hash:"" }, history = { replaceState(){} };
const addEventListener = () => {};
const setInterval = () => 0, clearInterval = () => {}, setTimeout = () => 0, requestAnimationFrame = () => 0;
const localStorage = { getItem:()=> null, setItem(){}, removeItem(){} };
const navigator = { clipboard: { writeText(){} } };
const XMLSerializer = function(){ this.serializeToString = () => ""; };
const Image = function(){};
"""

# panel id -> what it means, for versions where it must not be empty
RUN_MAP_PANELS = {"stats": "the header counts", "legend": "the plate legend",
                  "steps": "the step list", "bands": "the phase bar"}


def run_page(html, panels):
    from py_mini_racer import MiniRacer
    script = re.search(r"<script[^>]*>(.*?)</script>", html, re.S)
    if not script:
        return ["no <script> found in the page"]
    ctx = MiniRacer()
    ctx.eval(STUB)
    try:
        ctx.eval(script.group(1))
    except Exception as exc:  # noqa: BLE001 - the whole point is to report whatever it threw
        return [f"threw while starting up: {str(exc).splitlines()[0][:200]}"]
    problems = []
    for panel, what in panels.items():
        size = int(ctx.eval(f'String((_els[{panel!r}]||{{innerHTML:""}}).innerHTML || "").length'))
        if size == 0:
            problems.append(f"{what} ({panel}) is empty")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="just this version (default: all of them)")
    ap.add_argument("--liquid", action="store_true", help="check the liquid-handling pages as well")
    a = ap.parse_args()

    versions = [REPO / "protocols" / a.version] if a.version else sorted(
        d for d in (REPO / "protocols").iterdir() if (d / "viz" / "pd_run_map.html").exists())
    failures = 0
    for base in versions:
        page = base / "viz" / "pd_run_map.html"
        if not page.exists():
            print(f"{base.name}: no run map built")
            continue
        problems = run_page(page.read_text(), RUN_MAP_PANELS)
        failures += bool(problems)
        print(f"{'FAIL' if problems else 'ok  '} {base.name} run map")
        for p in problems:
            print(f"       {p}")
        if a.liquid:
            pages = sorted((base / "viz" / "liquid").glob("*.html"))
            panels = {"index.html": {"tips": "the tip box table", "runs": "the run list"}}
            bad = [(p.name, run_page(p.read_text(),
                                     panels.get(p.name, {"labware": "the labware maps", "rows": "the command table"})))
                   for p in pages]
            bad = [(n, pr) for n, pr in bad if pr]
            failures += bool(bad)
            print(f"{'FAIL' if bad else 'ok  '} {base.name} liquid pages ({len(pages)})")
            for n, pr in bad:
                print(f"       {n}: {'; '.join(pr)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
