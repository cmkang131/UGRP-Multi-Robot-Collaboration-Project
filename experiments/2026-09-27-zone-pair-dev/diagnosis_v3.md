# dev03/dev04 원인 재구성 및 v3 준비 — 2026-09-27

대상: PR #235, 작업 기준 `c4dbfd49717e18b98e243aa0e6f3d8fac602341e`.
실행 원본 소스는 `9f28cbf030442a701a666899c02ebb4374e3e3e2`이며 두 SHA 사이
`harness/`, `scripts/`, `sim/`, `maps/` 변경은 없다. **tags_temporary, dev, 연구 결과 아님.**
기존 [결과](results.md)와 v1/v2 사전 기록은 바꾸지 않았다. 새 공동 운반 실행·모델 호출·커밋은 없다.
단, 검증 중 잘못 포함한 기존 테스트의 물리 초기화 사고는 아래에 따로 기록했다.

원본(읽기 전용):
`/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v2-9f28cbf030442a701a666899c02ebb4374e3e3e2/`.
각 실행 `artifacts.sha256.json`의 **2,012개 파일, 합계 4,024개 해시가 일치**한다.
기계 판독 근거: [diagnosis_v3.json](diagnosis_v3.json). 원본·입력·이벤트의 해시를 포함한다.

## 60 s SELF_UNCERTAIN: 두 실행 모두 gate_ok 하나가 직접 원인

| 실행/로봇 | 59.9003 s 자기 σxy / σyaw | gate | 태그 나이 | 실제 API |
|---|---|---|---|---|
| dev03 r1 | 0.05033 m / 0.01533 rad | uncertain, 초기부터 미해제 | 약 0 s | SELF_UNCERTAIN |
| dev03 r2 | 0.04086 m / 0.01233 rad | ok, 15.1 s 해제 | 약 0 s | 수락 |
| dev04 r1 | 0.03808 m / 0.01082 rad | ok, 3.9 s 해제 | 약 0 s | 수락 |
| dev04 r2 | 0.95959 m / 0.31633 rad | uncertain, 초기부터 미해제 | 58.6 s | SELF_UNCERTAIN |

`robots.json`의 프레임별 추정 기록을 원래 UncertaintyGate에 시간순으로 넣어 재구성했다.
gate는 `uncertain`에서 시작하며, **σxy ≤ 0.05 m AND σyaw ≤ 0.06 rad를 0.4 s 유지**해야
`ok`가 된다. ok에서 불확실 상태로 돌아가는 HIGH는 0.08 m / 0.10 rad, dwell 0.6 s다.
따라서 5.033 cm가 HIGH보다 작아도 아직 해제되지 않은 gate를 통과하지 못한다.

- dev03 r1: 제출 이전 최소 σxy도 0.05015 m여서 LOW를 한 번도 충족하지 못했다.
  이후 60.1003/60.3003/60.5003 s의 0.04983/0.04947/0.04916 m로
  약 60.5 s에야 해제된다. 60 s 1회 제출이 먼저 거부됐고 재제출은 없다.
  이 사후 관찰은 제출 시각을 옮기면 운반이 성공한다는 증거가 아니다.
- dev04 r2: 첫 1.3003 s 프레임의 태그 51/53/55 뒤로 새 태그 관측이 없다.
  팔은 발행 PWM `{1:2000,3:800,4:2380,5:1380,6:1500}`에 멈췄다.
  `frames/r2/00000.jpg`에는 위쪽 태그가 보이지만 `00293.jpg`에는 태그가 화면 위로 벗어나 있다.
  첫 팔 명령 뒤 관측된 큰 σ에서 guard가 다음 팔 전이를 막고, 멈춘 시야에서 태그를
  다시 못 얻는 부트스트랩 정체다. raw는 측정 관절을 제어에 제공하지 않는다.
- 네 로봇 모두 제출 직전 report age 약 0.0998 s, 관측 age 약 0.09975 s로 신선하다.
  initialized·σ 유한성·servo 1/3/4/5/6·빈 집게 조건은 충족했다.
  보존 JPEG로 frame gate도 네 경우 모두 통과했다. 태그 나이는 **진단 값**이며
  현재 pair admission의 별도 거부 조건이 아니다.
