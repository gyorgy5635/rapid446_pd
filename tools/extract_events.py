#!/usr/bin/env python3
"""Turn a MADSci experiment script into a labware-movement event log.

Reads full_run.py with the Python AST (it is never executed), follows every
submit_workflow() call in order, expands the referenced workflow YAMLs into
atomic steps, and tracks which plate sits where so each move names a plate.

Usage:
    python3 -I tools/extract_events.py --app protocols/<v>/protocol --config protocols/<v>/config --out protocols/<v>/viz/events.json
"""
import argparse
import ast
import datetime as dt
import json
import re
import statistics
from collections import defaultdict
from difflib import SequenceMatcher
import sys
from pathlib import Path

import yaml

FLEX_MOVE_RE = re.compile(r"pcr_([A-D]\d)_to_([A-D]\d)\.py$")
PHASE_RE = re.compile(r"^\s*#{2,}\s*([A-Z][A-Z \-]{2,}?)\s*$")
NOISE_RE = re.compile(r"WORKING|TIPS USED|COMBO|^\s*#+\s*(OT2|FLEX|\d|[A-Z ]+:\s*\d)|^\s*#+\s*$|TODO|STARTING TIP", re.I)
DELAY_RE = re.compile(r"^[^#\n]*\bdelay\(\s*(minutes|seconds)\s*=\s*([\d.]+)", re.M)

PF400 = "pf400_piper"
FLEX = "otflex_sandy"
FLEX_PREFIX = "otflex_sandy.deck_nest_"
FLEX_HANDOFF = FLEX_PREFIX + "A4"   # the only Flex slot the PF400 serves; the Flex gripper moves plates on from here


def call_name(node):
    """Return 'a.b.c' for a Call's func, or ''."""
    f = node.func if isinstance(node, ast.Call) else node
    parts = []
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return ".".join(reversed(parts))


