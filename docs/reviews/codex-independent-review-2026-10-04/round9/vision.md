# R9 — 현재 HIGH PF의 반복 관측 감쇠가 적용되는 범위

검토 SHA: PR #363 `6727751b49ce11fb62234bb97274137f22850765` (2026-10-04). 이전 검토 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`에서 추가된 v98 PF consistency와 현재 호출 경로를 읽었다. 원본 저장소 파일은 변경하지 않았으며 실제 영상·physics·held-out 자료는 열지 않았다.

**판정: 구현 버그 추가가 아니라 현재 정책의 적용 범위와 연구 해석 제한이다.** 이 모듈은 own nonzero command마다 new view로 간주한다고 명시한다. 실제 continuous carry는 같은 속도 lease를 매 0.05초 다시 발행하므로, 적격 scan에서는 매번 repeat counter가 초기화될 수 있다. stationary/fine-align 조건의 효과를 continuous carry까지 동일하게 적용했다고 설명할 수는 없다.

## 호출 경로와 관측이 들어오는 조건

- `harness/zone_pair_highpose_pf_consistency.py:18–27,91–94,111–132`: servo/load 변경, nonzero mecanum command, 또는 own commanded-velocity odometry의 0.02m/0.035rad 누적이 new view 조건이다. `repeat_rho=.5`, column cap 4/기존 8이다. command trigger 자체가 의도된 규칙이므로 threshold 구현 누락으로 분류하지 않는다.
- `scripts/study_owncam_pair_beam.py:409–421`: 진행 중 schedule 구간에서 같은 mecanum 벡터와 `duration_s=.15`를 매 tick 발행한다. `scripts/run_pair_highpose.py:228–242`는 capture/frame → controller command → advance 순서다. `ZoneOwnExecutor.on_command`(`harness/zone_own_executor.py:198–208`)에는 동등 lease를 제거하는 경로가 없다.
- `harness/zone_study_pose_delay_p03.py:86–142`: timestamp/sequence 순서로 자신의 frame/command를 0.16초 지연 전달한다. 같은 capture time의 frame보다 후속 command가 먼저 보이는 것으로 가정하지 않았다.
- frozen `experiments/2026-09-26-vision-loc/vision_loc.py:734–763`의 settle gate는 arm/pan 명령 이후 경과시간을 검사한다. `harness/vision_pose_source_highpose.py:60–67,94–110`은 loaded일 때 issued HIGH와 `HIGH_SETTLE_S=8`을 추가한다. 두 gate 모두 base가 정지해야 한다는 조건은 아니다. initialized, settled, informative columns 등 실제 scan admission 조건은 여전히 필요하다. 따라서 실제 물리 실행에서 모든 20Hz frame이 반드시 적용된다는 주장이 아니다.

## 최소 합성 재현

`vision-temporal-repro.py`는 원본 consistency 모듈, delay adapter, `_carry`, frozen PF의 `settled/update_obs` 본문을 실행한다. PF 운동/likelihood는 일정한 속도와 고정 likelihood의 endpoint로 대체한다. 최초 t=10, HIGH since=0, settled=8초를 만족시키고 20개의 합성 관측을 보낸다. 아래 가중치는 각 scan이 frozen E=8 likelihood에 곱하는 계수의 합이다. posterior accuracy·물리 이동·NEES가 아니다.

| 20개 관측의 조건 | new view / repeat | 누적 likelihood 계수 |
|---|---:|---:|
| 계속 hold | 1 / 19 | 0.952381 |
| 같은 속도, 0.05초마다 0.15초 lease 갱신 | 20 / 0 | 10.000000 |
| 같은 fake 속도 경로, 1.2초 lease 한 번 | 4 / 16 | 2.955556 |
| odometry=0 endpoint, lease 반복 갱신 | 20 / 0 | 10.000000 |
| odometry=0 endpoint, lease 한 번 | 2 / 18 | 1.450000 |
| lease 한 번, 0.15초 후 만료 | 2 / 18 | 1.450000 |
| arm unsettled / informative columns 부족 | 0 update | 0 |

