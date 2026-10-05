2026-10-03 독립 검토 부록. **아래 문제는 그 경로를 선택·재사용할 때 적용합니다. 현재 wrist-only OpenCV DEV의 최초 영상 실패 원인으로 합치지 않습니다.** 관련 #213 #214 #226 #3, #293 #309 #353.

기준 main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`; 개별 PR은 별도 head를 표시합니다. 코드 변경·새 물리/모델/학습·실기기·원격 작업·연구 원자료 열람 없이 소스와 임시 합성 반례를 확인했습니다. P1/P2는 아래 도달 조건을 포함한 우선순위입니다. 실제 물리 피해·과거 학습 오염·과금 손실이 발생했다는 증거와 구별합니다.

## 선택 경로의 인수 전 결함

### O1. 일반 RGB v63 realtime open carry의 detached route가 초기화 필드를 잃습니다 — P1, 선택한 경로

**조건:** skills executor + realtime_control + open/non-cluttered beam + ACT override 없음. v63은 own RGB+공통 TOP+지도+own commands 계약입니다. TOP 사용을 별도 최종 wrist-only 계약 위반으로 보고하지 않습니다.

### 고정 SHA 근거

1. [현재 carry 분기](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/run_dispatch_skills.py#L1490-L1508)는 realtime에서 `carry_realtime(ImageRoute(...,'beam'))`를 호출한다. [BoundPairSkill 생성](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/dispatch_pair_skill.py#L402-L410)은 `process_pair_perception = bool(io.realtime_control)`을 설정한다.
2. [현재 worker 초기화](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/dispatch_pair_skill.py#L1345-L1365)는 `detached_beam_route(navigator)`를 전달한다. [detached dict와 복원](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/dispatch_pair_perception.py#L20-L56)은 `ImageRoute.__new__`를 사용하여 정상 생성자를 건너뛰며 `planned`를 복원하지 않는다.
3. [정상 생성자](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/dispatch_skill_binding.py#L396-L405)는 `self.planned = self.task.get('route') == 'auto'`를 만든다. beam에서는 `False`여야 하지만 필드 자체는 필요하다. 클래스 기본값/`__getattr__` fallback은 없다.
4. [worker analyze_top](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/dispatch_pair_perception.py#L58-L75)가 실제 `route.observe`를 호출하고, [observe 공통 분기](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/dispatch_skill_binding.py#L1244-L1250)는 beam/box 모두 `self.planned`를 읽는다. 에러는 RPC RuntimeError가 되어 owner로 전파되며 carry의 finally는 hold한다. 이는 crash/availability 결함이고 collision이나 계속 주행의 증거가 아니다.

### 실제 오프라인 재현

프로젝트 `requirements-test.txt`의 핀인 numpy 2.5.2, OpenCV-headless 5.0.0.93, pytest 9.1.1을 **`/tmp/ugrp-review-cv` 전용 venv**에 설치했다. 시스템 패키지·프로젝트 requirements는 변경하지 않았다.

```text
PYTHONDONTWRITEBYTECODE=1 /tmp/ugrp-review-cv/bin/python -m pytest -q \
  -p no:cacheprovider --basetemp=/tmp/ugrp-review-pytest \
  tests/test_dispatch_pair_process.py::test_top_analysis_precedes_own_and_rejects_mismatched_stage