def const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class Extractor:
    def __init__(self, app: Path, config: Path):
        self.app = app
        self.src_path = app / "src" / "full_run.py"
        self.src = self.src_path.read_text()
        self.lines = self.src.splitlines()
        self.plates_cfg = json.loads((config / "plates.json").read_text())
        self.dur = json.loads((config / "durations.json").read_text())
        layout = json.loads((config / "layout.json").read_text())
        src_cfg = config / "source.json"
        self.source = json.loads(src_cfg.read_text()) if src_cfg.exists() else {}
        self.aliases = layout.get("aliases", {})

        self.paths = {}       # variable -> relative file path (e.g. workflows/transfers/x.yaml)
        self.payload = {}     # payload key -> relative file path
        self.env = {}         # other variables -> relative file path
        self.state = {}       # canonical location -> plate id
        self.plates = []
        self.steps = []
        self.calls = []
        self.warnings = []
        self.phase = "Setup"
        self.seen_workflow = False
        self.bookkeeping = 0
        self.prev_end = 0
        self.loc_use = {}

    # ---------- helpers ----------
    def canon(self, loc):
        return self.aliases.get(loc, loc)

    def warn(self, line, msg):
        self.warnings.append({"line": line, "message": msg})

    def comments_between(self, start, end):
        """Comment lines in source lines (start, end) exclusive, 1-indexed."""
        out = []
        for ln in range(start + 1, end):
            text = self.lines[ln - 1]
            if text.strip().startswith("#"):
                out.append((ln, text))
        return out

    def path_expr(self, node):
        """Resolve `dir / "file"` (possibly parenthesised) to a relative path."""
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            name = const_str(node.right)
            base = node.left.id if isinstance(node.left, ast.Name) else None
            folder = {"run_directory": "workflows/run_instrument",
                      "transfers_directory": "workflows/transfers",
                      "protocol_directory": "protocols"}.get(base)
            if name and folder:
                return f"{folder}/{name}"
        return None

    def resolve(self, node):
        if isinstance(node, ast.Name):
            return self.paths.get(node.id) or self.env.get(node.id)
        if isinstance(node, ast.Subscript) and call_name(node.value) == "payload":
            return self.payload.get(const_str(node.slice))
        if isinstance(node, ast.Call) and call_name(node).endswith(".resolve"):
            return self.resolve(node.func.value)
        if isinstance(node, ast.Call) and call_name(node).endswith("generate_ot2_protocol"):
            return self.resolve(node.args[0])
        return None

    def new_plate(self, loc, line, comment):
        cfg = self.plates_cfg.get(loc, {})
        pid = f"p{len(self.plates) + 1}"
        self.plates.append({
            "id": pid,
            "name": cfg.get("name") or comment or f"Plate at {loc}",
            "short": cfg.get("short") or pid.upper(),
            "kind": cfg.get("kind", "pcr"),
            "color": cfg.get("color", 0),
            "start": self.canon(loc),
            "line": line,
        })
        self.state[self.canon(loc)] = pid
        return pid

    # ---------- statement walk ----------
    def run(self):
        tree = ast.parse(self.src)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_experiment")
        self.prev_end = fn.lineno
        self.walk(fn.body)
        self.check_unused_assignments()
        return self.result()

    def walk(self, body):
        for stmt in body:
            comments = self.comments_between(self.prev_end, stmt.lineno)
            for ln, text in comments:
                m = PHASE_RE.match(text)
                if m:
                    self.phase = " ".join(w.upper() if len(w) <= 3 else w.title()
                                          for w in m.group(1).split()).replace("FD GLU", "FDGlu")
            caption = [t.strip().lstrip("#").strip() for ln, t in comments
                       if not NOISE_RE.search(t) and not PHASE_RE.match(t)]
            self.caption = caption[-1] if caption else ""
            self.prev_end = getattr(stmt, "end_lineno", stmt.lineno)
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                self.warn(stmt.lineno, f"{type(stmt).__name__} block: branches/loops are expanded once, in source order")
                self.prev_end = stmt.lineno
                self.walk(stmt.body)
                continue
            self.statement(stmt)

    def statement(self, stmt):
        value = stmt.value if isinstance(stmt, (ast.Assign, ast.Expr)) else None
        if value is None:
            return
        # variable = dir / "file"
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            tgt = stmt.targets[0]
            p = self.path_expr(value)
            if isinstance(tgt, ast.Name) and p:
                self.paths[tgt.id] = p
                self.check_flex_name(tgt.id, p, stmt.lineno)
                return
            if isinstance(tgt, ast.Subscript) and call_name(tgt.value) == "payload":
                r = self.resolve(value)
                if r:
                    self.payload[const_str(tgt.slice)] = r
                return
            if isinstance(tgt, ast.Name) and isinstance(value, ast.Call) and call_name(value).endswith("generate_ot2_protocol"):
                self.env[tgt.id] = self.resolve(value)
                return
        if not isinstance(value, ast.Call):
            return
        name = call_name(value)
        if name.endswith("submit_workflow"):
            self.submit(value, stmt.lineno)
        elif name.endswith("push_new_assay_plate_resource"):
            loc = next((const_str(k.value) for k in value.keywords if k.arg == "location_name"), None)
            if not self.seen_workflow:
                comment = self.caption
                self.new_plate(loc, stmt.lineno, comment)
            else:
                self.bookkeeping += 1
        elif name.endswith("pop_assay_plate_resource"):
            self.bookkeeping += 1
        elif name == "input":
            msg = const_str(value.args[0]) if value.args else "Paused"
            self.add_step(stmt.lineno, None, kind="pause", mover="human", detail=msg,
                          duration=self.dur["manual_pause"], dsrc="estimate")

    def check_flex_name(self, var, path, line):
        m_var = re.match(r"([A-D]\d)_to_([A-D]\d)$", var)
        m_file = FLEX_MOVE_RE.search(path)
        if m_var and m_file and m_var.groups() != m_file.groups():
            self.warn(line, f"Variable {var} points at {Path(path).name} (moves {m_file.group(1)}→{m_file.group(2)}, not {m_var.group(1)}→{m_var.group(2)})")

    def check_unused_assignments(self):
        pass

    # ---------- workflows ----------
    def submit(self, call, line):
        self.seen_workflow = True
        wf = self.resolve(call.args[0]) if call.args else None
        if not wf:
            self.warn(line, "submit_workflow with an argument this tool could not resolve")
            return
        files = {}
        for kw in call.keywords:
            if kw.arg == "file_inputs" and isinstance(kw.value, ast.Dict):
                for k, v in zip(kw.value.keys, kw.value.values):
                    files[const_str(k)] = self.resolve(v)
        wf_path = self.app / wf
        if not wf_path.exists():
            self.warn(line, f"Workflow file not found: {wf}")
            return
        doc = yaml.safe_load(wf_path.read_text()) or {}
        call_id = len(self.calls)
        self.calls.append({"id": call_id, "workflow": Path(wf).name, "wf_name": doc.get("name", ""), "line": line,
                           "sig": [[st.get("node"), st.get("action")] for st in doc.get("steps") or []],
                           "phase": self.phase, "caption": self.caption,
                           "info": (doc.get("metadata") or {}).get("info", "")})
        for s in doc.get("steps") or []:
            self.expand_step(call_id, line, s, files)

    def expand_step(self, call_id, line, s, files):
        node, action = s.get("node"), s.get("action")
        locs = s.get("locations") or {}
        args = s.get("args") or {}
        if node == PF400 and action == "transfer":
            self.move(call_id, line, locs.get("source"), locs.get("target"), mover="pf400")
            return
        if action == "run_protocol" and node in ("ot2_patrick", FLEX):
            key = next(iter((s.get("files") or {}).values()), None)
            proto = files.get(key)
            if not proto:
                self.warn(line, f"{node} run_protocol with unresolved protocol file")
                proto = "unknown"
            pname = Path(proto).name
            delay, dsrc = self.protocol_delay(proto)
            m = FLEX_MOVE_RE.search(pname)
            if node == FLEX and m:
                src, dst = FLEX_PREFIX + m.group(1), FLEX_PREFIX + m.group(2)
                self.move(call_id, line, src, dst, mover="flex_gripper", protocol=pname,
                          extra=delay, extra_src=dsrc)
                return
            est = self.dur["protocols"].get(pname, self.dur["protocols"]["_default"])
            label = self.dur.get("protocol_labels", {}).get(pname, pname)
            deck = sorted(p for loc, p in self.state.items() if loc.startswith(node))
            self.add_step(line, call_id, kind="protocol", mover=node, node=node, action="run_protocol",
                          protocol=pname, detail=label, plates=deck,
                          duration=est + delay, dsrc="code" if delay else "estimate")
            return
        # any other instrument action
        argstr = " ".join(f"{k}={v}" for k, v in args.items() if k != "plate_type")
        key = f"{node}.{action}" + (f" {argstr}" if argstr else "")
        dur = self.dur["actions"].get(key, self.dur["actions"].get(f"{node}.{action}", 30))
        self.add_step(line, call_id, kind="action", mover=node, node=node, action=action,
                      detail=(s.get("name") or action) + (f" ({argstr})" if argstr else ""),
                      duration=dur, dsrc="estimate")

    def protocol_delay(self, proto):
        p = self.app / proto
        if not p.exists():
            return 0, None
        total = 0
        for unit, val in DELAY_RE.findall(p.read_text()):
            total += float(val) * (60 if unit == "minutes" else 1)
        return int(total), ("code" if total else None)

    def move(self, call_id, line, src, dst, mover, protocol=None, extra=0, extra_src=None):
        csrc, cdst = self.canon(src), self.canon(dst)
        if mover == "pf400" and FLEX_HANDOFF not in (csrc, cdst) and any(x.startswith(FLEX_PREFIX) for x in (csrc, cdst)):
            self.warn(line, f"PF400 move {src} → {dst} uses a Flex slot other than the A4 handoff")
        for raw, c in ((src, csrc), (dst, cdst)):
            u = self.loc_use.setdefault(raw, {"name": raw, "canonical": c, "uses": 0, "movers": []})
            u["uses"] += 1
            if mover not in u["movers"]:
                u["movers"].append(mover)
        plate = self.state.pop(csrc, None)
        if plate is None:
            self.warn(line, f"Move from {src} but no tracked plate is there; created a placeholder")
            plate = self.new_plate(csrc, line, f"Unknown plate at {src}")
            self.state.pop(csrc, None)
        if cdst in self.state:
            self.warn(line, f"Move to {dst} but {self.name(self.state[cdst])} is already there")
        self.state[cdst] = plate
        base = self.dur["transfer"] if mover == "pf400" else self.dur["flex_gripper_move"]
        self.add_step(line, call_id, kind="move", mover=mover, src=src, dst=dst,
                      from_=csrc, to=cdst, plate=plate, protocol=protocol,
                      detail=f"{self.name(plate)}: {src} → {dst}",
                      duration=base + extra, dsrc=extra_src or "estimate",
                      hold=extra,
                      hold_note=(f"protocol.delay() of {extra // 60} min inside {protocol}" if extra else None))

    def name(self, pid):
        return next((p["name"] for p in self.plates if p["id"] == pid), pid)

    def add_step(self, line, call_id, kind, mover, duration, dsrc, detail="", **kw):
        step = {"i": len(self.steps), "phase": self.phase, "call": call_id, "line": line,
                "kind": kind, "mover": mover, "detail": detail,
                "duration_s": int(duration), "duration_source": dsrc}
        for k, v in kw.items():
            if v is not None:
                step["from" if k == "from_" else k] = v
        if kind == "pause":
            step["phase"] = self.phase
        self.steps.append(step)

    def result(self):
        final = {loc: pid for loc, pid in self.state.items()}
        moves = [s for s in self.steps if s["kind"] == "move"]
        phases = []
        for s in self.steps:
            if not phases or phases[-1]["name"] != s["phase"]:
                phases.append({"name": s["phase"], "first": s["i"], "last": s["i"]})
            phases[-1]["last"] = s["i"]
        return {
            "meta": {
                "version": self.source.get("name", ""),
                "title": self.source.get("title", ""),
                "source": " @ ".join(x for x in (self.source.get("repo"), self.source.get("branch"),
                                                  (self.source.get("commit") or "")[:7]) if x) or "local",
                "derived_from": self.source.get("derived_from"),
                "script_url": (self.source["repo_blob_url"] + "/src/full_run.py") if self.source.get("repo_blob_url") else None,
                "generated": dt.datetime.now().isoformat(timespec="seconds"),
                "workflow_calls": len(self.calls),
                "steps": len(self.steps),
                "pf400_moves": sum(1 for s in moves if s["mover"] == "pf400"),
                "flex_gripper_moves": sum(1 for s in moves if s["mover"] == "flex_gripper"),
                "resource_bookkeeping_calls_ignored": self.bookkeeping,
                "estimated_total_s": sum(s["duration_s"] for s in self.steps),
            },
            "plates": self.plates,
            "phases": phases,
            "calls": self.calls,
            "steps": self.steps,
            "final_state": final,
            "locations": sorted(self.loc_use.values(), key=lambda u: u["name"]),
            "warnings": self.warnings,
        }


