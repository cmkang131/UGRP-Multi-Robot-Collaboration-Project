"""Offline gate tests. Constructed times, poses and contacts are test data."""
import contextlib
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(BASE), str(BASE / "exec")]
from handover import cloud_plan, layout, run_trial, score
from handover.records import Recorder, StopTrial
from sim.handover_scene import arena
from harness import robot_tags_v1 as tags


def synthetic(trial=None):
    trial = trial or layout.trials()[1]
    d, r = trial["donor"], trial["receiver"]
    direction = trial["direction"]
    events, rows = [], []
    def at(u, v):
        return layout.xy(direction, u, v)
    def pose(t, position, held=None):
        return dict(body=layout.BODY, body_id=7, sim_s=t, x=position[0], y=position[1], yaw=trial["mark"][2],
                    z=.036 if held else .016, tilt_deg=1., clearance_m=.020 if held else .0, speed_m_s=.0,
                    finger_n={rid: [1.,1.] if rid == held else [0.,0.] for rid in (d,r)})
    def event(name,t,**data):
        events.append(dict(event=name, sim_s=t, seq=len(events), **data))
    def lift(t,rid,position):
        event("grasp_attempt",t,robot=rid,attempt=1,outcome="lift",pose=pose(t,position,rid),
              lift_samples=[[round(t-3+i*.1,3),.02,1.,1.,1.] for i in range(31)],frame="lift.jpg")
    def release(name,start,rid,position,stand):
        end = round(start+9.7,1)
        event(name+"_start",start,robot=rid,pose=pose(start,position,rid),chassis=stand)
        event(name+"_open",start+4.5,robot=rid,pose=pose(start+4.5,position),frame="open.jpg")
        event(name,end,robot=rid,pose=pose(end,position),frame="rest.jpg",rows=87,
              rest=[pose(round(end-.9+.1*i,3),position) for i in range(10)],
              pose_at_sign=layout.pose_at_sign(trial,pose(end,position)),
              sign_relative=layout.sign_relative(trial,*position))
    event("start",0.)
    event("world_ready",0.,controllers=["r1","r2"],welds=0,dt=.005,body=layout.BODY,body_id=7)
    event("attempt_start",.5,robot=d,attempt=1)
    lift(3.7,d,trial["box_start"][:2])
    release("release",4.,d,at(0,0),at(-.31,0))
    event("donor_clear",14.8,robot=d,xy=at(*layout.PARK),pose=pose(14.8,at(0,0)))
    event("scan_start",15.2,robot=r,xy=at(.8,0))
    event("receiver_seen",15.3,robot=r,frame="seen.jpg",observed_xy=at(0,.01),
          kind="red" if trial["colour"] == "red" else "cyan")
    event("attempt_start",15.4,robot=r,attempt=1)
    lift(18.5,r,at(0,0))
    event("sign_seen",19.,robot=r,sign=trial["receiver_sign"],frame="qr.jpg",
          corners_px=[[101,101],[120,101],[120,120],[101,120]])
    release("set_down",19.5,r,at(2.36,0),at(2.05,0))
    event("complete",29.2,pose=pose(29.2,at(2.36,0)))
    run = dict(trial=trial["trial"],schema="handover.run.v1",status="finished",sim_s=29.2,last_step=5840,dt=.005)
    for i in range(293):
        t = i/10
        row = dict(step=20*i,sim_s=t)
        places = {d: trial["starts"][d][:2] if t<4 else at(-.31,0) if t<14.8 else at(*layout.PARK),
                  r: trial["starts"][r][:2] if t<15.2 else at(.8,0) if t<19.5 else at(2.05,0)}
        for rid,(x,y) in places.items():
            for key,val in zip(("x","y","xmin","xmax","ymin","ymax"),(x,y,x,x,y,y)):
                row[rid+"_"+key]=val
        rows.append(row)
    return trial, events, rows, run


