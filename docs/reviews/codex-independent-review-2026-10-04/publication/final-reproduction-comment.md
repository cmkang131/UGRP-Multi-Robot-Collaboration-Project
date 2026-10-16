# 최소 offline 재현 부록

공통 실행 조건은 **각 절의 고정 SHA로 된 깨끗한 소스 checkout의 root**, Python 3.11+이다. 이 문서에는 checkout을 바꾸는 git 명령이 없다. `PYTHONDONTWRITEBYTECODE=1 python -`로 Python 블록을 실행하면 된다. 추가 의존성은 각 절에만 적었다. 실행 전에 `git rev-parse HEAD`로 해당 SHA를 확인한다. 소스·원자료·기존 outputs 경로에 쓰지 않으며, 쓰기가 필요한 재현은 스스로 만든 TemporaryDirectory만 사용한다.

모든 관측은 앞 라운드에서 작성자와 독립 확인자가 검증한 결과다. 출판 준비에서는 import 경로를 checkout 기준으로 바꾸고 문장을 압축했으며, **아래 압축 블록은 syntax/source 대조만 하고 같은 테스트를 세 번째 재실행하지 않았다.** 실제 통합 성능·물리·모델·학습·실기기·실제 디스크 full·실제 과거 데이터 오염을 재현했다고 하지 않는다.

## E1 — 같은 tick peer abort 후 dispatch: 본문용 5단계

소스는 main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`의 [Runtime.step 56–74](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_final_pair_runtime.py#L56-L74), [PairTeam.poll 602–614](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_pair_executor.py#L602-L614), [backend.issue 90–107](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/final_environment_checks.py#L90-L107) 및 실제 CameraRobotPort다. #363 `81dbb3eb5c0a915b6b314e3c4898ea253f890267`에서도 [HIGH 상속](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_pair_highpose_runtime.py#L401-L415)과 [dispatch 205–213](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/scripts/run_pair_highpose.py#L205-L213)가 이 순서를 유지한다는 담당자 최신 diff 확인을 받았다. 게시 전 `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`에서도 [Runtime 상속431–445](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_runtime.py#L431-L445)과 [runner210–217](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/scripts/run_pair_highpose.py#L210-L217)의 최종 veto 부재를 source로 확인했다.

1. 이미 입장 완료한 두 PairExecution/OwnExecutor를 만든다. 원문 메서드 몸체를 AST로 실행하며 frame/geometry/bootstrap 및 controller 출력만 boundary 대체한다.
2. 같은 `now=0`에서 r1 controller는 `mecanum(.1,0,0,duration=.15)`을 append하고, 이어 처리되는 r2 controller는 local failure로 전환한다.
3. 실제 `Runtime.step→Own.step→PairExecution→PairTeam.poll`을 실행한다. 결과는 `issued=[r1 motion,r2 hold]`, `terminal={r1:true,r2:true}`, 양쪽 pending hold이다.
4. runner와 같은 `backend.issue→runtime.on_command` 순서로 그 batch를 전달한다. 실제 CameraRobotPort에 연결한 fake robot은 terminal 이후에도 r1 motor `[.1,.1,.1,.1]`과 해당 receipt를 받는다.
5. `port.tick(.049)`에는 같은 setpoint이며 다음 `.05` hold 뒤 `[0,0,0,0]`이다. .15s는 lease이고 정상 loop 관측 잔존은 .05s다.

E1의 완전한 코드는 이 이슈의 ‘E1 추가 재현: 같은 tick abort 이후 실제 command-only port까지의 dispatch’ 댓글에 따로 둔다. 표준 라이브러리만으로 실행 가능한 142줄이며 위5단계의 실제 lifecycle 경계를 보존한다. 긴 이유는 실제 abort lifecycle과 actual command-only port를 보존하여 ‘가짜 step 함수가 가짜 명령을 반환한다’는 동어반복을 피하기 위해서다. 실제 이동·접촉은 생성하지 않는다.

## E2 — staged HIGH의 발행 이력: 과거 재현, 최신 해소 인정

`73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`의 [own_history132–157](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_staging.py#L132-L157)와 [initial_commands318–333](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_staging.py#L318-L333)는 pre-close 자세→close→raise를 자기 명령으로 순서대로 넘깁니다. 따라서 과거 ‘최종 PWM만 전달해 loaded=False가 된다’는 지적은 현재 잔존 결함으로 게시하지 않습니다. [새 test555–583](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/tests/test_highpose_dev_pilot.py#L555-L583)는 fixed delay 뒤 loaded=True/최종 PWM과 구 single-row 반례를 비교합니다. 소스만 읽었고 새 test를 실행하지 않았습니다. 모든 이력 row를 같은 `now`에 넣으므로 원래 prefix와 motion/camera/HIGH settle epoch까지 완전히 동등하다고 새로 검증한 것은 아닙니다. 아래 코드는81db의 과거 반례를 보존한 것이며 최신 미해결 재현으로 읽지 않습니다.

소스: #363 `81dbb3eb5c0a915b6b314e3c4898ea253f890267`. [runner 188–197](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/scripts/run_pair_highpose.py#L188-L197) → [initial_commands](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_final_pair_runtime.py#L43-L46) → [LoadState 81–104](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/owncam_localizer.py#L81-L104). Python 3.11+와 NumPy가 있는 소스 checkout에서 실행한다. 아래는 LoadState의 원문 AST와 실제 v3 순수 FK만 사용한다. v3 tool_pose 연결은 [production binding 25–36](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/vision_pose_source_pair_v3.py#L25-L36)과 같다. 시뮬레이터/영상 gate/접촉을 생성하지 않는다.

<details>
<summary>임시 합성 입력 재현 코드</summary>

```python
import ast
from pathlib import Path
from harness.visual_arm_v3 import tool_pose
from harness.zone_final_pair_loaded_schedule import POSES