1 failed in 0.48s
ImageRoute.observe:1246 -> AttributeError: 'ImageRoute' object has no attribute 'planned'
```

기존 portable `pair_grasp_spacing` fixture의 JPEG와 원본 모듈만 사용했다. detector나 route 메서드를 mock하지 않았다. `review-notes/round3-pair-perception-repro.py`로 원본 inline state뿐 아니라 **실제 spawned CPU worker**에서도 `pair perception AttributeError: ... planned`를 확인했다(0.74초). 별도 새 인스턴스에 `route.planned=False` 한 필드만 진단적으로 보충하면 같은 frame 7, time 1.25, 같은 JPEG에서 `analyze`가 완료되고 `route_done=False`를 반환한다. 이 반사실은 저장소 수정/완성된 patch 검증이 아니다.

`prepare_result_save`의 독립 `round3-perception-init-repro.py`도 exact AST 메서드 몸체 + 합성 image boundary에서 동일 접근 오류를 재현했다. 이 AST 근거보다 위 원본 모듈/실제 OpenCV/실제 spawn 재현을 우선 증거로 삼는다.

### 테스트가 말해주는 범위 / 수용 기준

- 기존 portable process 테스트는 결함을 **이미 검출한다**. 테스트 설계가 모킹 때문에 놓친다고 말하면 부정확하다. 반면 `test_dispatch_pair_partial_carry.py:31–51`는 worker와 detach 함수를 통째로 대체하므로 이 생성자 계약을 검사하지 못한다.
- `run_ci_tests.py`의 명시 목록과 tests.yml 직접 선택에서 `test_dispatch_pair_process.py`를 찾지 못했다. 최종 CI coverage는 테스트 감사 담당이 별도로 판단한다. 여기서는 “모든 CI가 반드시 놓친다”라고 단정하지 않는다.
- 수용 기준: 허용 beam route의 모든 observe 필수 필드를 같은 계약으로 초기화하고, 위 portable 테스트를 실제 child process 경계까지 통과시킨다. inline 원본 ImageRoute와 detached/child 결과가 첫 프레임 및 후속 route index/confirmation에서 일치해야 한다. route_overlap의 live authority는 owner에 유지한다. 단순히 예외를 숨기거나 default 동작을 fallback시키는 것은 충분하지 않다.
- 별도 simulation/LLM/cohort를 재실행하기 전에 현재 오프라인 테스트 한 개로 고칠 수 있는 blocker다.
### O2. 실물 stop_all의 한 모터 반복 실패가 나머지 정지 시도를 막습니다 — P1, 실물 재개 전

[stop_all](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/masterpi_control.py#L366-L379): retry try가 모터1→4 전체를 감쌉니다. fake transport에서 motor1만 계속 실패하면 호출은 `[(1,0),(1,0),(1,0)]`, motor2–4는 한 번도 시도하지 않습니다. 명시 stop/motion-finally/signal 및 red_block의 watchdog fallback도 이 함수에 의존합니다. I2C write timeout/flock은 다른 모터의 미시도를 해소하지 않습니다.

**수용:** 각 retry에서 모든 motor zero write를 독립 시도하고 오류를 모아 유한 시간 내 보고합니다. persistent·transient·전체 버스 실패 대조에서 모든 시도와 cleanup 시간을 확인합니다. 전체 버스 실패 때 실제 정지를 보장하거나 실제 지속 이동을 측정한 발견은 아닙니다. control 검토자가 독립 재현했습니다.

### O3. 실물 pose recorder가 servo duration 이전에 stable로 승인합니다 — P2, read-only REAL 관측

[recorder](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/masterpi_control.py#L100-L115) / [tracker](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/real_pose.py#L95-L115) / [read-only caller](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/real_spatial_observe.py#L16-L37). servo target은 발행 직후 기록되지만 duration/완료 예정 시각이 사라집니다. 두 파일의 target이 같고 age≥.18이면 stable입니다. 합성 3초 명령에서 .2초에 stable/metric admitted, 실제 `once` 호출도 fake I/O에서 .32초에 승인했습니다. 동기 Robot.move_servo의 duration+.15 대기가 별도 reader까지 전달되지는 않습니다.

**수용:** 진행 중 모든 arm/camera commanded trajectory의 not-before-settle 시각을 보존하고 그 이전 metric admission을 거절합니다. 더 긴 기존 motion을 후속 명령으로 잊지 않습니다. 완료 후에도 commanded pose이며 measured joint truth가 아닙니다. 현재 owncam PF 입력 또는 실제 오차 크기로 확대하지 않습니다. control 독립 재현 완료.

### O4. ACT의 reply timeout이 blocking request write를 포함하지 않습니다 — P2, 직접 직렬 ACT caller

[RecoveryClient.predict](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/recovery_act_client.py#L35-L53) / [비실시간 caller](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/dispatch_act_carry.py#L98-L103). 큰 RGB JSON을 pipe write/flush한 뒤 selector read timeout을 시작합니다. ready 후 stdin을 소비하지 않는 stdlib 대역 worker에서 timeout=.05s인데 .304s 후에도 predict는 반환/예외 없이 block했고 외부 cleanup 뒤 BrokenPipeError로만 끝났습니다. worker/thread는 모두 회수했습니다. Reference/PairCarry/InputCarry client도 같은 경계를 공유합니다.

**수용:** write와 전체 JSON reply에 하나의 monotonic deadline, partial-write/timeout 후 worker 정리, stale reply 재사용 방지. ready 후 미소비·부분 line 정지·정상 큰 payload를 검사합니다. realtime temporal ACT의 owner-abort/60초 join 보호와 현재 vision_loc_client의 nonblocking deadline은 별도이며 같은 무한대기 주장으로 묶지 않습니다. 문헌 담당 독립 재현 완료.

### O5. Colab A→B→C relay takeover가 조상 seen ID를 잃습니다 — P2, 연속 relay 인계

[resume](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/relay_colab_models.py#L44-L51) / [drained_seen](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/colab_relay_pipeline.py#L16-L30). B는 A의 완료 ID X를 상속하지만 자기 run에는 상속 개수/이전 경로만 저장합니다. C는 B가 직접 처리한 request 파일명만 읽어 X를 잃습니다. **원격 request가 아직 남고 TTL 안인 두 번의 인계**가 조건입니다. fake Contents/provider에서 B_seen=[X], C_seen=[], 추가 provider1/response PUT1을 재현했습니다.

**수용:** 완료 ID의 durable 누적집합 또는 검증한 predecessor chain을 전이적으로 상속합니다. A→B→C에도 X의 provider 호출은 최초1회, 불확실 lineage는 자동 재전송 대신 unknown으로 둡니다. 로봇 행동이 반드시 두 번 실행된다는 주장은 아닙니다. 1회 takeover·만료 rejection·동일 run upload retry 보호는 동작합니다. 평가 담당 독립 재현 완료.

### O6. Kaggle refresh-source 뒤 재사용에서 job SHA와 실행 SHA가 어긋납니다 — P2, source reuse

[reuse](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/kaggle_simulation_cli.py#L146-L191) / [delta](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/kaggle_source_delta.py#L8-L17). prepare archive=A, 첫 refresh=A→B 이후 job은B지만 immutable archive는A입니다(이 자체는 의도). B 출력을 plain reuse하면 delta를 잃어 driver는A/job은B인데 submit.validate가 통과합니다. B에서 C로 refresh하면 archiveA에 base_shaB인 delta를 적용하여 local `source delta base mismatch`가 납니다.

작은 local Git A→B→C fixture로 실제 prepare/pack/reuse/validate/verify를 연결했습니다. 외부 Kaggle/API 호출·가중치 다운로드는 없었습니다. **최종 collect.verify는 plain reuse의 identity mismatch를 거절**하므로 잘못된 확증 결과 승인 결함은 아닙니다.

**수용:** archive base와 실행 SHA/delta를 분리 보존하여 refresh 뒤 plain reuse는B, 연속 refresh는C가 되도록 하거나 지원하지 않는 chain을 submit 전에 거절합니다. 최초·연속·동일SHA refresh와 tampered delta를 검사합니다. 평가 담당 독립 재현 완료.

## 등록된 구형·학습·퇴역 경로

### O7. 구형 통합 runner에서 결과 writer 실패가 host.close를 건너뜁니다 — P2, managed legacy

[run_trial finally](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/run_zone_study_integration.py#L566-L576) / [retry](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_study_llm_driver.py#L565-L591). write_outputs 뒤에만 host.close가 있어 writer ENOSPC/EIO 때 close가 생략됩니다. host 생성 후 모델 요청 전 준비 실패와 writer 실패가 겹치고 budget 종료기록은 가능한 조건이면 pre-request retry가 다음 host를 엽니다.

실제 run_trial AST+retry+MainStudyBudget/SQLite와 fake host/writer에서 `hosts=2, closed=0, second_host_when_older_open=1, requests=0`; writer 정상 대조는 `hosts=2, closed=2, older_open=0`입니다. 실제 GPU 잔류·물리 지속을 측정하지 않았습니다. 등록 ID `zone-study-integration-run`은 managed_legacy_cli이며 새 v99가 아닙니다.

**수용:** 저장 실패와 무관하게 close를 시도하고 cleanup 종료/명시 실패 처리 전 다음 attempt를 열지 않습니다. 원래 시행/저장/정리 오류를 각각 남깁니다. paid request 뒤 재시도 금지, unknown usage cap, attempt 경로 재사용 거절은 기존대로 유지하며 이번 대조에서 확인했습니다. control 독립 재현 완료.

### O8. legacy CoELA late reply의 알려진 비용이 반환 회계에서 빠집니다 — P2, mixed_* 재사용

[late_reply](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/coela_runtime.py#L148-L159) / [return](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/coela_runtime.py#L279-L286). deadline 뒤 도착한 reply를 in_flight에서 빼고 journal만 남기므로 usage/pending_usage 어디에도 없습니다. fake planner가 .03초 뒤7 tokens를 반환하고 timeout=.01인 사례에서3호출/journal21인데 반환 `usage=[]`, `pending_usage={}`입니다.

**수용:** 행동 폐기와 비용 정산을 분리하여 알려진 late usage를 합산하고 아직 미도착한 값은 unknown으로 보존합니다. 현재 #371 새 live model_usage는 실패/unknown을 보존하므로 이 legacy 반례를 그 경로에 적용하지 않습니다.

### O9. carry 기본 데이터 빌더가 split 간 동일 이미지 검사를 건너뜁니다 — P2, legacy ACT 입구

[builder](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/build_carry_act_data.py). root.resolve 교집합과 episode 내부 SHA는 검사하지만 `--base-dataset` 없는 기본 호출은 merge_base의 cross-split digest 검사를 실행하지 않습니다. 다른 두 temp root에 같은 합성 RGB bytes와 전체 trajectory를 복제하면 실제 extract/main이 통과하고, 빈 base와 merge_base 대조는 `identical source images cross train/development split`로 거절합니다. trainer/bundle에서 root 경로 중복을 검사하는 것만으로는 별도 폴더의 내용 복제를 막지 못합니다.

**수용:** base 여부와 무관한 동일 split validator, episode/provenance group의 하류 재확인. 동일 bytes가 독립 episode에서 우연히 나올 모든 경우가 누수라는 일반 명제는 아닙니다. 이 반례는 trajectory 전체 복제입니다. 실제 과거 데이터가 오염됐다는 증거는 아니며 현재 OpenCV 수행의 누수로 올리지 않습니다. architecture 독립 재현 완료.

### O10. recovery ACT의 r1-only split guard가 r3-only 중복을 놓칩니다 — P2, 허용 입력의 조건부 도달

[loader/main](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/train_recovery_act.py). loader는 case의 r1/r3 동시 존재를 요구하지 않는데 main은 r1 case 교집합만 확인합니다. train r1-train/dev r1-dev와 양쪽 shared-r3 case를 합성하면 r1 교집합은 비고 r3는 중복이지만 loader/guard를 통과합니다. 모델·훈련 loop는 실행하지 않았습니다. 표준 collector가 항상 두 robot을 쓰던 dataset에서는 발생하지 않을 수 있습니다.

**수용:** 모든 robot case 합집합의 split 중복을 검사하거나 declared pair의 완전성을 강제하되 split 검증 의도를 유지합니다. 소스가 허용하는 오염 입력의 반례이며 실제 과거 누수 발견이 아닙니다. architecture 독립 재현 완료.

### O11. 선택 RL domain randomization이 reset 사이 누적됩니다 — P2

[baseline/reset](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/masterpi_training_env_v2.py#L123-L165). dynamics=None이며 randomization>0이면 이전 world.dynamics에 난수를 다시 곱합니다. seed7/spread.3/nominal k1의 같은-seed reset8회는 1.075057→1.784238로 변하며 명시 baseline dict 대조는 고정됩니다. randomization0·명시 dynamics는 반례 밖입니다.

**수용:** 최종 초기 dynamics의 immutable baseline에서 매 episode 샘플링하여 같은 seed가 reset 이력과 무관하고 spread 범위를 유지해야 합니다. 실제 학습 성능 악화 증거가 아닙니다. 평가 담당 독립 재현 완료.

### O12. 퇴역 WS worker는 partial-result 전송 오류 뒤 action batch를 반복합니다 — P2, 재사용할 때

[act_parallel](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/multi_masterpi_production.py#L4460-L4470) / [worker cache](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/run_mujoco_ws_worker.py#L478-L517) / [redelivery](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/bridge.py#L579-L583). action은 완료했는데 callback의 partial_result send가 실패하면 completed_results cache에 도달하지 않습니다. 같은 worker/world로 reconnect하고 inflight batch를 재전달하면 action이 다시 실행됩니다. 실제 branch AST+fake socket/counter에서 최초 r1/r2 각1회→cache없음→재전달 각2회였습니다. 정상 final-result send 실패는 먼저 저장한 cache가 보호합니다.

**수용:** action completion/idempotency를 먼저 확정하고 publication 실패가 결과 수집을 중단하지 않게 합니다. 같은 command ID side effect는1회, 불확실하면 자동 실행 대신 reconciliation으로 둡니다. 현재 local CLI/pair caller와 실제 로봇에 적용했다고 하지 않습니다. 평가 담당 독립 재현 완료.

### O13. 현재 production caller를 찾지 못한 front-follow 옵션이 입력 rotation view를 수정합니다 — P3

[front-follow](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/snapshot_render.py#L93-L100) / [capture caller](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/snapshot_render.py#L182-L189). float64 xmat의 np.asarray/reshape/slice view에서 `forward[2]=0`이 live xmat를 수정합니다. .3rad rotation 반례에서 xmat[2,0]은 −.295520→0, 정규직교성이 깨집니다. 현재 production TOP/own caller는 이 옵션을 쓰지 않습니다.

**수용:** 계산용 배열을 copy하여 snapshot 전후 입력 bytes가 같고 rotation이 보존되어야 합니다. 실제 현재 scene corruption을 관측했다는 주장은 아닙니다.

## 5차 열린 PR 검토

### O14 — P1: pack_frames 부분 삭제 뒤 재실행이 이미 보존한 프레임을 덮어쓴다 (#353)

분류: **opt-in 보존/삭제 도구의 실제 데이터 손실 경로, P1**. 최신 pair DEV 실행이나 현재 원자료가 손실됐다는 주장은 아니다. PR merge/도구의 원본 삭제 사용 전 고칠 사안이다.

- base `2523269857596ffdd1a8cda9814a6e92f399f1da` 대비 새 파일이다. GitHub의 정확한 파일 patch는 `@@ -0,0 +1,119 @@`였다.
- [pack_frames.py:47–50](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/scripts/pack_frames.py#L47-L50)는 ffmpeg `-y`로 기존 목적 영상을 교체한다. [67–80](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/scripts/pack_frames.py#L67-L80)는 지금 남은 JPEG만 다시 열거해 영상과 해시 목록을 덮어쓰고, 검증 뒤 하나씩 unlink한다.
- 원본이 3장일 때 첫 삭제가 성공하고 둘째에서 PermissionError/중단이 나면, 3-frame MP4와 3-row 목록은 아직 온전하지만 JPEG는 2장이다. 같은 문서 명령을 다시 실행하면 그 2장으로 기존 영상과 목록을 교체한다. 처음 삭제된 프레임은 원본·영상·해시 목록 모두에서 사라지는데 `verified=True`, exit 0이다.
- [정책/사용법:170–179](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/docs/disk_management.md#L170-L179)의 명시적으로 지정한 새 실행 대상에서도 발생한다. 과거 sealed cohort를 금지하는 절차는 이 재시도 경로를 막지 않는다. H.264가 손실 압축이라는 알려진 정책 한계와 별개의 프레임 자체 소실이다.

재현: 검토용 pack-retry fixture. PR 원문을 import하고 PIL의 32×32 단색 JPEG 3장, 실제 ffmpeg/ffprobe를 사용했다. 둘째 unlink만 실패시키고 documented CLI를 다시 실행했다. 연구 데이터, 코드 수정, 영상 렌더링은 없다.

| 시점 | 남은 JPEG | MP4 decode frame 수 | hash row 수 | 첫 프레임 hash |
|---|---:|---:|---:|---|
| 둘째 unlink 실패 뒤 | 2 | 3 | 3 | 유지 |
| 같은 명령 재실행, exit0/verified=true | 0 | 2 | 2 | 소실 |

[기존 테스트:82–97](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/tests/test_frame_sink.py#L82-L97)는 원본 8장이 전부 남은 상태에서 pack→remove를 실행하므로 통과한다. 이 테스트를 그대로 실행해 통과를 확인했다. 중간 삭제 실패 후 남은 일부만으로 재실행하는 경계가 없다.

**수용 기준:** 이미 검증된 archive/manifest는 부분 삭제 재시도에서 불변이어야 한다. 기존 archive가 있으면 입력 집합을 검증해 원래 목록에 대한 삭제만 재개하거나, 충돌을 명시적으로 거절해 기존 archive를 보존해야 한다. 세 장 중 첫 장 삭제 뒤 중단한 fixture를 재실행해도 처음 프레임의 보존물이 남고, 삭제/검증 상태가 정직해야 한다. 원본이 일부 사라진 집합으로 archive를 다시 만드는 성공 경로는 허용하지 않는다.

architecture 담당이 원문·기존 테스트를 읽고 같은 real ffmpeg 반례를 독립 재실행해 위 수치를 확인했다. 기존 archive/manifest 불변 또는 명시적 거절이라는 인수 기준에 동의했다.

### O15 — P2: write_cap_guard가 leader 종료를 그룹 종료로 취급한다 (#353)

분류: **standalone 용량 안전망의 실제 종료 결함, P2**. 상위 `ugrp_session`의 별도 정리가 보완할 가능성이 있으므로 전체 표준 런처가 반드시 자식을 남긴다고 확대하지 않는다.

새 파일의 [run:52–71](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/scripts/write_cap_guard.py#L52-L71)은 별도 session의 command를 감시하고 cap 초과에 `_stop`을 호출한다. [_stop:74–85](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/scripts/write_cap_guard.py#L74-L85)는 그룹에 TERM을 보낸 뒤 **직접 child의 poll만 종료되면 즉시 return**한다. 같은 PGID에 TERM을 무시하거나 cleanup 중인 descendant가 남아 있어도 grace 뒤 KILL 단계에 도달하지 않는다. [문서:159–168](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/docs/disk_management.md#L159-L168)는 독립 guard의 프로세스 그룹 TERM→grace→KILL을 약속한다.

재현: 검토용 cap-descendant fixture. 원문 모듈의 실제 Popen/killpg를 실행했다. 작은 부모가 자기 자식을 기다리고, descendant는 TERM을 무시한 채 최대 0.5초/200KiB만 임시 파일에 쓴다. cap은 8192 bytes다. 실제 관측은 `cap_exceeded=true`, leader `-15`, guard 반환 때 **32768 bytes**, 반환 후 100ms에 **73728 bytes**였다. fixture의 finally에서 오직 자기 기록 PGID에 KILL을 보내 정리했다. 시간별 크기는 스케줄링에 따라 달라질 수 있고 핵심은 guard 반환 후 크기가 증가한다는 것이다.

[기존 테스트:106–115](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/tests/test_frame_sink.py#L106-L115)는 하나의 leaf writer를 정지시키며 그 테스트는 그대로 통과했다. 프로세스 그룹의 leader와 descendant 수명이 다른 경우는 검증하지 않는다.

**수용 기준:** 용량 초과 종료가 leader poll 완료만으로 그룹 정리 완료가 되어서는 안 된다. TERM에 남은 자기 그룹의 descendant를 grace 뒤 정리하거나, 살아 있음을 명시적인 정리 실패로 보고해야 한다. 정상 exit code 전달은 유지하며, 위 TERM 무시 descendant fixture에서 종료 반환 뒤 쓰기가 계속되지 않아야 한다. 다른 작업 프로세스나 공유 그룹을 대상으로 확대해서는 안 된다.

control 담당이 원문과 같은 실제 프로세스 fixture를 독립 확인했다. 32768→73728 및 leader=-15/cap_exceeded=true를 재현했고 standalone guard 한정 범위에 동의했다.

### O16 — P3, 선택 경로: SIM catalog의 기본 횡이동 인자가 validator에 거절됩니다

main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`의 보존 adapter 계약입니다. 현재 표준 native dispatch나 #363/#371의 필수 경로가 아니며 현재 E2E 차단 원인으로 올리지 않습니다. [harness CLI38–48](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/cli.py#L38-L48)의 명시적 `--actions scripts/sim_actions.py` 등으로 이 adapter를 재사용할 때 적용됩니다.