class Design(unittest.TestCase):
    def test_balanced_preselection_and_room_starts(self):
        ts = layout.trials()
        self.assertEqual(list(ts),list(range(1,13)))
        self.assertEqual(len({t["seed"] for t in ts.values()}),12)
        for direction in layout.AXES:
            group = [t for t in ts.values() if t["direction"] == direction]
            self.assertEqual(len(group),3)
            self.assertEqual({t["colour"] for t in group},{"red","blue"})
        for factor in ("wall","donor","receiver"):
            for value in {t[factor] for t in ts.values()}:
                self.assertEqual(sorted(t["colour"] for t in ts.values() if t[factor] == value),["blue"]*3+["red"]*3)
        for t in ts.values():
            for r in t["starts"]:
                self.assertGreater(layout.margin(layout.room(t,r), *t["starts"][r][:2]),.3)
            self.assertLess(layout.uv(t["direction"],*t["box_start"][:2])[0],-.25)
            self.assertLess(abs(math.dist(t["starts"][t["donor"]][:2], t["box_start"][:2])-.76),.15)
            self.assertEqual(layout.margin(layout.room(t,t["receiver"]),0,0),0)
            area = layout.map_config(t)["signs"][str(t["receiver_sign"])]["area"]
            self.assertGreater(layout.margin(area,*layout.xy(t["direction"],2.35,0)),0)

    def test_built_xml_both_orientations_both_sides(self):
        template = """<mujoco><worldbody><geom name='floor'/><geom name='old_prop'/>
            <body name='r1__robot' pos='0 0 .0325'/><body name='r2__robot' pos='0 0 .0325'/>
            <body name='r3__robot' pos='0 0 .0325'/><body name='dispatch_box'><geom name='dispatch_box_geom'
            rgba='.20 .65 .70 1'/></body></worldbody>
            <actuator/><equality><weld/></equality><contact/><asset/></mujoco>"""
        for t in layout.trials().values():
            cfg = layout.map_config(t)
            signs = {int(k): (*v["pos"],v["facing"]) for k,v in cfg["signs"].items()}
            with patch.object(tags,"SIGNS",signs):
                xml = tags.add_signs(arena(template,t),{(n,"h"):f"{n}.png" for n in signs})
            root=ET.fromstring(xml)
            world=root.find("worldbody")
            self.assertEqual({b.get("name") for b in world.findall("body")},{"r1__robot","r2__robot",layout.BODY})
            box = world.find("body[@name='dispatch_box']/geom[@name='dispatch_box_geom']")
            self.assertEqual(box.get("rgba"), {"blue": ".10 .25 .85 1", "red": ".80 .12 .10 1"}[t["colour"]])
            self.assertIsNone(root.find("equality"))
            self.assertIsNone(world.find("geom[@name='old_prop']"))
            for side in ("a","b"):
                jamb=world.find(f"geom[@name='jamb_{side}']")
                axis=1 if t["wall"]=="north-south" else 0
                self.assertAlmostEqual(abs(float(jamb.get("pos").split()[axis]))-
                                       float(jamb.get("size").split()[axis]),layout.OPENING/2)
            for n in signs:
                self.assertIsNotNone(world.find(f"geom[@name='destination_sign_{n}']"))
            self.assertEqual(sum(g.get("name","").startswith("tape_") and g.get("contype")=="0" for g in world),4)

    def test_trace_catches_one_substep_excursion_and_keeps_raw_point(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            trial=layout.trials()[1]
            recorder=Recorder(Path(tmp),trial,stack)
            recorder.sample(0.,-1.,0.,1.,0.)
            recorder.sample(.005,-.001,0.,1.,0.)
            with self.assertRaisesRegex(StopTrial,"chassis centre"):
                recorder.sample(.01,.00003,0.,1.,0.)
            bad=json.loads((Path(tmp)/"events.jsonl").read_text())
            self.assertEqual((bad["step"],bad["robot"],bad["xy"]),(2,"r1",[.00003,0.]))


class Referee(unittest.TestCase):
    def setUp(self):
        self.t,self.events,self.rows,self.run = synthetic()

    def result(self):
        return score.score(self.t,self.events,self.rows,self.run,lambda _: True)

    def e(self,name,occurrence=0):
        return [e for e in self.events if e["event"]==name][occurrence]

    def test_success_rotated_reversed_and_identity(self):
        for t in layout.trials().values():
            self.assertEqual(score.score(*synthetic(t),lambda _:True)["status"],"SUCCESS")

    def test_release_thresholds_and_first_failure(self):
        self.e("release_open")["pose"]["yaw"]+=math.radians(26)
        self.e("donor_clear")["xy"]=[0,0]
        self.assertEqual(self.result()["stage"],"release")

    def test_rectangular_box_half_turn_equivalent(self):
        self.e("release_open")["pose"]["yaw"]+=math.pi
        self.assertEqual(self.result()["status"],"SUCCESS")

    def test_clearance_and_receiver_wait(self):
        self.e("donor_clear")["xy"]=[-.84,.1]
        self.assertEqual(self.result()["stage"],"donor_clear")
        self.rows[8]["r2_ymax"]+=.07
        self.assertEqual(self.result()["stage"],"receiver_wait")

    def test_same_body_and_contiguous_lift(self):
        lift=self.e("grasp_attempt",1)
        lift["pose"]["body_id"]=42
        self.assertEqual(self.result()["stage"],"receiver_pick")
        lift["pose"]["body_id"]=7
        del lift["lift_samples"][9]
        self.assertEqual(self.result()["stage"],"receiver_pick")

    def test_both_fingers_and_hold_duration(self):
        self.e("grasp_attempt")["lift_samples"][9][3]=0.1
        self.assertEqual(self.result()["stage"],"donor_pick")

    def test_sign_and_final_floor_pose(self):
        self.e("sign_seen")["sign"]=99
        self.assertEqual(self.result()["stage"],"sign_seen")
        self.e("sign_seen")["sign"]=self.t["receiver_sign"]
        self.e("complete")["pose"]["speed_m_s"]=.2
        self.assertEqual(self.result()["stage"],"set_down")
        self.e("set_down")["rest"][0]["x"]=0.1
        self.assertEqual(self.result()["stage"],"set_down")

    def test_jaw_opening_while_still_held(self):
        self.e("release_open")["pose"]["finger_n"]["r1"]=[.9,.8]
        self.assertEqual(self.result()["stage"],"release")

    def test_retry_count_and_extra_attempt(self):
        start=self.e("attempt_start")
        index=self.events.index(start)+1
        fail=dict(event="grasp_attempt", sim_s=.6, robot=self.t["donor"],attempt=1,outcome="miss")
        retry=dict(start,sim_s=.7,attempt=2)
        self.events[index:index]=[fail,retry]
        self.e("grasp_attempt",1)["attempt"]=2
        self.e("grasp_attempt",1)["lift_samples"]=[[.7+i*.1,.02,0,1,1] for i in range(31)]
        for i,e in enumerate(self.events): e["seq"]=i
        self.assertEqual((self.result()["status"],self.result()["retries"]["donor"]),("SUCCESS",1))
        self.e("grasp_attempt",1)["outcome"]="miss"
        self.assertEqual(self.result()["stage"],"donor_pick")

    def test_missing_sign_read_and_early_observation(self):
        self.e("receiver_seen")["kind"]="cyan"
        self.assertEqual(self.result()["stage"],"receiver_seen")
        self.e("receiver_seen")["kind"]="red"
        self.events.remove(self.e("sign_seen"))
        for i,e in enumerate(self.events): e["seq"]=i
        self.assertEqual(self.result()["stage"],"sign_seen")

    def test_no_sampling_gap_or_between_endpoint_crossing(self):
        self.rows[2]["r1_xmax"]=.000001
        self.assertEqual(self.result()["stage"],"room_limit")
        self.rows[2]["r1_xmax"]=-1.5
        del self.rows[3]
        self.assertEqual(self.result()["stage"],"room_trace")

    def test_scene_without_images_cannot_pass(self):
        result=score.score(self.t,self.events,self.rows,self.run,lambda _:False)
        self.assertEqual(result["stage"],"donor_pick")

    def test_gate_requires_unique_complete_cohort(self):
        results=[dict(trial=i,status="SUCCESS" if i<=10 else "FAIL",evaluated=True) for i in range(1,13)]
        self.assertEqual(score.aggregate(results),(10,"PASS"))
        self.assertEqual(score.aggregate(results[:-1])[1],"PENDING")
        self.assertTrue(score.aggregate(results+[results[0]])[1].startswith("INVALID"))
        results[0]["status"]="FAIL"
        self.assertEqual(score.aggregate(results),(9,"FAIL"))
        results[0]["evaluated"]=False
        self.assertEqual(score.aggregate(results)[1],"PENDING")


class Interfaces(unittest.TestCase):
    def test_file_backed_score_reads_evidence_and_rejects_a_missing_frame(self):
        from PIL import Image
        t, events, rows, run = synthetic()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, value in (("trial", t), ("run", run)):
                (folder/(name+".json")).write_text(json.dumps(value))
            (folder/"events.jsonl").write_text("".join(json.dumps(e)+"\n" for e in events))
            with (folder/"chassis.csv").open("w",newline="") as stream:
                writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            for name in {e["frame"] for e in events if "frame" in e}:
                Image.new("RGB",(4,4)).save(folder/name)
            self.assertEqual(score.score_dir(folder,layout.trials())["status"],"SUCCESS")
            (folder/"qr.jpg").unlink()
            self.assertEqual(score.score_dir(folder,layout.trials())["stage"],"sign_seen")

    def test_explicit_trial_and_no_overwrite(self):
        args=run_trial.parser().parse_args(["--trial","12","--out","new"])
        self.assertEqual((args.trial,args.wall_seconds),(12,1080))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_trial.parser().parse_args(["--out","new"])
        with tempfile.TemporaryDirectory() as tmp:
            occupied=Path(tmp)/"keep"
            occupied.write_text("original")
            with self.assertRaises(FileExistsError): run_trial.run(layout.trials()[1],Path(tmp),1)
            self.assertEqual(occupied.read_text(),"original")

    def test_dry_run_and_staged_manifest_offline(self):
        with patch.object(socket,"socket",side_effect=AssertionError("network")), tempfile.TemporaryDirectory() as tmp:
            stdout=io.StringIO()
            with contextlib.redirect_stdout(stdout): cloud_plan.main(["--dry-run"])
            self.assertEqual(stdout.getvalue().count("python3 -B"),12)
            stage=Path(tmp)/"stage"
            cloud_plan.main(["--stage",str(stage),"--exec-sha","a"*40])
            with (stage/"manifest.csv").open() as f: rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),12)
            for row in rows:
                scene=(stage/"trials"/(row["scene_id"]+".json")).read_bytes()
                self.assertEqual(row["scene_sha256"],hashlib.sha256(scene).hexdigest())
                self.assertEqual(row["robots"],"r1,r2")
                self.assertEqual(row["server_args"],"")
            with self.assertRaises(FileExistsError): cloud_plan.main(["--stage",str(stage),"--exec-sha","a"*40])

    def test_ordinary_executor_parser_has_no_gate_option_or_import(self):
        from scripts import run_team_carry
        source=Path(run_team_carry.__file__).read_text()
        self.assertNotIn("handover_policy",source)
        self.assertNotIn("handover_scene",source)
        with patch.object(sys,"argv",["run_team_carry.py","--help"]), contextlib.redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as stopped: run_team_carry.main()
        self.assertEqual(stopped.exception.code,0)
        self.assertNotIn("--trial ",out.getvalue())
        self.assertIn("--regrasp-max",out.getvalue())