- 수락한 상대는 start_ready 이후 65 s 랑데부 timeout으로 abort했다.
  dev04는 carry GO에 못 가서 사전 등록 abort 주입도 미도달이다.

한계: σ는 원본 report의 소수 5자리, 프레임 시간은 소수 4자리로 저장돼 있다.
이는 raw 보고값 기반 gate 재구성이며 PF를 다시 실행하거나 과거 메모리 상태를 직접 읽은 것이 아니다.
60 s의 LOW 판정은 반올림 경계와 떨어져 있어 거부 원인을 구분할 수 있다.

## look_around: 충돌 검출이 아니라 불확실성을 포함한 경로 보증 실패

raw의 정확한 guard 입력으로 `transition_diagnostic`을 다시 계산해 제한 구체·벽·수치를 일치시켰다.

| 실행/로봇 | 종료/단계 | 제한 부위 | 원시 여유 | 요구 margin | 최종 여유 |
|---|---|---|---:|---:|---:|
| dev03 r1 | 12.0 s pan | yaw bearing, 서쪽 벽 | 85.735 mm | 245.470 mm | −159.734 mm |
| dev03 r2 | 12.0 s pan | yaw bearing, 서쪽 벽 | 138.976 mm | 217.354 mm | −78.378 mm |
| dev04 r2 | 11.4 s arm | upper arm, 서쪽 벽 | 260.175 mm | 343.383 mm | −83.208 mm |

margin은 `20 mm + body 잔차 15 mm + 2σxy + 2σyaw×lever`다.
기존 cap(σxy 0.15 m, σyaw 0.20 rad)도 그대로 적용했다.
dev03 종료 σxy는 각각 0.1052347675/0.0911770307 m,
dev04 r2는 0.9552986867 m다. 세 실패 모두 zero-sigma 진단에서는 전이가 clear지만,
실제 자기 σ를 넣으면 **현재 자세부터 음수 여유**다.
따라서 WIDE_LOOK_PANS의 모든 대체 pan과 현재 자세의 동쪽 8 cm 이동이 거부된다.
10 s 누적 정지 재관측 후 fail-closed로 끝난 것이다. 반복 pan 선택만으로 해결되지 않는다.

## 출발 dock 및 코디네이터 선택지

서쪽 벽의 안쪽 면은 x=−1.025 m, 정적 spawn 중심은 x=−0.85 m다.
guard 차체 뒤끝은 중심−0.15 m이므로 벽까지 **25 mm**다.
σ=0이어도 최소 margin 35 mm보다 **10 mm 부족**하다. 이는 물리 침투 10 mm라는 뜻이 아니다.
raw 평가 시작 위치도 x≈−0.849997 m로 정적 배치와 일치한다.

이 출발점에서 먼저 안전한 곳으로 이동하라는 수정은 현재 전신 guard의 시작 샘플을 통과하지 못한다.
시작 샘플 생략·margin 축소·σ/좌표 강제 보정·무검사 pan은 적용하지 않았다.
안전 기준이 과도하다는 검증 근거도 없어 이동 정책과 장면은 그대로 두었다.

1. **정적 dock을 동쪽으로 이동하는 후보:** x=−0.70 또는 −0.65 m.
   y=−0.85, yaw=0, σxy=0.05 m/σyaw=0.06 rad에서 차체 여유는 각각
   **19.009 / 69.009 mm**, 같은 팔 자세의 동쪽 8 cm 전신 이동 검사도 통과한다.
   이는 정적 계산뿐이다. 시작 태그 가시성·PF 수렴·팔 전이·pickup 및 r3 간섭·실제 주행은 미검증이다.
   선택하면 scene과 정적 spawn keepout/map 설명을 함께 버전·해시로 고정해야 한다.
