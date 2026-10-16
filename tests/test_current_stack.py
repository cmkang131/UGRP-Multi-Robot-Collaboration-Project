"""Stack drift/replay/queue counterexamples. No physics, rendering or network."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.check_current_stack import check_document, main, read_json, xml_evidence

ROOT = Path(__file__).resolve().parents[1]


def baseline(flow="release"):
    stack = read_json(ROOT/"configs/current_stack.json")
    values = {r["id"]: (r["allowed"][0] if r.get("operator") == "one_of" else r["current"])
              for r in stack["rules"] if flow in r["flows"]}
    return stack, {"flow": flow, "stack_values": deepcopy(values)}


def status(rows, key):
    return [x["status"] for x in rows if x["id"] == key]


def test_latest_unknown_and_conflicting_runtime_cannot_be_hidden_by_declarations():
    stack, doc = baseline()
    assert all(x["status"] == "current" for x in check_document(doc, stack))
    assert doc["stack_values"]["scene_profile"] == "walls_floor_contrast_v5_indigo110_s80"
    assert doc["stack_values"]["noslip_iterations"] == 0
    # Runtime option defeats a correct desired stack declaration.
    doc["contact_profile"] = {"profile": "warp_native_contact_v1", "options": {"noslip_iterations": "10"}}
    rows = check_document(doc, stack)
    assert status(rows, "noslip_iterations") == ["deviation"]
    doc.pop("contact_profile")
    del doc["stack_values"]["localization_path"]
    assert status(check_document(doc, stack), "localization_path") == ["unknown"]
    # False must never stand in for a measured integer zero.
    doc["stack_values"]["held_world_reads"] = False
    assert status(check_document(doc, stack), "held_world_reads") == ["deviation"]
    doc["stack_values"]["gcp_guards"]["credentials_on_vm"] = 0
    assert status(check_document(doc, stack), "gcp_guards") == ["deviation"]
    doc["stack_values"]["gcp_project"] = "ugrp-sim-c-1016"
    # Both names are allowed individually; this host/project pair is wrong.
    assert status(check_document(doc, stack), "gcp_host") == ["deviation"]
    doc["cargo"] = [{"kind": "heavy_crate"}]
    assert status(check_document(doc, stack), "heavy_crate") == ["deviation"]
    with pytest.raises(ValueError, match="flow"):
        check_document(doc, stack, flow="teacher_gate")


def test_queue_each_world_approval_and_replay_scope_are_separate():
    stack, doc = baseline()
    doc["runs"] = [{"name": "latest"}, {"name": "legacy", "noslip_iterations": 10}]
    assert status(check_document(doc, stack), "noslip_iterations") == ["current", "deviation"]
    doc["runs"][1]["stack_deviations"] = [{"id": "noslip_iterations", "reason": "explicit historical contact comparison",
        "approval": {"authority": "coordinator", "evidence": "fixture: comparison approval, not real authorization"}}]
    rows = check_document(doc, stack)
    assert status(rows, "noslip_iterations") == ["current", "approved_deviation"]
    invalid = deepcopy(doc)
    invalid["runs"][1]["stack_deviations"][0]["approval"]["evidence"] = " "
    with pytest.raises(ValueError, match="approval"):
        check_document(invalid, stack)
    invalid = deepcopy(doc)
    invalid["runs"][1]["stack_deviations"][0]["id"] = "*"
    with pytest.raises(ValueError, match="deviation id"):
        check_document(invalid, stack)
    doc["runs"][1].pop("stack_deviations")
    doc["runs"][1]["replay_of"] = "original-run/manifest.json"
    assert status(check_document(doc, stack), "noslip_iterations") == ["current", "replay_exception"]
    doc["runs"][1]["replay_of"] = ""
    with pytest.raises(ValueError, match="replay_of"):
        check_document(doc, stack)


def test_xml_conflict_cli_reports_and_malformed_inputs(tmp_path, capsys):
    stack, doc = baseline()
    xml = tmp_path/"scene.xml"
    xml.write_text('<mujoco><option noslip_iterations="10" cone="elliptic" integrator="implicitfast" impratio="5.0"/></mujoco>')
    fields, checks = xml_evidence(xml)
    assert status(check_document(doc, stack, xmls=[(xml, fields, checks)]), "noslip_iterations") == ["deviation"]
    manifest = tmp_path/"queue.json"
    manifest.write_text(json.dumps(doc))
    output = tmp_path/"failed.json"
    assert main([str(manifest), str(xml), "--output", str(output)]) == 1
    assert read_json(output)["admission"] == "blocked"
    xml.write_text('<mujoco><option noslip_iterations="0" cone="elliptic" integrator="implicitfast" impratio="5"/></mujoco>')
    good = tmp_path/"passed.json"
    assert main([str(manifest), str(xml), "--output", str(good)]) == 0
    assert read_json(good)["current_compliant"] is True
    partial = tmp_path/"partial.json"
    assert main([str(xml), "--output", str(partial)]) == 1
    assert read_json(partial)["admission"] == "partial_only"
    xml.write_text('<mujoco><include file="unread.xml"/></mujoco>')
    fields, checks = xml_evidence(xml)
    assert any(x["status"] == "unknown" for x in checks)
    with pytest.raises(SystemExit):
        main([str(manifest), "--output", str(manifest)])
    manifest.write_text('{"flow":"release","flow":"replay"}')
    bad = tmp_path/"invalid.json"
    assert main([str(manifest), "--output", str(bad)]) == 1
    assert "duplicate JSON key" in read_json(bad)["error"]
    capsys.readouterr()
