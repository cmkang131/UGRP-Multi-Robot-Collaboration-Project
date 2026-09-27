# Pair executor dev PHYSICAL 게이트 준비 — 2026-09-27

최신 미실행 후보는 [표식 무관 자세 계약 v5d](landmark_v5d.md)와 [prereg_v5d.json](prereg_v5d.json)이다.
#221 결정에 따라 dev11·dev12는 prepare-only로 보류한다. 아래 과거 기록과 사전등록은 그대로 보존한다.

## dev07/dev08 결과 진단 — 소스 8effc2ce, prereg_v4

**tags_temporary · dev · 연구 결과 아님.** 원본을 읽기만 했으며 코드 수정·신규 물리 step·모델 호출·git 커밋 없음.
[진단 v5](diagnosis_v5.md) · [하위 조건·원본 해시·수치](diagnosis_v5.json) · [prereg_v4.json](prereg_v4.json).

| 실행 | 결과·실패 (SIM 절대시각) | 미도달·판정 |
|---|---|---|
| dev07 / seed901 / 정상 시도 | approach·align·양쪽 pregrasp relook/fix·standoff·descend 후 202.8 s r1 `PREGRASP_NOT_READY` → r2 `PARTNER_ABORT`. 하위 원인은 **END_CLIPPED 입력을 BAND_CLIPPED 전용 track이 거부**한 BEAM_UNCERTAIN; 자세/전파 σ는 한도 이내, 여유 계산은 미도달 | 닫힘 명령 0건, joint_grasp·lift·door·배치 미도달, `DEV_NOT_CONFIRMED` |
| dev08 / seed902 / abort 진단 | align 중 175.6 s r2 `POSE_UNCERTAIN` → r1 `PARTNER_ABORT`. **XY σ 0.07004 m > loaded HIGH 0.07 m**; yaw σ 1.512°는 3° 이내. 태그 갱신 공백 15.3 s/153프레임 | 닫힘 명령 0건, joint_grasp·lift·door·배치 미도달, `intervention_not_reached`, `DEV_NOT_CONFIRMED` |

권고는 **align 전/중 공통 pose 재관측 + 근접 preclose 관측 계약 보완**이며 임계값 완화는 권고하지 않는다.
원본 16,642개 해시 일치, 비물리 회귀 81개 통과. TensorBoard 임시 snapshot 변환·이벤트/영상 등록은 확인했고,
primary 쓰기 제한으로 공유 게시·화면/핀/HParams 검증은 남았다. 아래 v3/v2 준비·결과는 당시 기록으로 보존한다.

## dev05/dev06 결과 진단 — 소스 4a17e7d4, prereg_v3

**tags_temporary · dev · 연구 결과 아님.** dock x=−0.65 m의 기존 실행을 읽기 전용으로 진단했다.
코드 변경·신규 물리 step·모델 호출·git 커밋 없음. [진단 v4](diagnosis_v4.md) · [수치/원본 해시](diagnosis_v4.json).

| 실행 | 결과·실패 (SIM 절대시각) | 미도달·판정 |
|---|---|---|
| dev05 / seed901 / 정상 시도 | r1·r2 approach 성공 → 190.42875 s r1 `PAIR_COLLISION_GUARD` → r2 `PARTNER_ABORT`. PF 위치 오차 0.759 m와 미파지 전체 빔 영역이 정적 벽 여유를 소진 | joint_grasp·lift·door·배치 미도달, `DEV_NOT_CONFIRMED` |
| dev06 / seed902 / abort 진단 | r1·r2 approach 성공 → r2 wait_lift 중 193.7 s `POSE_UNCERTAIN` → r1 `PARTNER_ABORT`. 실제 초과값은 **yaw σ 3.00115° > 3°**; XY σ 0.05753 m는 loaded HIGH 0.07 m 이하 | joint_grasp·lift·door·배치 미도달, `intervention_not_reached`, `DEV_NOT_CONFIRMED` |

