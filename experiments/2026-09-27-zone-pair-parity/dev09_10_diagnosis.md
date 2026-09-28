# dev09·dev10 재관측 진단

2026-09-28 KST · 분석만 · 제어 코드 변경/물리 step/모델 호출/커밋 0.

**결론: 두 실행의 직접 원인은 태그 미검출이 아니라 재관측 성공 조건의 시각 비교 결함이다.** `ALIGN_RELOOK_NO_FIX`라는 종료 문자열만으로 FOV 부족을 결론 내리면 틀린다. 자기 RGB 154/154장에 태그가 검출됐고, 실제 제어기가 소비한 재관측 판단 프레임 10장도 모두 태그가 있다. frozen 판정 함수의 시각 비교 한 항만 기존 시각 허용오차에 맞추면 9/10 판단이 통과한다. 나머지 1장은 σxy 5.601 cm로 5 cm fix 기준을 실제로 넘는다. 이것은 조건부 판정 재생이며 새로운 운반 성공이 아니다.

## 출처와 범위

- 원본: `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v5b-3ea2edc08e5addafaf3cedc934c463ad8e1635c8/{dev09,dev10}`. 읽기 전용.
- 실행 SHA: `3ea2edc08e5addafaf3cedc934c463ad8e1635c8`, 원본 manifest의 `source_dirty=false`. 분석 checkout: `6d1125a531377726ddc2a47d2e616ba937a15b89`.
- [#221 최신 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5857067742)를 확인했다. 방향인 빔 상대 추정은 평가하되, 코멘트의 “재관측해도 태그로 고정하지 못함”은 아래 근거로 세분해야 한다. 코멘트를 수정하거나 게시하지 않았다.
- #240은 조회 시 OPEN/DRAFT, head가 위 실행 SHA와 같았다. [조회 기록](beam_frame_sources.json). CLI `git fetch`는 공유 FETCH_HEAD 쓰기 제한, `gh`는 네트워크 제한으로 실패해 연결 GitHub 읽기 도구로 확인했다. primary main은 `ba0eb4f547996af880de65003442882c5326c71d`; 동기화·병합하지 않았다.
- [재현 분석](beam_frame_analysis.py), [프레임별 JSON](dev09_10_diagnosis.json), [태그 표시 영상표](dev09_10_relook.jpg), [장애물 후보 영상표](dev09_10_blockage.jpg). JPEG와 연결 JSON의 SHA-256을 검사했다. 제어기/검출기/투영/guard의 필요한 소스는 실행 SHA와 일치 검사하거나 frozen Git blob을 직접 import했다.
- 입력은 자기 `robots.json`, `commands.jsonl`, `inputs/`, `pair_records.json`의 자기 로그, 정적 지도뿐이다. 이번 분석은 `eval_only/`, GT, 측정 관절, 접촉, TOP을 읽지 않았다. 과거 성공군 선정과 과거 평가 오차는 기존 parity/loaded 기록에서 가져온 별도 사후 근거다.

## P1: 반올림된 PF 시각을 미래 fix로 오판

실행 SHA의 `harness/zone_pair_align.py:134`:

```python
start < r.t_est - r.since_tag_s <= now
```

`harness/owncam_localizer.py:389`의 `estimate()`는 `t=round(self.t, 4)`를 반환하고 `since_tag_s`도 소수 3자리로 반올림한다. `harness/owncam_pose_source.py:143`은 이 반올림된 시각으로 실제 `PoseReport`를 만든다. 단지 로그를 저장할 때만 생기는 차이가 아니다. 반면 제어기 `now`는 누적된 SIM 원래 실수다.

| 실제 판단 | `now` | `t_est−since_tag_s` | 차이 |
|---|---:|---:|---:|
| dev09 r1 첫 look | 177.2999999975354 | 177.3 | +2.4646 ns |
| dev09 r1 중단 look | 179.49999999748337 | 179.5 | +2.5166 ns |
| dev10 r1 두 번째 look | 155.59999999804853 | 155.6 | +1.9515 ns |
| dev10 r1 중단 look | 156.69999999802252 | 156.7 | +1.9775 ns |

이미 `zone_own_contract.py:35–41`의 report freshness는 **100 µs (`1e-4 s`)** 반올림 허용오차를 둔다. 위 별도 항이 이를 다시 엄격 비교하면서 거부한다. accepted tag의 `last_tag_t`는 현재 원래 capture 시각이고 `since_tag_s=0`이므로 태그 없음·오래된 태그가 원인이 아니다. `GuardedPairApproach.loc` property가 shared own pose를 가리켜 서로 다른 PF를 검사하는 문제도 아니다.

오프라인에서는 정확한 frozen `_align_fix_ready`를 호출했다. 자기 보고로 hysteresis를 다시 계산하고, **134행 오른쪽 상한만 `now + 1e-4`로 바꾼 별도 메모리 함수**와 비교했다. σ·freshness·새 태그·동일 localizer 조건은 유지했다. 원본 함수 0/10, 시각 항만 변경 9/10이다. 코드 파일을 고친 것이 아니다. 로그 σ의 반올림은 인정하되, 해당 통과 표본은 경계에서 충분히 떨어져 있다. raw PF 전체 입자/RNG/제어 경로 재생은 아니다.

권고하는 수정 범위는 새 설계와 별개의 작은 시각 계약 수정이다. authoritative accepted-tag capture timestamp를 사용하고, report와의 비교에 기존 허용오차를 일관되게 적용한다. 반대 부호 반올림에서는 136행 `last_tag_t <= r.t_est`도 같은 문제가 생길 수 있으므로 함께 검사한다. 새 태그가 relook 시작 이전이면 거부하고, 허용오차보다 큰 미래/오래된 보고도 계속 거부해야 한다. 실패 로그에는 어느 conjunct가 거부했는지를 남긴다. **5 cm/3° 기준을 완화할 이유가 없다.**

## pan·프레임·가림

각 로봇은 relook sequence **1회**, 상위 pan **3개**를 예약했다. r1은 3방향의 판단을 모두 했고, r2는 3번째 방향까지 명령한 상태에서 r1 abort를 받아 판단은 2회만 했다. 전체 후보는 7개이나 나머지 4개는 방문하지 않았다. 첫 arm 이동 0.8 s+settle 0.6 s, 후속 pan 0.4 s+settle 0.6 s에 0.1 s control cadence가 붙는다. 재관측 중 base 이동 명령은 0이다.

| 실행·로봇 | 선택한 pan 목표 순서 (PWM) | 판단 시각 s | 판단 시 pan | 검출 태그 수 | σxy cm / σyaw ° |
|---|---|---|---|---|---|
| dev09 r1 | 1500 → 1230 → 1770 | 177.3 / 178.4 / 179.5 | 동일 | 9 / 8 / 8 | 4.552/1.237, 2.960/.718, 2.495/.551 |
| dev09 r2 | 700 → 970 → 1500 | 177.3 / 178.4 | 700 / 970 | 3 / 5 | 2.489/.662, 2.204/.474 |
| dev10 r1 | 1500 → 1770 → 1230 | 154.5 / 155.6 / 156.7 | 동일 | 9 / 7 / 8 | 5.601/1.486, 3.626/.882, 2.557/.548 |
| dev10 r2 | 700 → 970 → 1230 | 154.5 / 155.6 | **713** / 970 | 3 / 3 | 2.248/.590, 2.477/.643 |

dev10 r2의 첫 판단에 기록된 **발행 pan은 713**이다. 목표 700을 실현했다고 표현하지 않는다. 팔/카메라의 실제 관절 위치는 이번 입력 범위에서 알 수 없다. 양쪽 명령은 LOOK_P20 계열이며 결정 프레임의 팔 PWM은 3=1072, 4=2400, 5=1482, grip=2000이다. r2의 판단되지 않은 마지막 방향에서도 마지막 사전-abort 저장 프레임에 태그가 있다(dev09 179.4 s, pan1500, 5개; dev10 156.6 s, pan1230, 3개).

검출 ID:

- dev09 r1: `53,54,55,64,65,72,73,76,77` → `50,51,52,53,54,55,72,73` → `5,6,64,65,66,67,76,77`.
- dev09 r2: `3,4,5` → `1,2,3,4,37`.
- dev10 r1: `53,54,55,64,65,72,73,76,77` → `5,64,65,66,67,76,77` → `50,51,52,53,54,55,72,73`.
- dev10 r2: `3,4,5` → `2,3,4`.

trigger~abort 구간 모든 자기 카메라 프레임을 다시 검출했다. dev09 r1 39/39장(5–10개), r2 38/38장(3–6개); dev10 r1 39/39장(5–9개), r2 38/38장(3–5개). 총 **154/154장**의 검출 ID가 원래 `last_valid_obs.tag_ids`와 일치한다. JSON `dev[].robots[].frames`에 시각·SHA·발행 PWM·투영 ID·검출 ID·σ·판단 사용 여부를 모두 남겼다.

정적 map+당시 own pose+명령 PWM 투영도 각 선택 pan에 태그를 예측한다. 명목 pickup prestation에서도 7개 pan 각각 가시 후보가 있다(`nominal_prestation_projection`). 판정 조건은 카메라 앞, 네 모서리 raw 유효 영역 안, 평균 변 길이 ≥8 px, 태그 정면이다. **ray/물체 가림은 이 정적 투영에 없다.** 투영만 된 ID의 미검출 원인을 곧바로 FOV 밖이나 가림으로 확정하지 않는다.

실제 RGB에는 중앙 빔과 상대 로봇 팔/몸체가 보이고 일부 배경을 가린다. 그러나 여러 벽·문설주 태그는 그 옆과 위에 선명하게 보이며 검출된다. **팔 자세·빔 가림은 이 두 NO_FIX의 직접 원인이 아니다.** 이 관찰을 더 낮은 근접 파지 자세나 loaded 뷰에도 일반화하지 않는다. 재관측은 align 진입에서 끝나 본격적인 낮은 팔 align/close/lift 뷰를 새로 만들지 못했다.

## P2: 목표 빔이 route blockage로 분류됨

두 이벤트의 정확한 JPEG를 같은 검출 함수에 다시 넣어 `yes`, confidence .8, `UNMAPPED_OBSTRUCTION_IN_LANE`을 재현했다. 저장 보고 σ에 따른 belief confidence도 동일 규칙으로 계산했다.

| 실행 | 사건 | 가장 가까운 성분 bbox `[x,y,w,h]` | 자기 추정 거리 | 사건의 위치 |
|---|---|---|---:|---|
| dev09 r2 | 179.8 s / frame_id1491 | [314,181,99,236] | .4573 m | 두 로봇 abort 179.5 s **이후**, job 없음 |
| dev10 r1 | 154.6 s / frame_id1240 | [245,180,93,226] | .4711 m | align_relook 도중, abort 156.7 s 이전 |

표시된 성분은 자기 영상의 노란 목표 빔이다. 더 먼 상대 로봇/영상 성분도 후보 목록에 있지만 `nearest`는 빔이다. `zone_own_perception.py:700–793`은 nonfloor 성분의 바닥 접점을 추정하고 정적 wall과 일치하지 않으면 장애물로 분류한다. `zone_own_status.py:69–80`은 작업 대상 빔과의 연관을 전달하지 않는다. 따라서 화물도 물리적으로 길을 차지한다는 검출은 맞지만, **그것을 예상 밖 장애물로 취급하는 작업 의미가 틀리다.** 빔의 정확한 세계 좌표나 실제 충돌은 이 값으로 측정하지 않았다.

이 사건이 NO_FIX를 일으켰다는 증거는 없다. dev09는 시간상 원인일 수 없고, dev10도 실제 종료는 위 재관측 판정 경로다. 모델 호출은 없었다. 다음 구현에서는 자기 RGB target association이 강한 해당 성분만 `expected_target_occupancy`로 로컬 분류한다. unknown/다른 물체/합쳐진 성분은 계속 장애물 후보로 남기며 빔 충돌 영역도 계속 검사한다. 단순히 pair 작업의 blockage 검사를 모두 끄지 않는다. 상대 로봇이 시야에 보이는 것과 상대 좌표를 공유받는 것은 다르다.

## 판정과 다음 작업

1. **우선 P1 시각 계약 수정 및 회귀 검증**을 #240 후속 범위로 제안한다. 이 두 실패를 “태그가 보이지 않는 pickup의 물리 한계”의 증거로 사용하지 않는다.
2. 빔 상대 좌표계는 앞선 dev05–08의 낮은 팔 motion/PF 문제와 loaded 관측 문제를 대상으로 계속 설계할 가치가 있다. [후속 설계](beam_frame_design.md)는 이를 별도 검증 과제로 다룬다.
3. clock 항 수정 시 첫 분기는 dev09 양쪽 177.3 s, dev10 r2 154.5 s/r1 155.6 s다. 이후 원본 영상은 이미 다른 pan을 실행한 경로이므로 새 align/파지/완주 결과로 이어 붙일 수 없다.

검증 명령과 최종 결과는 [검증 기록](beam_frame_validation.json)에 저장한다. `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`, cache/bytecode OFF; 끝나면 해당 임시 디렉터리를 삭제한다. 물리/모델 모듈 import는 차단했다.

TensorBoard는 이 진단과 M2 근거를 별도 3-run 오프라인 snapshot으로 변환하고 EventAccumulator로 실제 scalar/HParams를 재로딩한다([영수증](beam_frame_tensorboard.json)). 공유 root는 쓰기 범위 밖이고 Chrome은 `cgWindowNotFound`, 브라우저 inventory도 비어 GUI·핀·HParams 표시 검증은 미완료다. [기존 dashboard](http://127.0.0.1:6006)에 새 snapshot이 게시됐다는 뜻이 아니다. 새 물리 영상/서버는 없으며 기존 snapshot과 원본을 보존했다. Google Drive는 프로젝트 예외에 따라 사용하지 않았다.
