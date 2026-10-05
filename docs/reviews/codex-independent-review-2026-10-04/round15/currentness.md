# R15 최신 head와 공개 상태

2026-10-04 **08:23:46.872 UTC**, 공식 GitHub PR363 API의 head는 `66ff0978a817caa949d2d738b51d7ae89dd17e71`, updated는08:20:27Z다. `current-frontier-66ff.json` (Mac 전달본 증거)를 저장했다. PR의 base_sha `798198…`는 PR base snapshot이며 main branch 조회 결과가 아니다.

de03 대비5commits/18files다. 새 `carry_align`, `relook`, `final_veto`; PF consistency/roughening, runtime/staging/lookaround와 tests, runner, 공개 README가 바뀌었다. 전체18파일의 기능 검증을 완료했다는 뜻은 아니다. R14는 de03의 고정 검토로 보존한다.

## 공개 작성자 보고의 변화

읽은 자료는 tracked README의 추가115줄뿐이다. 그 안의 `outputs/…` 원본, 영상, trajectory, 평가 GT는 열지 않았다. 아래 내용은 작성자가 보고한 `af2f7c2a` DEV_PILOT 단계 실행이지 이번 검토자가 재실행한 결과가 아니다. result의 SIM 검사 시간과 controller event 시계도 분리했다.

| 공개 단계 | 최신 작성자 보고 | 과거 de03 요약과의 관계 |
|---|---|---|
| dock `raise_high` | 양쪽 `LOOKED` 뒤 r2 `PAIR_COLLISION_GUARD` event10.9s, r1 partner abort; result 검사9.65s | 이전 r2입장 SELF_UNCERTAIN/상대 rendezvous timeout을 현재 첫 실패로 유지하지 않음 |
| `raise_high_align` | r2 `ALIGN_RELOOK_NO_FIX` event28.6s, r1 partner abort; 검사27.35s | 과거83.55s REACHED에서 퇴행했다고 작성자가 표기 |
| `align_to_carry` | 같은 정렬 재관측 실패, 아직 파지·carry 미도달 | 과거 edge88.9/GO89.1/loaded gate92.2는 이 새 실행의 상태가 아님 |

작성자의 새 진단은 `p45→inspect` 전환 도중 `fix_gap` 재관측 stop이 중간 issued arm posture765/1991/1865를 남기고, 그 자세의 camera model이 없어 provider가 `UNMEASURED_V3_CAMERA_POSTURE`로 fail-closed했다는 것이다. 이 원인을 raw로 독립 확인한 것은 아니다. R12의 de03 실제-source command-only hold/interpolation 증거와는 **같은 종류의 명령·camera-model 경계에서 나온 별도 증거**로 연결한다. 동일 fixture, 동일 발생 시각, 동일 실패 원인이 이미 입증됐다고 합치지 않는다. 최신 inspect/stop/provider caller는 다음 좁은 source 검토 대상이다.

## 이번 결과의 현재성

- [checkpoint attachment identity](attachment.md): de03 증거 보존,66ff의 관련 메서드/MRO와 실제 flag 전달을 다시 확인했다. geometry consumer12파일도 동일하다. 최신 공개 run이 checkpoint까지 도달했다는 증거는 없으므로 현 실패 원인으로 쓰지 않는다.
- `final_veto`는 기존 같은-tick peer-abort dispatch 문제를 수정하려는 별도 변경이다. 소스 의도만으로 완전 해결이라고 판정하지 않고 해당 원본 경로의 합성 회귀 검증 결과를 따로 사용한다.
- 새 dock8방향/relook/30초 rendezvous 및 carry-align 유의성 규칙, PF roughening은 각각 별도 새 동작이다. 예전5방향/고정 seed 증거를 최신8방향 또는 난수 흐름의 결과로 바꾸지 않는다.

공개 README의 앞으로 예상한 `HIGH_CHECKPOINT_REOBSERVE_TIMEOUT`은 작성자 source 예측이며 관측 결과가 아니다. R14는 checkpoint timeout 전에 공통 pose guard가 먼저 실패할 수도 있음을 보였다. R15의 attachment 결함도 향후 carry에서 회복 조건이 충족될 때 영향을 주는 별도 경계다. 현재 첫 실패, 조건부 다음 실패, 안전 검사 불일치를 같은 한 원인으로 묶지 않는다.