양쪽 실패를 모두 보존한다. 권고는 임계값 완화보다 **파지 전 공통 위치 추정 재관측·양쪽 준비 동기화**다.
원본 해시 16,926개 일치, 비물리 회귀 65개 통과. TensorBoard 임시 변환·이벤트/영상 등록은 확인했고,
primary 쓰기 범위 제한으로 공유 snapshot 게시·화면/핀/HParams 확인은 남았다.
아래 준비 절과 dev01~dev04 기록은 작성 당시 상태로 보존한다.

**최신 사전등록: [dock v3 변경·검증·실행 절차](dock_v3.md), [prereg_v3.json](prereg_v3.json).**
dev05/dev06은 기존 `zone_wide_door_tags_v2`의 벽·태그를 유지하고 세 로봇의 dock x만
−0.85 → −0.65 m로 옮긴다. workflow는 `zone-pair-dev` 0.2.0이다.
아래 v1/v2 및 v3 DRAFT 절은 당시 기록으로 보존한다. 확정 v3는 명시적으로
`--prereg .../prereg_v3.json`을 선택한다. 물리 실행·모델 호출·커밋은 이번 작업에 없다.
**walls_v3(PR #208) 적용은 후속 작업**이다.

PR #235, 리뷰 기준 `2b4cab6700056e8602140a7f89571c27eff8a33a`의 후속이다.
**tags_temporary, dev, 연구 결과 아님.** v1 dev01의 적용값 거부와 dev02 미실행은
[원본 결과](results.md)에 보존했다. 이번 v2 수정에서는 물리 실행·모델 호출·git 커밋을 하지 않는다.
v2는 실행 전 DRAFT이며, 실제 실행은 코디네이터가 소스를 커밋·고정한 뒤 한다.
[새 사전 기록 v2](prereg_v2_DRAFT.json), [보존한 v1](prereg_DRAFT.json), [설계 게이트 1~6](../../docs/design/2026-09-27-pair-executor.md#dev-physical-점검-게이트--3차-리뷰에서-이관)을 함께 읽는다.
`6d25954` dev 리뷰 P1/P2 수정의 근거와 수정 전/후 검증은 [리뷰 수정 기록](dev_review_fixes.md)을 따른다.
`a2c1db7` 재리뷰 P1의 바닥 지지·재들기 면제 수정은 [재리뷰 수정 기록](dev_review2_fixes.md)에 남겼다.

## 구현과 판정 경계

- 진입점: `scripts/run_zone_pair_dev.py`, 표준 workflow ID `zone-pair-dev` (`0.1.0`).
  실제 물리 구현은 `scripts/zone_pair_dev_runtime.py`다. `OwnCamTeamHost`가 생성하는
  **실제 PairTeam과 기존 M2DoorStudent v3**를 사용한다. 동결 M2 CLI와 제어기는 편집하지 않는다.
- r1/r2가 각자 `look_around`를 수행하고 고정 60 SIM초 이후 자기 작업이 끝나면
  자기 `pair_carry(cargoX, B, partner)`를 한 번만 제출한다. 상대 상태를 읽어 대신
  제출하거나 실패한 제출을 재시도하지 않는다. 이는 LLM 통신 실험이 아닌 고정 dev script다.
- 기존 `TaggedCargoZoneScene → ZoneScene → Scene`을 재사용한다. Scene factory에 필요한
  임시 cyan 주문의 상자는 **XML 생성 전** 정적 설정에서 제거한다. 실제 화물은 long_beam 1개다.
  표준 host에는 검증된 Scene 주입 인자만 추가했다. 맵·seed·기본 접촉 프로필·화물 목록이
  host spec과 다르면 거부한다. 보정·weld·카메라 변경이나 실행 중 위치 교정은 없다.
  표준 장면이 남기는 비표시·비충돌 `dispatch_box`/`team_beam` 템플릿 body는 유지한다.
  `other_objects=0`은 활성 색상 상자 수이며, 이런 비활성 템플릿 body의 삭제를 뜻하지 않는다.
- 3대 슬롯을 전제로 하는 host의 스케줄러를 보존하기 위해 **r3를 기존 seeded depot spawn에 둔다**.
  r3에는 작업 API·팔·주행 명령을 보내지 않는다. 충돌·질량·마찰은 유지하며 정적 출발지 keepout도 보존한다.
  비간섭을 미리 성공으로 간주하지 않는다. 평가에서 r3 작업 0건, 동작 명령 0건,
  r1/r2·빔과 접촉 0건, 시작 이후 최대 이동 2 cm 이하를 별도로 요구한다.
- 위치추정은 `OwnCamPoseSource`의 임시 벽/문 태그 provider다. 입력은 자기 wrist `robot_cam`
  JPEG·자기 발행 명령·허용 정적 지도/보정/개략 주문서·STATUS뿐이다. 자기 입력 JPEG와 원래
  관측 메타데이터를 검증 전에 저장하며, 제어기 소비 frame ID/hash도 보존한다. 모델 호출은 0이다.
- 실제 적용 `noslip_iterations=10`, timestep `0.00025 s`, weld OFF, 지도·화물·전체 로봇 목록을
  모델 생성 후 읽어 manifest에 기록하고 불일치하면 진행하지 않는다. 준비 실행의 `applied`는
  `null`이다. 컴파일된 모델 XML은 `eval_only/applied_model.xml`, SHA는 manifest에 둔다.
- GT, 접촉·힘, 카메라 평가, 원래 장면 설정과 observer 영상, 파생 성공 판정은 전부 `eval_only/`에만
  쓴다. 외부 `result.json`은 평가 경로를 가리키고 `physical_success: null`을 유지한다.
  평가 값은 로봇·단계 전환·종료 조건으로 되돌려주지 않는다.

## 사전 기록 v2 — 프로필 timestep 유지

코디네이터 결정: 연구 전체 `cargo_noslip_v1`과 기반 `local_contact_fine`은 변경하지 않는다.
`prereg_v2_DRAFT.json`은 v1 원본 SHA256을 `supersedes`에 연결한다. 기존 dev01·dev02 ID는
재사용하지 않는다. `scripts/zone_pair_dev_contract.py`가 **실제 base/cargo XML 변환**을
컴파일 없는 정적 probe에 적용해 timestep·noslip을 유도한다. 프로필 정의의 SHA256,
두 소스 파일의 SHA256, 파생값을 포함한 전체 계약 SHA256을 사전 기록에 고정했다.
드라이버는 이를 현재 소스에서 재계산해 대조하고, 모델 생성 후 실제 값도 v2와 대조한다.
정적 probe는 물리 접촉 검증이 아니며 `applied=null`인 준비 기록을 실행 증거로 세지 않는다.

| 항목 | v1 (보존) | v2 |
|---|---:|---:|
| 기대 timestep | 2 ms (잘못된 전제) | 프로필 유도 0.25 ms |
| GT 주기 / 스텝 수 | 50 ms / 25 | 50 ms / 200 |
| GT 최대 허용 간격 | 52.1 ms | 50.35 ms = 50 ms + 1 step + 기존 0.1 ms 수치 여유 |
| 접촉 관측 | 매 step | 매 0.25 ms step |
| SIM 상한 | 900 s | 900 s |
| 상한 내 최대 물리 interval 수 | 450,000 | 3,600,000 |
| 내부 wall 상한 | 7,200 s | 57,600 s (16시간) |
| 외부 종료 상한 | 7,260 s | 57,660 s |

SIM 임무 시간·제출 60초·종료 후 2초·영상 5 Hz는 유지한다. wall 예산은
`7,200 × (3,600,000 / 450,000) = 57,600초`로, 모든 기존 비용을 스텝 배수 8로
확대한 보수적 상한이다. **실측 속도·완료 시간 예측이 아니다.** dev01은 관측 시작 전
거부됐으므로 속도 추정의 근거로 사용하지 않는다. 외부 정리 여유는 기존 60초를 유지한다.
실제 접촉 interval 수는 `round((sim_end_s - simulator_start_s) / applied timestep_s)`로
검사하며 초기 관측은 step에 포함하지 않는다. 초기화가 소비한 SIM 시간을 빼므로
3,600,000은 상한이고 매 실행에 요구하는 고정 관측 수가 아니다.

## 사전 고정한 두 dev 실행

| 실행 | seed | 목적 | 종료 한도 |
|---|---:|---|---|
| dev03 | 901 | 접근 → 공동 파지 → 들기 → 문 → B 배치·방출의 전체 시도 | 900 SIM s / 57600 wall s |
| dev04 | 902 | r2의 첫 `carry_go_0` 소비 0.1 SIM s 뒤 명시적 abort | 동일 |

정상 시도 1회와 중단 진단 1회를 구분한다. 2회 연구 성공률로 합산하지 않는다.
실패·거부·한도 초과도 그대로 보존하고 임의 추가 실행은 하지 않는다. dev04가 해당 GO에
도달하지 못하면 `intervention_not_reached`이며 중단 검증을 통과한 것으로 세지 않는다.
영상 이상·상대 소실의 물리 주입은 이 두 회차에 포함하지 않는다. 기존 비물리 회귀에서만
검사하며, 물리 검증이 더 필요하면 새 사전 기록을 작성한다.

[평가기](../../scripts/evaluate_zone_pair_dev.py)는 다음을 별도로 검사한다.

1. 접근 GO 시각의 실제 로봇 위치가 개략 주문서 prestation에서 12 cm / 15° 이내.
2. 양쪽 로봇의 두 손가락 힘이 모두 1 N 이상으로 0.2 SIM초 지속.
3. 위 파지를 유지하면서 빔의 **8개 꼭짓점 모두** 바닥보다 4 cm 이상으로 0.2 SIM초 지속.
4. 빔 전체가 문 벽 slab 서쪽에서 동쪽으로 이동. slab 통과 중 y 범위는 항상 유지하며,
   들림·파지는 사전 등록한 **계획된 set-down** 구간만 예외다. 기존 M2의 2.40 m 체크포인트는
   유지한다. 최종적으로 모든 꼭짓점 x>2.225 m, 양쪽 carry, 공동 파지·4 cm 들림을
   0.2 SIM초 유지해야 문 통과다. 체크포인트 도달 자체는 통과가 아니다.
5. 문 통과 뒤 최종 1초 동안 B 전체 발자국 포함, 바닥 배치·기울기·속도·방출 기준 충족.
   B의 x 폭 60 cm와 빔 길이가 같으므로 발자국 허용 오차 **2 cm**를 dev 조건으로 명시했다.
6. 예상하지 않은 낙하·기울기, 로봇 간/벽/빔-벽 접촉, 접근 중 빔 접촉, r3 간섭 없음.
   정상 바닥 지지·손가락 파지는 허용한다. 계획된 set-down은 양쪽 lower GO부터 다음 carry GO 전까지,
   해당 segment/상태·정적 종점 12 cm 이내일 때만 후보 구간이다. 빔 두께를 반영한 8개 꼭짓점의
   바닥 근접과 낮은 수직 속도가 확인되기 전에는 공동 파지를 유지해야 한다. 방출은 현재 바닥
   지지 중에만 허용한다. 바닥 지지 후 공동 파지·4 cm 들림이 0.2 SIM초 유지되면 해당 면제를
   닫고, 다음 carry GO 전 재낙하·재접촉에도 다시 열지 않는다. 기울기·바닥 관통·금지 접촉은
   예외가 없다. 접촉은 초기 관측과 매 0.25 ms 스텝, GT trace는 초기·50 ms마다·정확한 종료 시각에 기록한다.
7. 모든 관측된 GO를 양쪽이 같은 SIM 시각에 소비. 정상 실행은 계획된 모든 구간의 GO 필요.
   STATUS abort 뒤 양쪽 arm/carry/port/host macro queue·포트 보간·모터가 비어 있고,
   같은 SIM 시각의 뒤쪽 명령을 포함하여 arm/look/drive/mecanum 추가 발행 0건.
   최소 0.5 SIM초를 계속 관찰하며 미실행 경로는 `not_exercised`로 표시한다.
8. 영상의 모든 단계를 검토자가 확인한 기록이 정확한 trace·영상 SHA와 일치해야 최종 DEV_PASS.
9. trace의 양 끝이 manifest의 시작·종료 시각과 일치하고 모든 시각이 timestep 격자에 있어야 한다.
   접촉도 같은 양 끝과 정확한 물리 스텝 수·내부 누락 0건을 요구한다. 누락은 미완료다.
10. 평가 전에 `prereg.json` 원본 바이트 SHA256과 원본 manifest의 사전등록 해시 일치를 강제한다.
    해시가 없거나 다르면 물리 점수를 판정하지 않는다. prepare는 원본 바이트를 그대로 복사한다.
11. manifest의 명시적 `host_error` 또는 `state=host_error`는 경로·trace·영상이 없어도
    **HOST_ERROR와 원래 type/message/ENOSPC 원인**을 먼저 보고한다. 이때 물리 점수는
    계산하지 않고 사전 기록 해시 검증 여부·누락 파일을 별도로 남긴다. host 오류 기록 없이
    증거만 빠진 경우는 계속 EVIDENCE_INCOMPLETE다.

`PAIR_SEQUENCE_DONE / unconfirmed` 자체, 영상 미검토, 누락/비유한 trace,
소스 변경, wall/SIM 한도 초과는 물리 성공 근거가 아니다. 모든 수치와 예외는 JSON에 고정했다.

## 물리 실행 없는 준비

현재 작업 worktree에서 실행한다. `sim_cli workflow plan`은 자식 프로세스를 만들지 않는다.
기본 드라이버 호출은 manifest와 정적 입력만 만들며 MuJoCo를 import하지 않는다.
출력은 항상 새 경로여야 한다.

```sh
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PAIR_PREREG=experiments/2026-09-27-zone-pair-dev/prereg_v2_DRAFT.json
"$PAIR_PY" -m scripts.sim_cli workflow plan zone-pair-dev -- \
  --prereg "$PAIR_PREREG" --run-id dev03
"$PAIR_PY" scripts/run_zone_pair_dev.py --prereg "$PAIR_PREREG" \
  --run-id dev03 --output /tmp/zone-pair-dev-prepare-NEW
```

공통 관리 기록은 source SHA와 실행 트리 해시, workflow 버전, 사전 기록·맵·보정 입력 해시,
환경·명령·종료 코드·전체 출력 receipt를 연결한다. `--prereg`의 누락/존재 여부도 검사한다.
개별 manifest에는 seed·요청/실제 설정·부하·입력 경계·소스 변경 여부를 추가한다.

## 코디네이터의 잠금과 물리 실행 절차 — 이번 작업에서 실행하지 않음

실행 전에 사용자 요청에 맞게 검토된 변경을 **코디네이터가 커밋**하고 아래 `PAIR_SHA`를
고정한다. source dirty이면 드라이버가 거부한다. `main`에서 실행하지 않는다.
같은 코호트 중 소스/설정/seed/기준을 바꾸지 않는다. source SHA가 바뀌면 새 코호트 경로를 쓴다.

먼저 `python3 scripts/agent_lock.py status`와 `python3 scripts/disk_report.py`를 읽는다.
다른 작업이 점유하면 시작하지 않는다. 아래는 생존하는 드라이버 shell PID에 잠금을 묶고
자식 종료 뒤 자기 잠금만 반환하는 예시다. 코디네이터가 Claude/Kiro이면 `PAIR_OWNER`를 바꾼다.
`ugrp_session.py`의 기본 10 GiB 여유 공간 검사를 우회하지 않는다.

```sh
bash <<'PAIR_DEV'
set -euo pipefail
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PAIR_OWNER=codex
PAIR_BRANCH=$(git branch --show-current)
PAIR_SHA=$(git rev-parse HEAD)
PAIR_PRIMARY=/Users/changmin/projects/ugrp
PAIR_PREREG=experiments/2026-09-27-zone-pair-dev/prereg_v2_DRAFT.json
PAIR_ROOT="$PAIR_PRIMARY/outputs/zone-pair-dev-v2-$PAIR_SHA"
PAIR_TIMEOUT=$("$PAIR_PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["limits"]["outer_wall_timeout_s"])' "$PAIR_PREREG")
PAIR_LOCK_MINUTES=$("$PAIR_PY" -c 'import json,math,sys; p=json.load(open(sys.argv[1])); print(math.ceil(p["planned_run_count"]*p["limits"]["outer_wall_timeout_s"]/60)+3)' "$PAIR_PREREG")
test "$PAIR_BRANCH" != main
test -z "$(git status --porcelain)"
"$PAIR_PY" scripts/agent_lock.py acquire --owner "$PAIR_OWNER" --branch "$PAIR_BRANCH" \
  --purpose "pair-v2-dev03-dev04 $PAIR_SHA; no model calls" --pid "$$" --expected-minutes "$PAIR_LOCK_MINUTES"
trap '"$PAIR_PY" scripts/agent_lock.py release --owner "$PAIR_OWNER"' EXIT
export OMP_NUM_THREADS=1
for PAIR_RUN in dev03 dev04; do
  # 매 실행 소스를 검사한다. timeout/host 오류면 이 shell을 중단한다.
  "$PAIR_PY" scripts/ugrp_session.py run "pair-$PAIR_RUN-${PAIR_SHA:0:8}" -- \
    "$PAIR_PY" -m scripts.sim_cli workflow run zone-pair-dev \
    --record "$PAIR_ROOT/$PAIR_RUN-managed" --timeout "$PAIR_TIMEOUT" -- \
    --prereg "$PAIR_PREREG" --run-id "$PAIR_RUN" --output "$PAIR_ROOT/$PAIR_RUN" \
    --execute --expected-source-sha "$PAIR_SHA" --lock-owner "$PAIR_OWNER"
done
PAIR_DEV
```

SIM 종료는 기존 host 스케줄러가 담당한다. 내부 wall 타이머는 초기화부터 적용하고,
관리 workflow의 v2 57660초 timeout은 네이티브 호출/정리가 멈출 때 프로세스 그룹을 정리하는
최종 상한이다. 오류가 나도 `close_episode`로 중단·queue 제거·hold를 수행하고 raw를 보존한다.
ENOSPC는 HOST_ERROR다. 디스크가 이미 가득 찼다면 최종 파일 저장도 실패할 수 있으므로
공통 `console.log`와 부분 입력을 보존하고 성공/컨트롤러 실패로 바꾸지 않는다.
필요한 수동 중단은 `scripts/ugrp_session.py stop <위 세션 이름>`으로 자기 세션만 종료한다.

## 사후 평가·영상·TensorBoard 이관

실행 후 `manifest.applied` 및 `artifacts.sha256.json`과 실제 파일을 대조한다.
`eval_only/result.json`은 영상 검토 전 판정이므로 `physical_success=false`가 정상이다.
아래 형식으로 검토 기록을 **eval_only 안에 새 파일**로 쓰고 실제 전체 영상·자기 입력을 보고 채운다.
여기 적힌 `false`를 실행 없이 바꾸지 않는다.

```json
{
  "run_id": "dev03",
  "reviewer": "검토자 이름",
  "trace_sha256": "실제 eval_only/trace.jsonl SHA256",
  "videos": {"overview.mp4": "실제 파일 SHA256"},
  "stages": {"approach": false, "joint_grasp": false, "lift": false, "door": false,
             "placement_release": false, "drop_contact": false}
}
```

```sh
# PAIR_OUT은 검토할 한 실행의 절대 경로
"$PAIR_PY" scripts/evaluate_zone_pair_dev.py "$PAIR_OUT" \
  --video-review "$PAIR_OUT/eval_only/video-review-01.json" \
  --output "$PAIR_OUT/eval_only/review-01/result.json"
# 성공이 아니면 exit 1; 결과 파일은 보존된다. 중단 진단을 정상 성공으로 표시하지 않는다.
# 검토 result와 영상을 새 파생 뷰에 연결한다. 기존 raw/검토 파일은 수정하지 않는다.
# 같은 파일시스템의 hardlink라 영상 바이트 복제가 없다. ../ symlink는 변환기가 거부한다.
PAIR_VIEW=/Users/changmin/projects/ugrp/outputs/tb-view/pair-dev-NEW
mkdir "$PAIR_VIEW"
cp "$PAIR_OUT/eval_only/review-01/result.json" "$PAIR_VIEW/result.json"
ln "$PAIR_OUT/eval_only/overview.mp4" "$PAIR_VIEW/overview.mp4"
"$PAIR_PY" scripts/export_tensorboard.py \
  --source "$PAIR_VIEW" \
  --output /Users/changmin/projects/ugrp/outputs/tensorboard/pair-dev-NEW --max-images 0
```

실패/중단 결과도 새 snapshot에 넣는다. [TensorBoard 지침](../../docs/tensorboard.md)에 따라
기존 manifest의 원본 경로·해시를 비교하여 중복 변환을 피하고, 공용
`outputs/tensorboard-view.json`은 쓰기 직전에 읽어 자기 항목만 갱신한다.
기존 viewer 소유 PID/명령/logdir 확인 후 자기 viewer만 갱신한다. 실제 native TensorBoard에서
새 run·영상 등록·HParams 열·성공/SIM·wall 시간/명령 수/모델 호출 0·응답 시간 해당 없음과
관련 기준선을 확인한 뒤 대시보드 링크를 보고한다. v1·v2 실제 실행 및 기존 snapshot 검증은
[결과](results.md), v3 오프라인 원인 재구성과 영상 변환 확인은 [진단](diagnosis_v3.md)을 따른다.

## v3 준비 초안 — dev05/dev06, 실행 금지

[prereg_v3_DRAFT.json](prereg_v3_DRAFT.json)은 dev03/dev04 뒤의 **준비 전용** 초안이다.
seed 901/902·빔 설정·60 s 1회 제출·평가 기준·물리 프로필·예산은 v2와 같다.
거부 하위 조건은 `eval_only/pair_admission.jsonl`에 action_id로 연결하여 저장한다.
기존 raw·v1/v2 사전 기록을 바꾸거나 코호트를 합산하지 않는다.

서쪽 dock에서 기존 전신 guard가 출발 자세조차 보증하지 못한다. 시작 위치·관측 부트스트랩은
코디네이터가 [근거와 선택지](diagnosis_v3.md)를 보고 정한다. 장면/위치 변경은 아직 적용하지 않았다.
드라이버는 v3의 `--execute`를 거부한다. 결정 뒤 구현·정적 검증·장면/지도 해시·새 소스 커밋을
완료하고 사전 기록과 실행 허용 경로를 함께 검토해야 한다. 아래는 물리 실행 없는 prepare다.

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 "$PAIR_PY" scripts/run_zone_pair_dev.py \
  --prereg experiments/2026-09-27-zone-pair-dev/prereg_v3_DRAFT.json \
  --run-id dev05 --output /tmp/zone-pair-dev05-prepare-NEW
```

## 비물리 검증

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 "$PAIR_PY" -m pytest -q \
  tests/test_zone_pair_dev.py --basetemp=./.pytest_tmp
rm -rf ./.pytest_tmp
```

새 테스트는 CI `TEST_PATTERNS`에 등록했다. 드라이버 인자/해시/manifest,
MuJoCo import 금지 상태의 prepare·help, 정적 Scene 설정, 독립 제출,
종료 후 보존 endpoint queue, GO·abort 반례와 단계별 평가 반례를 검사한다.
동결 M2 import를 쓰는 fake-world 테스트들은 MuJoCo가 없으면 이유를 적고 skip한다.
world 생성/물리 stepping/모델 호출 테스트는 새 파일에 없다.
초기 구현은 [작업 기록](implementation_record.md), v2 변경·비물리 검증과 남은 게이트는
[v2 수정 기록](prereg_v2_fixes.md)에 남긴다.