2. **현재 dock 유지 + 관측 부트스트랩 재설계:** 원래 팔 자세에서 정지한 채 신선한 프레임을
   먼저 확보하고, 전 경로 guard가 허용하는 자세만 선택하는 후보를 검토한다.
   현 raw에는 그 조건의 관측이 없어 안전성과 효과를 보증할 수 없다. 현재 막힌 상태를
   그대로 이어받아 탈출하는 경로는 찾지 못했다. HIGH/dwell/guard 예외로 해결하지 않는다.

출발 위치는 **코디네이터 미결정**, 실제 변경 없음. dev03의 60 s 제출 시각만 늦추는 것은
dev04의 태그 소실 및 dock 기하를 해결하지 않으므로 이번 수정에 넣지 않았다.

## 구현과 다음 사전 기록

- `harness/zone_pair_admission.py`: 기존 준비 조건·우선순위를 하나의 판정/진단 스냅샷으로 묶었다.
  mode, gate, 초기화, report/영상 시간, σ 유한성, servo 누락, image validity, holding 조건을 기록한다.
  gate의 LOW/HIGH·dwell·후보 시작 시각과 반올림하지 않은 σ를 저장한다. NaN/Inf는 null + 실패 조건으로 남긴다.
- `ZoneOwnExecutor._ack`: 거부한 pair API의 action_id·원래 거부 enum과 private receipt를 연결한다.
  ACK·status·belief·event·peer STATUS에는 새 진단 필드가 없다.
- dev runtime: API 호출 직후 `eval_only/pair_admission.jsonl`을 flush한다. 스트림은 기존 정리 절차로 닫히고
  최종 artifact 해시에 포함된다. 원본 dev03/dev04에 사후 receipt를 끼워 넣지 않는다.
- [prereg_v3_DRAFT.json](prereg_v3_DRAFT.json): dev05 seed901 정상 시도 / dev06 seed902 carry-GO abort 진단.
  동일 seed의 개발 비교이며 연구/held-out test가 아니다. v2의 평가 기준·0.25 ms·noslip10·weld OFF·예산 유지.
  제출은 기존 60 s 한 번, 자동 재시도 없음. **출발 방식 결정 전 prepare-only**이며 v3 `--execute`는 거부한다.
  두 ID의 실제 prepare를 수행해 `prepared_not_executed`, applied=null, MuJoCo 미import를 확인했다.

## TensorBoard overview 수정

변환기와 미디어 registry가 `motion.mp4`/`execution.mp4`만 허용하던 목록에 `overview.mp4`를 추가했다.
기존 README의 `../overview.mp4` symlink는 이름 추가 뒤에도 경로 보호 규칙에 따라 거부된다.
README를 **새 파생 뷰의 검토 result 복사 + 같은 파일시스템의 영상 hardlink**로 고쳤다.
raw 밖 링크 허용이나 일반 symlink 추적은 추가하지 않았다. 이 작업에서는 raw에 hardlink도 만들지 않았다.

