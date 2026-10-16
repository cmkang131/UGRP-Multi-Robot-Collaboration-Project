#!/usr/bin/env python3
"""Read-only current-stack preflight. Stdlib only; never imports a simulator.

JSON fields are evidence declarations, not independent runtime measurements.
Missing evidence blocks admission. A replay preserves its original stack and
is labelled separately from current compliance. See the experiment README.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CONTAINERS = ("runs", "episodes", "worlds", "results", "attempts")
UNKNOWN = "확인 안 됨"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError(f"nonfinite JSON number: {value}")
    return json.loads(path.read_text(), object_pairs_hook=unique, parse_constant=nonfinite)


def values_at(value, selector):
    """Explicit selectors only. Never use the first recursive matching key."""
    parts = selector.split(".")
    def visit(obj, index, path):
        if index == len(parts):
            return [(path, obj)]
        part = parts[index]
        if part == "*" and isinstance(obj, list):
            return [v for i, item in enumerate(obj) for v in visit(item, index+1, f"{path}[{i}]")]
        if isinstance(obj, dict) and part in obj:
            return visit(obj[part], index+1, f"{path}.{part}".lstrip("."))
        return []
    return visit(value, 0, "")


def records(document):
    """Check each queued run/world; parent declarations remain evidence too."""
    def walk(node, parents, label):
        children = []
        for key in CONTAINERS:
            if key not in node:
                continue
            items = node[key]
            if not isinstance(items, list) or not items or any(not isinstance(x, dict) for x in items):
                raise ValueError(f"{label}.{key}: expected a nonempty list of records")
            children.extend((item, f"{label}.{key}[{i}]") for i, item in enumerate(items))
        if not children:
            yield label, parents + [node]
        for child, name in children:
            yield from walk(child, parents + [node], name)
    yield from walk(document, [], "$")


def normalized(rule, value):
    # Booleans must never compare equal to integers (False == 0 in Python).
    if rule.get("value_type") == "int":
        if type(value) is int:
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        return value
    if rule.get("value_type") == "scenario_version" and isinstance(value, str):
        match = re.search(r"(?:^|_)(v\d+)$", value)
        return match.group(1) if match else value
    return rule.get("aliases", {}).get(value, value) if isinstance(value, (str, int, float, bool)) else value


def equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def matches(rule, value):
    if rule["current"] == UNKNOWN:
        return False
    expected = rule.get("allowed", []) if rule.get("operator") == "one_of" else [rule["current"]]
    return any(equal(value, item) for item in expected)


def approvals(chain, rules):
    result = {}
    for doc in chain:
        entries = doc.get("stack_deviations", [])
        if not isinstance(entries, list):
            raise ValueError("stack_deviations must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("deviation must be an object")
            key, approval = entry.get("id"), entry.get("approval", {})
            if key not in rules or key in result:
                raise ValueError(f"unknown/duplicate deviation id: {key}")
            if (not isinstance(entry.get("reason"), str) or not entry["reason"].strip()
                    or not isinstance(approval, dict)
                    or approval.get("authority") not in ("user", "coordinator")
                    or not isinstance(approval.get("evidence"), str) or not approval["evidence"].strip()):
                raise ValueError(f"{key}: reason + user/coordinator approval evidence required")
            result[key] = entry
    return result


def xml_evidence(path):
    """Only explicit XML attributes; textures alone cannot identify a version."""
    root = ET.parse(path).getroot()
    if root.tag != "mujoco":
        raise ValueError(f"{path}: expected mujoco XML")
    result, checks = {}, []
    option = root.find("option")
    if option is not None:
        if "noslip_iterations" in option.attrib:
            result["noslip_iterations"] = option.get("noslip_iterations")
        for key, expected in (("cone", "elliptic"), ("integrator", "implicitfast"), ("impratio", "5")):
            actual = option.get(key)
            # Numeric XML formatting (5 vs 5.0) does not change this option.
            ok = actual == expected
            if key == "impratio" and actual is not None:
                ok = float(actual) == float(expected)
            checks.append(dict(id="contact_profile", field=f"XML.option.{key}",
                               expected=expected, observed=actual,
                               status="current" if ok else "unknown" if actual is None else "deviation"))
    else:
        checks.append(dict(id="contact_profile", field="XML.option", expected="explicit native options",
                           observed=None, status="unknown"))
    if option is None or "noslip_iterations" not in option.attrib:
        checks.append(dict(id="noslip_iterations", field="XML.option.noslip_iterations", expected=0,
                           observed=None, status="unknown"))
    if root.findall(".//include"):
        checks.append(dict(id="scene_profile", field="XML.include", expected="resolved standalone XML",
                           observed="unresolved includes", status="unknown"))
    else:
        welds = root.findall("./equality/weld")
        result["weld"] = any(w.get("active", "true").lower() not in ("false", "0") for w in welds)
    profile = root.find("./custom/text[@name='scene_profile']")
    if profile is not None:
        result["scene_profile"] = profile.get("data")
    return result, checks


def check_document(document, stack, *, flow=None, xmls=()):
    if not isinstance(document, dict):
        raise ValueError("manifest/summary/queue must be a JSON object")
    rules = {r["id"]: r for r in stack["rules"]}
    if len(rules) != len(stack["rules"]):
        raise ValueError("duplicate current_stack rule id")
    rows = []
    for label, chain in records(document):
        declared = [d["flow"] for d in chain if "flow" in d]
        if flow:
            declared.append(flow)
        replay_values = [d["replay_of"] for d in chain if "replay_of" in d]
        if any(not isinstance(v, str) or not v.strip() for v in replay_values):
            raise ValueError("replay_of must be a nonempty original run/manifest reference")
        replay = bool(replay_values)
        selected = declared[-1] if declared else "replay" if replay else None
        if selected not in stack["flows"] or any(v != selected for v in declared):
            raise ValueError(f"{label}: explicit consistent flow required ({stack['flows']})")
        if selected == "replay" and not replay:
            raise ValueError("flow=replay requires replay_of")
        deviations = approvals(chain, rules)
        for node in chain:
            canonical = node.get("stack_values", {})
            if not isinstance(canonical, dict) or set(canonical)-set(rules):
                raise ValueError("stack_values must be an object with known item ids")
        for rule in rules.values():
            if selected not in rule["flows"]:
                continue
            seen = []
            for level, node in enumerate(chain):
                for selector in rule["verification"]["paths"]:
                    for path, value in values_at(node, selector):
                        if (rule["id"] == "contact_profile" and selector == "profile"
                                and isinstance(value, str) and value not in
                                ("warp_native_contact_v1", "cargo_native_v1", "cargo_noslip_v1", "baseline_noslip10", "legacy_noslip10")):
                            continue  # 'profile' is overloaded by unrelated teacher/scene configs.
                        # A legacy object has its own explicit subfield selector.
                        if isinstance(value, dict) and not isinstance(rule["current"], dict):
                            continue
                        seen.append(dict(field=f"parent[{level}].{path}", value=value))
                for selector in rule["verification"].get("derived_kind_paths", []):
                    for path, kind in values_at(node, selector):
                        if not isinstance(kind, str):
                            raise ValueError(f"{path}: cargo kind must be a string")
                        seen.append(dict(field=f"parent[{level}].{path} contains heavy_crate", value=kind == "heavy_crate"))
            for path, fields, _ in xmls:
                if rule["id"] in fields:
                    seen.append(dict(field=f"{path}:{rule['id']}", value=fields[rule['id']]))
            normalized_values = [normalized(rule, x["value"]) for x in seen]
            if (not seen or any(v == UNKNOWN or (v is None and rule["current"] is not None)
                                for v in normalized_values) or rule["current"] == UNKNOWN):
                status = "unknown"
            elif all(matches(rule, v) for v in normalized_values):
                status = "current"
            else:
                status = "deviation"
            if rule["id"] == "gcp_host" and status == "current":
                # An allowed host with the wrong project/account is still wrong.
                for instance in normalized_values:
                    project = rule["project_for_instance"][instance]
                    account = stack["gcp_projects"][project]
                    for kind, expected in (("project", project), ("account", account)):
                        found = [(path, value) for node in chain
                                 for selector in rule["verification"][kind+"_paths"]
                                 for path, value in values_at(node, selector)]
                        seen.extend(dict(field=path, value=value) for path, value in found)
                        if not found:
                            if status != "deviation":
                                status = "unknown"
                        elif any(value != expected for _, value in found):
                            status = "deviation"
            row = dict(record=label, flow=selected, id=rule["id"], expected=rule["current"],
                       observed=seen, status=status)
            if replay:
                row.update(status="replay_exception", recorded_status=status, replay_of=replay_values)
            elif status != "current" and rule["id"] in deviations:
                row.update(status="approved_deviation", original_status=status, approval=deviations[rule["id"]])
            rows.append(row)
        for path, _, checks in xmls:
            for check in checks:
                row = dict(check, record=label, flow=selected, input=str(path))
                if replay:
                    row.update(status="replay_exception", recorded_status=check["status"], replay_of=replay_values)
                elif row["status"] != "current" and row["id"] in deviations:
                    row.update(status="approved_deviation", original_status=check["status"], approval=deviations[row["id"]])
                rows.append(row)
    return rows


def render_table(rows):
    def cell(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("|", "\\|").replace("\n", " ")
    lines = ["|대상|항목|판정|기준|실제 필드/값|", "|---|---|---|---|---|"]
    for row in rows:
        if row["status"] == "current":
            continue
        lines.append("|"+"|".join(cell(row.get(k)) for k in ("record", "id", "status", "expected", "observed"))+"|")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("inputs", type=Path, nargs="+", help="manifest/summary/queue JSON; optional standalone scene XML")
    p.add_argument("--stack", type=Path, default=ROOT/"configs/current_stack.json")
    p.add_argument("--flow", help="required when JSON does not declare flow; cannot override a conflicting declaration")
    p.add_argument("--output", type=Path, required=True, help="new JSON report; refuses to overwrite input or existing report")
    args = p.parse_args(argv)
    output = args.output.resolve()
    if output in {x.resolve() for x in [*args.inputs, args.stack]} or output.exists():
        p.error("output must be a new file, distinct from inputs/stack")
    report = dict(schema="ugrp.current_stack.check.v1", ok=False, current_compliant=False,
                  checker_sha256=digest(Path(__file__)),
                  scope="declared manifest fields; not independent runtime/physics verification", inputs=[], rows=[])
    try:
        stack = read_json(args.stack)
        report["stack"] = dict(path=str(args.stack.resolve()), sha256=digest(args.stack))
        xmls, documents = [], []
        for path in args.inputs:
            report["inputs"].append(dict(path=str(path.resolve()), sha256=digest(path)))
            if path.suffix.lower() == ".xml":
                fields, checks = xml_evidence(path)
                xmls.append((path, fields, checks))
            else:
                documents.append((path, read_json(path)))
        # XML alone is partial evidence and never admits a queue.
        if not documents:
            documents = [(None, {"flow": args.flow or "release"})]
            report["scope"] = "xml_partial; full manifest required for queue admission"
        for path, document in documents:
            rows = check_document(document, stack, flow=args.flow, xmls=xmls)
            for row in rows:
                row["input"] = row.get("input", str(path) if path else "XML only")
            report["rows"].extend(rows)
        statuses = Counter(row["status"] for row in report["rows"])
        report["counts"] = dict(statuses)
        report["ok"] = bool(report["rows"]) and not (statuses["deviation"] or statuses["unknown"])
        report["current_compliant"] = report["ok"] and not (statuses["replay_exception"] or statuses["approved_deviation"])
        report["admission"] = "pass" if report["ok"] else "blocked"
        if statuses["replay_exception"] and report["ok"]:
            report["admission"] = "historical_replay"
        if report["scope"].startswith("xml_partial"):
            report.update(ok=False, current_compliant=False, admission="partial_only")
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        report["error"] = str(exc)
        report["admission"] = "blocked"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(render_table(report["rows"]))
    print(json.dumps({k: report[k] for k in ("ok", "current_compliant", "admission")}, ensure_ascii=False))
    if "error" in report:
        print(report["error"], file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