tree = ast.parse(Path("harness/owncam_localizer.py").read_text())
constants = {"GRIP_CLOSED_MAX", "GRIP_OPEN_MIN", "GRASP_TOOL_Z_M"}
nodes = [n for n in tree.body
         if isinstance(n, ast.ClassDef) and n.name == "LoadState"
         or isinstance(n, ast.Assign) and any(
             isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
scope = {"tool_pose": tool_pose}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "LoadState-source", "exec"), scope)
LoadState = scope["LoadState"]
a, b = LoadState(), LoadState()
a.command({"kind":"initial_servo_command", "pulses":{1:1500, **POSES["edge_view_150"]}})
b.command({"kind":"initial_servo_command", "pulses":{1:2000, **POSES["floor_grasp"]}})
b.command({"kind":"arm", "servo_id":1, "pulse":1500})
for sid, pulse in POSES["edge_view_150"].items():
    b.command({"kind":"look", "pan_pulse":pulse} if sid == 6 else
              {"kind":"arm", "servo_id":sid, "pulse":pulse})
print({"same_final_pwm":a.servo == b.servo,
       "initial_only_loaded":a.loaded, "history_replay_loaded":b.loaded})
assert a.servo == b.servo and a.loaded is False and b.loaded is True
```

</details>

검증된 관측: `same_final_pwm=True, initial_only_loaded=False, history_replay_loaded=True`. 최종 PWM은 `{1:1500,3:896,4:2035,5:1894,6:1500}`이다. floor/high FK z는 각각 약 0.02391547/0.1498568m. 이는 같은 자기 명령 이력을 마지막 값으로 접으면 loaded 전이를 잃는다는 증거다. 실제 물리 파지·접촉이나 새 DEV rendezvous timeout의 원인을 입증하지 않는다. 당시 81db까지 잔존했으나 게시 전73429982에서는 위 순서 handoff 개선을 확인했다.

## O14 — PR #353 pack 부분 삭제 후 재실행

소스: `6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f`. [pack 47–80](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/scripts/pack_frames.py#L47-L80). Python 3.11+, Pillow, PATH의 libx264 지원 ffmpeg/ffprobe가 필요하다. 다른 경로를 인자로 받지 않고 TemporaryDirectory에 새 32×32 JPEG 3장만 만든다.

<details>
<summary>임시 합성 입력 재현 코드</summary>

```python
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image
from scripts import pack_frames as pack