[robot_actions92–105](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/robot_actions.py#L92-L105)의 move_left/right 기본 speed65/duration.65를 [sim_actions18–29](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/sim_actions.py#L18-L29)가 그대로 복사하고 [registry169–174](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/registry.py#L169-L174)가 생략된 인자에 채웁니다. 그러나 [SIM validator191–205](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/sim_actions.py#L191-L205)는31≤speed≤40만 받아 기본값65를 거절합니다. run_for_robot는 bridge 접근 전에 이를 검사하므로 backend 연결 유무와 무관합니다. **직접 `sim_actions.run('move_left')`를 인자 없이 호출하는 경로의 기본값은35이므로 이 실패에 해당하지 않습니다. catalog가65를 주입하는 tool 경로에 한정한 불일치입니다.**

실제 catalog→validate_args→loop.dispatch→SIM run에 fake bridge를 붙인 합성에서 양 횡이동 `{}`는 `TOOL_EXCEPTION`/POST0, 전후진·회전의 speed35 기본값은 fake POST1이었습니다. 횡이동에 speed35를 명시한 대조군도 validation/fake POST를 통과했습니다. 이 숫자를 실제 횡이동 성능이나 추천값으로 제시하는 것이 아닙니다.

**수용 기준:** backend별 public default/range/description을 일치시키고 모든 기본 primitive를 해당 실제 validator에 연결해 확인합니다. REAL 최소속도 제한을 완화하거나 frozen bundle을 묵시적으로 바꾸지 않습니다. 기존 schema/parity 테스트의 이름·metadata 비교와 실제 default 실행 경계를 구별합니다. 별도 검토자가 actual catalog→registry→runner→validator caller를 읽어 이 범위를 독립 확인했습니다.

### #353의 다른 변경 경계

`harness/frame_storage.py`와 TensorBoard `zone_study.py`는 위 base/head 양쪽을 실제로 읽고 diff했다. 기본값 all_v1→none_v1, 명시적 all_v1 유지, FrameSink 추가, request_images가 존재하지 않는 이미지 대신 hash-only count를 남기는 의미 변경이다. 이 의미 변경은 해당 PR의 명시적인 새 사용자 보존 정책이다. 원본 없이 픽셀을 복구할 수 있다는 주장으로 바꾸지 않았다.

최신 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 [보존 규칙](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/AGENTS.md#L55)은 진행 중 작업·최근3일·대표 영상·사전 등록 본 연구 범위 외 과거 이미지 원본의 정리를 허용하면서 텍스트·원장·결과/trace·삭제 이미지 sha256 목록은 항상 보존합니다. 이 정책을 존중합니다. O14는 원본 삭제 허용 여부와 별개로 이미 검증한 archive와 필수 hash 목록까지 retry가 축소하는 결함이며, O15의 descendant 종료 경계도 정책 변경으로 해결되지 않습니다.

main source의 FrameStoragePolicy 호출 검색에서는 자체/테스트 외 runner의 자동 적용 경로를 찾지 못했다. [docs:194–201](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f/docs/disk_management.md#L194-L201)도 frozen runner를 이번에 바꾸지 않았으며 새 bundle 때 연결한다고 명시한다. 따라서 이 PR이 이미 모든 실행의 디스크 사용량을 줄였다는 주장이나 새 FrameSink 결함이 현재 pair DEV에서 발생했다는 주장은 하지 않는다. 상단 module docstring의 옛 기본값 설명은 낡았지만 위 두 실패보다 우선순위가 낮아 별도 결함을 늘리지 않았다.

### #293 — 수정된 오프라인 계약의 한정 통과

base `a8094cc14e098a55483f53a3c49bf6a0b116043d`에는 이 D1 모듈이 없고, 원문 PR patch로 detector 230줄/evaluator 93줄의 추가를 확인했다. latest head의 두 모듈 전체, PREREG_DRAFT 및 REVIEW_RESPONSE, 관련 tests를 읽었다.

- [detect:195–228](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/d86cc82eedbe0c6693eaf808c54ce43387723f1d/experiments/2026-09-30-stall-detector-d1/d1_detector.py#L195-L228): 미래 프레임 없이 명령별 reference를 분리하고 결측은 streak를 끊는다. 관측 종료 뒤의 95% 관문은 causal alarm 기록을 지우지 않고 status를 바꾼다.
- [score_interval:56–93](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/d86cc82eedbe0c6693eaf808c54ce43387723f1d/experiments/2026-09-30-stall-detector-d1/d1_evaluation.py#L56-L93): 전체 scheduled grid/GT label 수를 요구하며 OTHER/MOVING에서 사건을 닫는다. 같은 STALL tick만 TP에 매칭하고, 관측 부족은 raw alarm을 남겨도 TP를 부여하지 않는다.
- 고정 기전30건, missing denominator, exact95%, 회복 후 alarm/선행FP/후속사건, timestamp jitter, 명령별 reference reset·causal frame selection의 **22개 기존 합성 unit test 통과**. 연구 결과 표를 읽는 test, raw replay, CI 전체, 새 cohort는 실행하지 않았다.

알려진 blocked-at-start/지터 실패와 live adapter/GT/두 로봇 case 집계 부재는 문서와 기존 댓글에 명시돼 있다. 이를 새 결함으로 부르거나 22개 unit 통과를 본실험 승인·검출 성능 통과로 해석하지 않는다. 본 라운드의 추가 blocker는 없다.

### #309 — 최신 stream executor의 한정 통과

base `6594536b1a1afec6d9d109b35dd85a8426142d01`의 `scripts/outputs_prune_stream.py` 조회는 부재(404)였고, 최신 head의 executor 두 파일·rules·관련 tests를 읽었다. 실제 현재 manifest/삭제 대상/보호·결과 inventory는 열지 않았으므로 [최신 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/309#issuecomment-5913930201)의 cache-only 0.567879GiB 수치를 새로 실측 검증했다고 주장하지 않는다.

[stream:305–340](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/c8379bbe16492687af9d7b2d04f85e4ae4c610cc/scripts/outputs_prune_stream.py#L305-L340)는 완료 journal과 batch identity를 맞추고, 사라진 파일의 예외를 durable pending 안으로 한정한다. [420–443](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/c8379bbe16492687af9d7b2d04f85e4ae4c610cc/scripts/outputs_prune_stream.py#L420-L443)는 unlink 전 pending fsync, 완료 journal fsync, keep 재검증 및 실패 receipt를 구현한다. bounded explicit names·keep/delete disjoint·hash/mtime·부모 symlink·active lock 경계를 따라 읽었다.

부분 batch/완료 batch 재개, torn journal, pending 밖 missing 거절, 바뀐 manifest/재등장 path 거절, keep/delete hash·overlap, parent symlink 교체, live lock·동시 pruner, 새 unlisted 파일 보존의 **12개 stream unit test 통과**. 모두 temp outputs 트리다. 이 경계에서 추가 결함을 확정하지 않았다. 오래된 프레임 삭제 규칙의 실행 승인, 캐시 분류기 전체 승인, 현재 manifest 삭제 승인은 포함하지 않는다.

## 버그로 승격하지 않은 경계와 양성 확인

- **학습·평가:** GT teacher label과 runtime input을 구분했습니다. train-only precise BN, 상수 ImageNet normalization, episode 안의 past history/future action target, development checkpoint 선택은 그 자체로 누수가 아닙니다. 내부 kernel CV는 included training 전체로 PCA를 먼저 맞추는 제한을 이미 기록합니다. 소스상 거리 스케일도 fold 밖에서 계산하므로 그 점수는 전체 pipeline의 독립 unseen trajectory 성능으로 확대하면 안 됩니다. 기존 overlap_check는 다른 seed와 독립 trajectory를 구별하고 frozen hash 검사도 존재합니다.
- **현재 OpenCV:** HighPoseSource가 learned segmentation을 instantiate하지 않는 것을 확인했습니다. frozen source hash 검사에 seg_model.py가 포함된다는 사실과 실제 checkpoint 실행은 다릅니다. O9/O10을 현재 DEV 차단 조건으로 삼지 않습니다.
- **v3 기하/보정:** 원래 오프라인12검사 통과, XML FK30자세의 최대 차이5.55e−17m, 현재3map(8/8/7legs)의 sample 독립 연속 swept rectangle에서20mm margin 통과. physical pad86.85mm와 SDK100mm, mount48.2mm, camera floor/optical 변환, source/map/calibration pin을 구분·확인했습니다. 이는 nominal static geometry 내부 일관성이고 loaded sag·실물 mount·접촉·운반 성공 검증이 아닙니다.
- **shared planner:** map_goto의 실제 endpoint 치환에서20mm 요청이16mm로 줄 수 있으나 physical overlap은 없었습니다. 중요한 beam_approach caller가 연속 sweep으로 이미 보완하고 현재 carry 경로도 통과하므로 새 current HIGH blocker로 올리지 않았습니다. 새 arbitrary caller는 실제 segment·endpoint margin을 다시 확인해야 합니다.
- **일반 RGB 반박:** 양쪽 own 분석·동일 frame/time/hash 전 TOP만으로 주행한다는 의심, stale lease 부활, r2/r3 pair에 r1 TOP key 누락, rigid rotation 선속도 부호 문제는 실제 caller에서 반박됐습니다. current loaded observer는 wheel tread를 제외하며 cargo visual identity는 force closure와 구분됩니다.
- **패키징/실행:** 모델 ZIP의 exact membership/hash/type/lock, Kaggle wheel membership, CLI override 후 config validation, 현재 owncam worker startup/checkpoint pin은 확인한 경계에서 방어했습니다. generic 환경변수·탈출 프로세스·미등록 wheel 가설만으로 도달하지 않는 새 결함을 늘리지 않았습니다.

기하 근거: [camera composition](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_final_pair_camera.py#L29-L66), [environment pin](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_final_environment.py#L50-L81), [current obstacles](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/zone_arena.py#L390-L410), [endpoint sweep](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/beam_approach.py#L311-L325). 학습 경계: [internal CV](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/camera_approach_student.py#L29-L119), [train-only BN](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-26-vision-loc/seg_model.py#L110-L201), [overlap guard](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/experiments/2026-09-26-vision-loc/overlap_check.py).

이 부록의 수용 기준은 해당 경로를 다시 쓰기 전의 좁은 인수 항목입니다. 현재 DEV를 모든 과거 옵션의 수정 완료까지 기다리게 하는 목록이 아닙니다.