# ---------------- MADSci history -> measured durations ----------------
def _ts(x):
    if not x:
        return None
    try:
        return dt.datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso_dur(x):
    """Parse an ISO 8601 duration such as PT1H2M3.5S (how pydantic serialises timedelta)."""
    if isinstance(x, (int, float)):
        return float(x)
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", str(x or ""))
    if not m or not any(m.groups()):
        return None
    d, h, mi, se = (float(g) if g else 0 for g in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def _step_seconds(st):
    a, b = _ts(st.get("start_time")), _ts(st.get("end_time"))
    if a and b:
        return (b - a).total_seconds()
    return _iso_dur(st.get("duration"))


def _wf_ok(w):
    stt = w.get("status") or {}
    if isinstance(stt, dict):
        return not (stt.get("failed") or stt.get("cancelled")) and _ts(w.get("start_time")) and _ts(w.get("end_time"))
    return str(stt).lower() in ("completed", "succeeded") and _ts(w.get("start_time"))


def load_history(paths):
    wfs = []
    for p in paths:
        data = json.loads(Path(p).read_text())
        wfs.extend(data.values() if isinstance(data, dict) else data)
    return wfs


def split_runs(wfs, gap_hours=12):
    """Group workflows into experiment runs: by experiment_id, then split on long idle gaps."""
    by_exp = defaultdict(list)
    for w in wfs:
        if _wf_ok(w):
            by_exp[((w.get("ownership_info") or {}).get("experiment_id")) or "(no experiment id)"].append(w)
    runs = []
    for eid, ws in by_exp.items():
        ws.sort(key=lambda w: _ts(w.get("start_time")))
        cur = [ws[0]]
        for w in ws[1:]:
            if (_ts(w["start_time"]) - _ts(cur[-1]["end_time"])).total_seconds() > gap_hours * 3600:
                runs.append((eid, cur)); cur = []
            cur.append(w)
        runs.append((eid, cur))
    return runs


def apply_history(res, paths, min_match=0.5):
    calls, steps = res["calls"], res["steps"]
    call_steps = defaultdict(list)
    for st in steps:
        call_steps[st["call"]].append(st)
    key = lambda name, sig: (name or "", tuple(tuple(x) for x in sig))
    call_keys = [key(c["wf_name"], c["sig"]) for c in calls]

    per_step = defaultdict(list)   # (call, k) -> [seconds]
    per_gap = defaultdict(list)    # call -> [seconds idle before it]
    used, report = 0, []
    for eid, ws in split_runs(load_history(paths)):
        hist_keys = [key(w.get("name"), [[s.get("node"), s.get("action")] for s in w.get("steps") or []]) for w in ws]
        blocks = SequenceMatcher(None, call_keys, hist_keys, autojunk=False).get_matching_blocks()
        pairs = [(b.a + j, b.b + j) for b in blocks for j in range(b.size)]
        frac = len(pairs) / len(calls)
        info = {"experiment_id": eid, "start": ws[0].get("start_time"), "workflows": len(ws),
                "matched_calls": len(pairs), "match": round(frac, 3), "used": frac >= min_match}
        report.append(info)
        if not info["used"]:
            continue
        used += 1
        prev = None
        for ci, hi in pairs:
            w = ws[hi]
            for k, hs in enumerate(w.get("steps") or []):
                sec = _step_seconds(hs)
                if sec is not None and k < len(call_steps[ci]):
                    per_step[(ci, k)].append(sec)
            if prev and prev[0] == ci - 1:
                per_gap[ci].append(max(0.0, (_ts(w["start_time"]) - _ts(ws[prev[1]]["end_time"])).total_seconds()))
            prev = (ci, hi)

    measured = 0
    for (ci, k), vals in per_step.items():
        st = call_steps[ci][k]
        st["duration_s"] = int(round(statistics.median(vals)))
        st["duration_source"] = "measured"
        st["measured_runs"] = len(vals)
        measured += 1
    # Idle time between workflows: manual pauses absorb it, otherwise it is shown as waiting time.
    for ci, vals in per_gap.items():
        gap = int(round(statistics.median(vals)))
        prev_call_last = call_steps[ci - 1][-1]["i"] if call_steps.get(ci - 1) else None
        first = call_steps[ci][0]
        pauses = [s for s in steps if prev_call_last is not None and prev_call_last < s["i"] < first["i"] and s["kind"] == "pause"]
        if pauses:
            for p in pauses:
                p["duration_s"] = gap // len(pauses); p["duration_source"] = "measured"; p["measured_runs"] = len(vals)
        elif gap > 0:
            first["wait_before_s"] = gap
    res["meta"]["timing"] = {"source": "MADSci archived workflows", "runs_used": used, "runs": report,
                             "measured_steps": measured, "min_match": min_match}
    res["meta"]["estimated_total_s"] = sum(s["duration_s"] + s.get("wait_before_s", 0) for s in steps)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", type=Path, required=True, help="folder holding src/, workflows/, protocols/")
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--history", type=Path, action="append", default=[],
                    help="MADSci archived-workflow JSON from export_madsci_history.py (repeatable)")
    ap.add_argument("--min-match", type=float, default=0.5,
                    help="use a run only if at least this fraction of the script's workflow calls line up with it")
    a = ap.parse_args()
    res = Extractor(a.app, a.config).run()
    if a.history:
        apply_history(res, a.history, a.min_match)
        t = res["meta"]["timing"]
        for r in t["runs"]:
            print(f"  run {r['experiment_id']} ({str(r['start'])[:16]}): {r['matched_calls']}/{len(res['calls'])} calls matched"
                  f"{'' if r['used'] else ' - not used'}", file=sys.stderr)
        print(f"  measured {t['measured_steps']}/{len(res['steps'])} steps from {t['runs_used']} run(s)", file=sys.stderr)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    m = res["meta"]
    print(f"{m['workflow_calls']} workflow calls -> {m['steps']} steps "
          f"({m['pf400_moves']} PF400 moves, {m['flex_gripper_moves']} Flex gripper moves); "
          f"est. {m['estimated_total_s'] / 3600:.1f} h", file=sys.stderr)
    for w in res["warnings"]:
        print(f"  warning line {w['line']}: {w['message']}", file=sys.stderr)


if __name__ == "__main__":
    main()