with TemporaryDirectory(prefix="pack-retry-") as td:
    root = Path(td); frames = root/"frames"; frames.mkdir()
    for i, color in enumerate(("red", "green", "blue")):
        Image.new("RGB", (32,32), color).save(frames/f"{i:05d}.jpg")
    first_hash = hashlib.sha256((frames/"00000.jpg").read_bytes()).hexdigest()
    original = Path.unlink
    def interrupted(path, *a, **kw):
        if path == frames/"00001.jpg":
            raise PermissionError("synthetic second unlink failure")
        return original(path, *a, **kw)
    with patch.object(Path, "unlink", interrupted):
        try: pack.main([str(root), "--execute", "--remove-originals"])
        except PermissionError: pass
    def counts():
        return (len(list(frames.glob("*.jpg"))),
                pack.decoded_frames(root/"frames.mp4"),
                len((root/"frames.sha256.jsonl").read_text().splitlines()))
    print("after_partial:", counts())
    assert counts() == (2,3,3)
    rc = pack.main([str(root), "--execute", "--remove-originals"])
    print("retry_exit:", rc, "after_retry:", counts())
    print("first_hash_present:", first_hash in (root/"frames.sha256.jsonl").read_text())
    assert rc == 0 and counts() == (0,2,2)
    assert first_hash not in (root/"frames.sha256.jsonl").read_text()
```

</details>

검증된 출력: `after_partial=(2,3,3)` → `retry_exit=0, after_retry=(0,2,2), first_hash_present=False`; retry 자체는 `verified=True`로 출력한다. 실제 ffmpeg/ffprobe를 썼다. 원본 파일 삭제 정책의 재논의가 아니라, 승인된 새 실행을 변환하다 부분 실패한 뒤 기존 archive까지 덮어쓰는 경계다. 기존 정상 pack 테스트는 통과했다. 보존된 archive/manifest를 유지하며 삭제만 재개하거나 충돌을 거절하는 것이 수용 기준이다.

## O15 — PR #353 standalone cap guard의 descendant

소스: `6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f`. [_stop 74–85](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/scripts/write_cap_guard.py#L74-L85). POSIX 환경의 Python 3.11+ 표준 라이브러리. 생성하는 worker는 최대 50회×4096 bytes, sleep 합계 0.5초로 제한된다. 기록한 새 process group만 finally에서 정리한다.

<details>
<summary>임시 합성 입력 재현 코드</summary>

```python
import os, signal, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts import write_cap_guard as guard

with TemporaryDirectory(prefix="cap-descendant-") as td:
    root=Path(td); out=root/"out"; out.mkdir()
    data=out/"data.bin"; group_file=root/"group.txt"
    worker=("import signal,time;from pathlib import Path\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            f"p=Path({str(data)!r})\n"
            "for i in range(50):\n"
            " with p.open('ab') as f:f.write(b'x'*4096)\n"
            " time.sleep(.01)\n")
    parent=("import os,subprocess,sys;from pathlib import Path\n"
            f"Path({str(group_file)!r}).write_text(str(os.getpgrp()))\n"
            f"p=subprocess.Popen([sys.executable,'-c',{worker!r}]);p.wait()\n")
    try:
        r=guard.run([sys.executable,"-c",parent], [out], 8192,
                    poll_s=.01, grace_s=.1)
        before=data.stat().st_size; time.sleep(.1); after=data.stat().st_size
        print({"cap_exceeded":r["cap_exceeded"], "leader_rc":r["child_returncode"],
               "bytes_at_return":before, "bytes_100ms_later":after})
        assert r["cap_exceeded"] and r["child_returncode"] == -signal.SIGTERM
        assert after > before
    finally:
        if group_file.exists():
            try: os.killpg(int(group_file.read_text()), signal.SIGKILL)
            except ProcessLookupError: pass
```

</details>

두 독립 실행의 관측: `cap_exceeded=True, leader_rc=-15, 32768→73728 bytes`. 스케줄링에 따라 바이트 수는 달라지므로 핵심 assertion은 guard 반환 뒤 파일 증가다. 부모의 종료를 확인한 것과 전체 그룹 종료를 확인한 것을 구분한다. 상위 ugrp_session까지 항상 잔존시킨다는 주장이나 physics/model subprocess 실험이 아니다.

## E5 — directory receipt 내부 symlink

소스: `f2577bb5121748644df31eb0fc5a1c1b94b80d80`. [path_receipt 56–71](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/workflow_manager.py#L56-L71). Python 3.11+ 표준 라이브러리와 symlink를 지원하는 임시 파일시스템만 필요하다.

<details>
<summary>임시 합성 입력 재현 코드</summary>

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from sim.workflow_manager import path_receipt

with TemporaryDirectory(prefix="receipt-link-") as td:
    root=Path(td); models=root/"models"; models.mkdir()
    target=root/"weights.bin"; target.write_bytes(b"model-v1")
    link=models/"weights.bin"; link.symlink_to(target)
    a=path_receipt(models)
    target.write_bytes(b"model-v2")
    b=path_receipt(models)
    print({"before_files":a["files"], "after_files":b["files"],
           "same_hash":a["sha256"] == b["sha256"], "consumed":link.read_text()})
    assert a["files"] == b["files"] == []
    assert a["sha256"] == b["sha256"] and link.read_bytes() == b"model-v2"
```