실제 dev03/dev04 `eval_only`를 읽기 전용으로 임시 변환하여 각 영상 1개가 manifest·media_registry에
등록되고 EventAccumulator가 `media/overview.mp4` 및 결과 scalar를 읽는 것을 확인했다.
영상 SHA는 원본 결과 기록과 일치한다. [검증 영수증](tensorboard_overview_check.json).
임시 이벤트는 정리했고 기존 공유 snapshot은 변경하지 않았다.
대시보드는 기존 [TensorBoard](http://127.0.0.1:6006)이며 **이번 변경의 화면/HTTP 재생 검증은 미완료**다.
공유 primary 쓰기 제한 및 localhost bind EPERM으로 새 공유 snapshot·viewer를 수정/시작하지 않았다.
코디네이터는 수정 반영 뒤 새 snapshot으로 재변환하고 기존 media 서버의 코드 반영 여부를 확인해야 한다.

## 테스트·작업 범위·사고 기록

최종 검증: **558 passed, 3 deselected, 23.35 s**. OMP_NUM_THREADS=1,
PYTHONDONTWRITEBYTECODE=1, `--basetemp=./.pytest_tmp`; 종료 후 `.pytest_tmp` 삭제 확인.
관련 pair 전체·own executor 전체·TensorBoard exporter 회귀를 실행했다.
MuJoCo `mj_step`, `mj_step1`, `mj_step2`를 AssertionError로 차단한 프로세스에서 검증했다.
제외 3개는 실제 물리 world 테스트 1개와 sandbox의 localhost bind를 요구하는 기존 HTTP 테스트 2개다.
새 receipt의 다중 실패·정확도·비유출·영속화, 세 raw guard 반례, v3 prepare/execute 차단,
영상 이벤트/registry·symlink 거부·hardlink 지원을 검사했다.

검증 중 **테스트 선택 실수**로 `test_team_host_isolation_abort_and_horizon_on_the_real_world`가 한 번 포함됐다.
단일 로봇 템플릿 생성자의 reset에 물리 settle이 있어 사용자 요청의 물리 실행 금지 범위를 어겼다.
그 뒤 3대 world는 렌더 초기화에서 `invalid CoreGraphics connection`으로 실패하여 공동 운반에는
도달하지 않았다. 해당 pytest 프로세스는 종료됐고 같은 테스트를 재실행하지 않았다.
템플릿 초기화의 실제 step 수/시간은 계측하지 않았으므로 새 실험 결과나 0-step 실행으로 표시하지 않는다.
이후 위 558개 검증에는 물리 step 차단을 걸었다. 새 모델 호출·장면/출발 변경·커밋·push·병합은 없다.

`git fetch origin`은 공유 Git 디렉터리의 FETCH_HEAD 쓰기 제한으로 실패했고 `gh`는 네트워크 제한으로 실패했다.
GitHub connector로 현재 canonical 저장소 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`의
PR #235 open/draft, head c4dbfd49 및 관련 열린 PR 목록을 확인했다. 원격 주소는 바꾸지 않았다.
기본 checkout은 main a67b6e33 / 로컬 origin/main 2823c57c로 뒤처져 있으나 쓰기 허용 범위 밖이므로 갱신하지 않았다.
결과는 이 worktree에만 저장했다. UGRP 예외에 따라 Drive 작업은 하지 않았다.

재구성 명령(새 출력 파일을 지정):

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.diagnose_zone_pair_dev \
  --raw-root /Users/changmin/projects/ugrp/outputs/zone-pair-dev-v2-9f28cbf030442a701a666899c02ebb4374e3e3e2 \
  --output /tmp/pair-dev-diagnosis-NEW.json
```

## 후속 결정 적용 — dock-only v3, dev05/dev06

위의 "코디네이터 미결정/prepare-only"는 진단 당시 상태다.
[이슈 #218 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/218#issuecomment-5853065426)
및 후속 지시에 따라, dev05/dev06은 기존 벽 높이 0.10 m·tags_v2를 그대로 두고
세 로봇의 출발 x만 −0.65 m로 옮긴 `zone_wide_door_tags_v2_dock_v3`를 사용한다.
[확정 사전등록](prereg_v3.json)·[정적 검증과 변경 파일/해시](dock_v3.md)를 추가했다.
기존 map·prereg DRAFT·진단 JSON·raw는 덮어쓰지 않았다.

**walls_v3(PR #208) 적용은 후속 작업**이며 이 브랜치에 가져오지 않았다.
후속 적용 시 벽 중심 x=−1.05 m, 반두께 0.025 m이므로 안쪽 면은 −1.025 m다.
yaw=0에서 차체 뒤끝은 `spawn_x−0.15`이고,
`margin = 0.020 + 0.015 + 2×min(σxy,0.15) + 2×min(σyaw,0.20)×sqrt(0.15²+0.09²)`다.
새 x=−0.65, σxy=0.05 m/σyaw=0.06 rad이면
`clearance = (−0.65−0.15)−(−1.025)−margin = 0.06900857317855691 m`.
행 y=−2.25/−0.85/+0.55, seeded 로봇 배정, z/yaw 및 keepout 반경 0.17 m를 유지한다.
walls_v3의 0.40 m 높이는 팔·카메라 가시성에 영향을 주므로, 차체의 이 수치만
그대로 적용할 수 있다. 그 장면의 전신 sweep·가시성·PF·pickup·실제 r3 비간섭은 별도 검증한다.
