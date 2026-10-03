# 2026-10-03 보정 수집 실행 기록 (v88 r8, v91 held-out)

Refs #219 #344. 이 문서는 **운영 기록**이다. 끝났는지, 얼마나 걸렸는지, 그때 컴퓨터 부하가 어땠는지,
파일 해시와 개수만 적는다. 기계가 읽는 같은 내용은 [run_record_20261003.json](run_record_20261003.json)에 있다.

## 자료 취급 (먼저 읽을 것)

v91 두 수집은 아직 채점하지 않은 **held-out(따로 떼어 둔 검증) 자료**다. 얼려 둔 기준 B(criterion B)의
채점기(validator, PR #356)는 독립 검토 중이다. 그래서 v91의 움직임·자세 오차·덮임(coverage)·적합
지표는 계산하지도 기록하지도 않았고, 이미지도 열지 않았다. 아래 수치는 모두 신원·완료 여부·시각·부하·
해시·파일 수·바이트 수다. 수집 전 약속은
[#219 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5958329647)에 있다.
v88 r8도 같은 운영 항목만 적었다. 로컬 raw는 원격 백업이 아니다. raw는 읽기만 했고 수정하지 않았다.

## 수집 목록

공통: seed 911, 370 SIM초(+reset 1.3 SIM초), 결과 `COLLECTED_UNQUALIFIED`, `protocol_complete=true`,
`physical_success=null`(성공 판정 아님), 파일 3,725개씩. 경로는 모두 `/Users/changmin/projects/ugrp/outputs/` 아래.

| 수집 | 소스 / 번들 / workflow | 시작 → 끝 (UTC) | 실제 시간 | 부하(1분) 시작 → 끝 |
|---|---|---|---|---|
| v88 loaded r8 (`final-pair-v88-cal-747d2b9f-20261001-r8/calibration-loaded`) | `747d2b9f` / zone-final-pair-v88 / zone-final-pair-v3 3.1.0, 옛 guard 코드, 지도 zone_wide_two_doors_final_v3 | 10-02 14:59:29 → 18:33:46, rc=0 | 3 h 34 m 17 s (12,857 s) | 48.42 → 7.87 (로그 51.59, swap 사용 6,176 MB / 7,168 MB) |
| v91 door (`final-pair-v91-heldout-04043e27-20261003/zone_wide_door_geometry_v3`) | `04043e27` / zone-final-pair-v91 / zone-final-pair-heldout-v91 3.3.0, 빠른 guard | 10-02 18:33:47 → 18:40:02, rc=0 | 6 m 15 s (375 s) | 9.48 → 12.17 |
| v91 corridor (`.../zone_wide_corridor_final_v3`) | 위와 같음 | 10-02 18:33:47 → 18:40:21, rc=0 | 6 m 34 s (394 s) | 9.48 → 9.79 |

v91 두 지도는 SIM 슬롯 두 개로 동시에 돌렸다(슬롯 `sim-claude-v91-door`, `sim-claude-v91-corridor`,
코디네이터 PID 47703). 실제 시간은 `driver_log.txt`의 시작·끝 시각 차이다. 부하는 각 `result.json`의
`loadavg_start/end`다.

**실패한 첫 실행 (자료 없음).** 10-02 18:01:10Z에 첫 v91 실행이 슬롯 규칙에 막혔다
("slot coordinator PID must be the lock holder that outlives workers"). 수집은 시작도 하지 않았고 자료가
없다(종료 시 부하 16.77). r8이 끝나기를 기다렸다가(18:03:15Z, 부하 14.81) 18:33:47Z에 자기
코디네이터 잠금을 잡고 다시 띄웠다. 근거는 같은 `driver_log.txt`다.

## 해시 (sha256)

| 수집 | plan.json | bundle.json | 사례 result.json | 전체 result.json | artifacts.sha256.json |
|---|---|---|---|---|---|
| v88 r8 | `94b5c6fc…3ff60d` | `ce773d59…67966a` | `a314a23f…71fa36` | `a58ac3ba…1fc208` | `ecf3ce0c…a7b553` |
| v91 door | `f1764544…8e8562` | `5e5c1af9…f5b698` | `c50f9582…f44ce2` | `0c40e1e6…5e8619` | `541b5660…510e07` |
| v91 corridor | `6afba91b…d14770` | `52b160ef…75b3b2` | `184d8199…ba7e99` | `6a858761…a81bf3` | `a8bf5d06…998b60` |

전체 64자리 해시와 `driver_log.txt`, 시뮬레이션 기록 manifest의 해시, 파일 수·바이트 수는 JSON에 있다.
수집별 바이트는 r8 107,936,922 / door 115,047,801 / corridor 114,320,798이다.
번들 목록 해시(plan의 `bundles_sha256`): r8 `095bdca5…90d659`, door `b8871bb8…68900d`,
corridor `c52a72bf…c9dad2`.

## #351 조립 첫 시도 실패 (v88 세 수집)

- 첫 실행: `ModuleNotFoundError: scipy`. `requirements-test.txt`가 고정한 `scipy==1.17.1`을
  `.venv-sim-worker-mac`에 설치해 해결했다(numpy 2.5.2, mujoco 3.12.0은 그대로).
- 둘째 실행: 결과 `PARTIAL`. 세 수집(unloaded, fine, loaded) 모두 수집 감사(audit)가
  "r1 frame clock must be a finite numeric time"로 실패했다. 출력은
  `/Users/changmin/projects/ugrp/outputs/final-pair-v88-measured-20261003`
  (calibration.json `c28aaf08…99e7aa`, fit_report.json `4b99d1c4…bee067`).
- 원인: 조립기(assembler)는 `frames.jsonl`의 키 `t`를 읽는데 실행기는 `sim_time`으로 쓴다.
  고치는 일은 별도 PR(브랜치 `claude/calib-assembly-clock`)이 한다. 이 PR에서는 고치지 않았다.
- 참고: 옛 `final-pair-v88-cal-747d2b9f-20261001/calibration-fine` 폴더에는 `result.json`이 없다
  (끝난 수집으로 기록하지 않음, 조사하지 않음).

## 속도에 대한 정직한 메모

같은 370 SIM초가 걸린 실제 시간은 아래와 같다.

| 실행 | 프로필 / guard | 실제 시간 | 실제초/SIM초 |
|---|---|---|---|
| v88 loaded r8 | loaded, 옛 guard, 접촉 많음 | 3 h 34 m (12,857 s) | 약 34.7 |
| v88 unloaded (2026-09-30~10-01) | unloaded, 옛 guard | 2 h 08 m (7,673 s) | 약 20.7 |
| v91 door / corridor | unloaded, 빠른 guard, 두 지도 동시 | 6.3 m / 6.6 m (375 s / 394 s) | 약 1.01 / 1.06 |

더 가까운 비교는 같은 unloaded 프로필인 옛 v88 unloaded 수집(`final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded`,
23:32:47Z → 01:40:40Z, rc=0)이다. 다만 그 실행은 끝날 때 컴퓨터 부하가 1분 평균 333까지 올라가
(시작 15.43) 다른 작업과 자원을 나눠 썼다. 이 표는 **통제된 속도 비교가 아니다**. 프로필, guard 코드,
지도, 부하, 동시 실행 여부가 모두 다르다. "빠른 guard가 몇 배 빠르다"고 읽지 말고, 빠른 guard 쪽이
실제로 370 SIM초를 약 6~7분에 끝냈다는 관측으로만 읽는다. guard 코드 자체의 동등성은
[이 폴더의 다른 기록](README.md)을 따른다.

## TensorBoard

새 스냅샷 `outputs/tensorboard/1003-calib-v91-record` (런 6개: r8 loaded, v88 unloaded, v91 door,
v91 corridor, 첫 실행 거부, #351 조립 실패). 값은 운영 지표(wall_s, sim_s, 부하, 완료·실패 건수)만이다.
원본으로 가는 읽기 전용 파생 뷰는 [tb_views/](tb_views/)에 있고 각 뷰가 원본 파일의 경로·sha256을 건다.
기존 스냅샷과 다른 키는 건드리지 않았다. 열기:
[TensorBoard](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fsim_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fload_start_1m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fload_end_1m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fprotocol_complete%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fload_exit_1m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcollections_started%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcollections_audit_fail%22%7D%5D&smoothing=0&runFilter=%5E1003-calib-v91-record%2F#timeseries)
(런이 500개를 넘어 처음에는 선택이 꺼져 있으니 왼쪽 맨 위 체크박스로 선택한다).

## 참고 자료

- 이 저장소의 기존 변환기 `scripts/export_offline_audit.py`와 [docs/tensorboard.md](../../docs/tensorboard.md)를 그대로 썼다(새 도구 없음).
- 수집 전 약속: #219 코멘트(위 링크). 빠른 guard·슬롯 설계: [README](README.md), PR #355.
- 열린 후속: 조립기 clock 키 수정(`claude/calib-assembly-clock`), 기준 B 채점기 PR #356 검토.