</details>

검증된 출력: 두 `files=[]`, `same_hash=True`, 읽는 target은 `model-v2`. directory 내부 link에 한정한다. 루트 인자가 파일인 경우 resolve 후 해시되는 동작을 결함으로 부르지 않는다. 외부 입력의 실제 bytes를 영수증이 보증하지 않는 반례이며 모델은 로딩하지 않는다.

## E6 — console writer ENOSPC

소스: `f2577bb5121748644df31eb0fc5a1c1b94b80d80`. [tee 및 join 590–612](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/workflow_manager.py#L590-L612)와 [기존 temp fixture](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/tests/test_simulation_workflow_manager.py#L20-L52). Python 3.11+ 표준 라이브러리. 기존 WorkflowManagerTests.setUp은 임시 root에서 문자열 출력/작은 JSON만 쓰는 runner를 만든다. `--spawn/--sleep` 옵션을 전달하지 않는다.

<details>
<summary>임시 합성 입력 재현 코드</summary>

```python
import errno, json, threading
from pathlib import Path
from unittest.mock import patch
from tests.test_simulation_workflow_manager import WorkflowManagerTests
from sim import workflow_manager as wm

fixture=WorkflowManagerTests(); fixture.setUp()
original=Path.open; errors=[]
class BrokenLog:
    def __init__(self, handle): self.handle=handle
    def write(self, chunk): raise OSError(errno.ENOSPC, "synthetic console full")
    def flush(self): return self.handle.flush()
    def close(self): return self.handle.close()
def opened(path, *a, **kw):
    handle=original(path, *a, **kw)
    return BrokenLog(handle) if path.name=="console.log" and a==("xb",) else handle
try:
    with patch.object(Path,"open",opened), patch.object(
        threading,"excepthook",
        lambda row: errors.append((row.exc_type.__name__, row.exc_value.errno))):
        record=wm.run_workflow(fixture.root,"fixture",[],timeout=5.)
    m=json.loads((record/"manifest.json").read_text())
    out={k:m[k] for k in ("status","exit_code","failure","finalization_errors")}
    out.update(thread_errors=errors, console_bytes=(record/"console.log").stat().st_size,
               child_result_exists=(record/"artifacts/result.json").is_file())
    print(json.dumps(out))
finally:
    fixture.doCleanups()
```

</details>

검증된 결과: `thread_errors=[["OSError",28]]`, `status=process_completed`, `exit_code=0`, `failure=null`, `finalization_errors=[]`, `console_bytes=0`, `child_result_exists=true`. console 한 곳만 실패시켰으므로 전체 디스크가 가득 찬 상황을 모사했다고 하지 않는다. stdout pipe가 나중에 꽉 차는 hang은 이 재현의 관측 결과가 아니다.

## E8 — 진입 분모 0의 view 변환

소스: `f2577bb5121748644df31eb0fc5a1c1b94b80d80`. [summarize 918–926](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/pair_stage_probe.py#L918-L926) → [view 183–199](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/build_pair_stage_probe_views.py#L183-L199). Python 3.11+ 표준 라이브러리. 아래 raw라는 변수명은 검토가 생성한 합성 JSON 폴더이며 실제 연구 원자료를 받지 않는다. TensorBoard 서버/렌더러를 실행하지 않는다.

<details>
<summary>임시 합성 입력 재현 코드</summary>

```python
import contextlib, io, json, re
from pathlib import Path
from tempfile import TemporaryDirectory
from harness import pair_stage_probe as probe
from scripts import build_pair_stage_probe_views as views

with TemporaryDirectory(prefix="empty-stage-") as td:
    root=Path(td); raw=root/"synthetic-grid1"; raw.mkdir()
    row={"case_id":"align:teacher:synthetic:s1","stage":"align","source":"teacher_grid",
         "cell":"synthetic","seed":1,"passed":False,"category":"HOST_ERROR",
         "cause":"STAGING_IK_ENVELOPE","labels":["synthetic","not_e2e_success"],
         "pair_policy":"v5h"}
    case=raw/"cases"/re.sub(r"[^A-Za-z0-9_.+-]+","_",row["case_id"])
    case.mkdir(parents=True)
    (case/"result.json").write_text(json.dumps({"row":row}))
    (raw/"manifest.json").write_text(json.dumps(
        {"source":{"source_sha":"a"*40},"probe_version":"0.11.1"}))
    (raw/"cases.jsonl").write_text(json.dumps(row)+"\n")
    summary=probe.summarize([row])
    (raw/"summary.json").write_text(json.dumps(summary))
    output=root/"views"
    with contextlib.redirect_stdout(io.StringIO()):
        views.main(["--raw",str(raw),"--output",str(output)])
    view=json.loads(next(output.glob("ALL-*/result.json")).read_text())
    source=summary["stages"]["align"]["staged_pass_rate"]
    scalars=view["offline_scalars"]
    print({"source_staged_pass_rate":source,"view_scalars":scalars})
    assert source is None and scalars["offline/staged_cases"] == 0
    assert scalars["offline/staged_pass_rate"] == 0.0
```

</details>

검증된 요지: source `staged_pass_rate=null`, view `staged_cases=0/staged_pass_rate=0.0`. 전체 planned pass rate 0은 정상이다. 잘못 표현되는 것은 별도 조건부 지표이며 이를 고치려고 계획 분모를 줄여서는 안 된다. 미정의 비율을 scalar에서 생략하고 Text/metadata로 이유를 남기는 인수 기준이다.

## E9 — unknown provenance의 확신 표시

소스: `f2577bb5121748644df31eb0fc5a1c1b94b80d80`. [provenance 1819–1828](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_study_eval.py#L1819-L1828) → [markdown 240–249](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/zone_study_report.py#L240-L249). Python 3.11+ 표준 라이브러리. 기존 `trial` 함수는 합성 dict만 생성하며 파일이나 모델을 읽지 않는다.

<details>
<summary>임시 합성 입력 재현 코드</summary>

```python
from harness import zone_study_eval as ev
from scripts import zone_study_report as report
from tests.test_zone_study_eval import trial

rows=[ev.parse_trial(trial("no_comm",seed=1,
        provenance={"code_sha":"same","map_sha256":"map-A","cost_profile_sha256":"cost-A"})),
      ev.parse_trial(trial("peer_ko",seed=1,provenance={"code_sha":"same"}))]
summary=ev.summarise(rows)
line=next(x for x in report.markdown(summary,[],[],"synthetic").splitlines()
          if "실행 번들 단일 여부" in x)
print(summary["provenance"]["mixed_fields"],summary["provenance"]["single_bundle"])
print(line)
assert summary["provenance"]["single_bundle"] is True
assert line == "- 실행 번들 단일 여부: 예"
```

</details>

검증된 출력은 `[] True`와 `- 실행 번들 단일 여부: 예`다. 다른 map/cost를 실제로 섞었다는 증거가 아니라, 한쪽에 값이 없어 확인 불가인데 ‘예’로 요약하는 반례다. loose pilot loader를 금지하거나 시행을 결과 분모에서 제거하자는 요구가 아니다.
## 현재성·수용 기준 점검

- E1은73429982의 shared step/runner 경계에서도 잔존함을 source로 확인했다. E2는81db 역사적 재현이며73429982 loaded handoff 개선을 인정한다. 최신 공개 DEV의 합류 통과·guard/preclose 종료는 저자 요약이며 위 offline 반례와 구분한다.
- #353의 head는 5차 마감에 재조회한 `6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f`다. #293/#309의 22/12 통과는 한정된 기존 합성 테스트이며 새 실험/삭제 승인으로 확장하지 않는다.
- E5/E6/E8/E9는 고정 main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`에 대한 증거다. 게시 후 main 변경은 자동 승계하지 않는다. architecture 담당은 해당 SHA를 근거로 확인했으며 더 새 main에서 해결됐다는 검증은 받지 않았다.
- #371 old cf82의 광범위 비용 소실은 새 e0ad model_usage로 부분 해결되어 이 재현 목록에서 뺐다. 최신 canonical usage completeness를 사용하고 잔존 alias 혼동을 별도로 논의한다.
- 기존 테스트 명령은 결함 재현의 대체물이 아니다. #353의 정상 pack/leaf-writer 테스트는 통과하면서 위 실패 경계를 놓친다. E9의 기존 mixed-provenance 테스트는 시행을 거절하지 않고 혼재 flag를 확인한다.
- 이번 문서는 source 패치 제안 PR이 아닌 검토 증거다. 스니펫의 failure 주입을 production 코드에 추가하라는 요청이 아니다.