연속 갱신과 긴 lease 대조는 **모든 관측 시점의 fake 좌표가 동일함을 assert**한다. 실제 backend/MuJoCo 경로가 정확히 같다는 실험은 하지 않았다. own issued-command history는 두 조건에서 다르고 현재 policy는 그 차이를 의도적으로 사용한다. `stalled_stub`이라는 JSON key는 단지 PF endpoint odometry를 0으로 강제한 대조다. 실제 PF가 물리 stall을 관측하거나 알 수 있다는 뜻이 아니다.

처음 frame이 첫 command 이전에 처리되므로 단일 lease 조건도 다음 frame에서 한 번 더 reset된다. 그 뒤 긴 lease는 누적 odometry threshold로 reset되고, 반복 lease는 매번 command-trigger로 reset된다. source의 “거리 threshold는 command 없는 drift의 fallback”이라는 설명과 일치한다.

## 과장하지 않고 남길 해석과 수리 기준

1. 현재 stationary 반복 억제와 column cap 감소를 분리해서 보고한다. continuous 갱신 경로에서는 여기 고른 eligible scan의 temporal 지수가 모두 1이고 column 비율 0.5는 계속 적용된다. “감쇠 전체가 꺼진다”는 표현은 틀리다.
2. 현재 threshold를 AMCL과 같은 이동량 전용 update gate라고 설명하지 않는다. scan을 버리는 gate가 아니라 적용된 likelihood의 지수이며 own-command trigger가 더 먼저 reset할 수 있다.
3. **제안하는 새 기준:** 연속 운동을 유지하는 동등 lease 갱신과, 별개의 작은 정렬 pulse를 구분할 필요가 있는지 정책을 먼저 정한다. 갱신 표현만 바꾼 fake trajectory 대조에서 가중치가 같아야 한다는 기준을 채택할 수도 있다. 이는 기존 source가 보장한 계약이 아니며 현재 구현 위반으로 소급하지 않는다. 실제 pose를 gate에 넣으라는 제안도 아니다.
4. `zone_final_pair_scan.quality`는 direct `vl.column_loglik`를 사용하고 consistency는 `pf.measurement`를 수정하지 않는다. informative receipt/fix gate 자체를 함께 낮춘다는 최초 의심은 source로 반증했다.
5. likelihood의 누적 지수 `c_K`가 등상관 Gaussian의 정확한 joint update인지에 관한 질문은 별도 `pf-theory.md`에서 다룬다. 현재 동적 PF의 오차나 실제 성공률 악화를 이 합성 결과에서 추론하지 않는다.

## 기존 edge 문제의 현재성

새 `zone_pair_highpose_edge.robust_edge_line`은 shared `edge_line`이 성공하면 즉시 그 결과를 반환하고, 실패할 때 robust fit을 시도한다. 따라서 R8의 ROI 끝까지 foreground가 이어지는 90/90 false consensus 경계는 이번 변화로 해결된 것으로 간주할 수 없다. 이는 R8 finding의 현재성 확인이며 새 R9 버그로 중복 계산하지 않는다. 공개 OLS minority-leverage timeout과 ROI censoring은 서로 다른 조건이다.

## 재현성과 한계

`vision-source/manifest.json`에 정확한 네 source SHA256이 있다. frozen `vision_loc.py`의 hash는 최신 Git object와도 일치함을 확인했다. 독립 담당자가 별도 임시 폴더에서 source hash guard와 fixture를 실행해 수치/negative controls를 재확인했다(`vision-temporal-validation.md`). 마지막 보강은 HIGH settle 상수를 8초로 맞추고 두 fake 경로의 좌표 동일 assert를 추가한 것이며 결과 수치는 같다.

이 fixture는 1×1 placeholder frame으로 synthetic observation을 전달한다. 실제 480×640 RGB validation/OpenCV/provider 전체를 통과한 실행으로 표시하지 않는다. acquisition timestamp·reset 경계는 이 결과와 섞지 않고 다음 appendix로 이어서 검증한다.
