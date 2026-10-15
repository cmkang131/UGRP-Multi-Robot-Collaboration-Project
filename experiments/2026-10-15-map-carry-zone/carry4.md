# Solo 구역 운반 4차 — 독립 검토 결함 일괄 수정

PR #505, `claude/map-carry-zone`. 시작 소스는
`de8c24125c8bc8966ec82fb3935e7e0eb5005053`; 사용자 전달 Claude 검토의 대상은
`84a1b7b85bcbeb036ddd51a843b0908f8feb341b`이다. 검토의 물리 원인을 새로 판정한 기록이 아니라
소스 수정과 오프라인 반례 검사 기록이다. 새 실행 소스는 이 파일을 포함한 커밋이며,
push 후 `outputs/e2e18-admin/vm3-queue/20261015-solo-carry-<SHA8>.json`에 전체 SHA를 고정한다.
실행 승인·제출·학습·관문 승격은 모두 하지 않았다.

## 수정

1. `scripts/make_solo_teacher_plan.py`의 carry 전용 배치는 **실제 선언 시작점을 먼저 적용**한다.
   pickup·모든 목적 구역·문 접근 영역에서 주차 중심을 최소 0.33 m 떨어뜨리고,
   정적 pickup 접근/운반 경로에서 0.59 m(운반 반경 0.26 + 주차 반경 0.18 + 여유 0.15)를 둔다.
   정적 벽·다른 화물·작업 로봇과의 기존 여유 검사도 적용한다. 옛 기본 생성 경로는 그대로다.
   이 계산은 장면 배치 전용이며 제어기에는 주차 좌표나 사전 계산 경로를 전달하지 않는다.
2. `sim/solo_carry_obstacles.py`는 자기 RGB 색/윤곽, 기존 화물 외형, fisheye 보정,
   발행 서보 FK와 자기 명령 자세만 받는다. 바닥/차체 평면 가정으로 추정한 다른 로봇·화물의
   disc를 들기 전부터 기억하고 **held 상태에서도 2 Hz 및 holding 전환 시 갱신**한다.
   미관측을 빈 공간으로 바꾸지 않는다. 잡은 물체는 발행 집기/팔 자세의 ray-box 마스크로
   제외하고 pickup 기억 하나만 제거한다. 같은 색의 다른 화물은 계속 인식한다.
   `CarryToZone.start/step`의 A*·목적 접근·waypoint 검사에 이 목록을 넘긴다.
   모든 기억 disc는 A*가 경로 실패 때 없애지 못하는 형태로 전달한다.
   켠 경로에서는 기존 가시성 판정 뒤 정답 좌표를 읽던 `refresh_obstacles`를 호출하지 않는다.
   raw 틱 기록에 `carry_obstacles`를 남긴다. top 영상은 제어 입력으로 받지 않는다.
3. carry re-look은 `LookaroundLocalizer`의 기존 wall/zone/door 특징 모델과 잔차를 재사용한다.
   scalar chi² 6.63, 최소 잔차 3개·독립 그룹 2개·자세 rank 3·inlier 80%,
   prior 대비 3차원 innovation chi² 11.345, 정보 증가 0.05 이상을 모두 요구한다.
   `grid` 존재만으로 fix를 세지 않는다. 거부 시 자세·공분산을 복구하고 fix 시각/횟수를 유지한다.
   공용 localizer의 기존 경로는 기본 off이며 이 수용 검사는 carry에서만 켠다.
4. runner는 `now - previous['t']`를 적분한다. 펄스 만료는 `min(dt, duration)`으로 처리하며,
   1초 초과 간격·시간 역행/중복 적분은 거부한다. 오차 예산 근거는 아래에 분리했다.
5. `de8c2412`의 동일 탐색 명령을 **시뮬레이터 생성 없이** 명령 FK로 재계산했다.
   pinhole과 fisheye 양쪽 화면의 8 px 안쪽에 28/28 셀 중심이 들어왔다(최대 2.81 m).
   거리 2.3 m·오른쪽 -54° 지점도 완료 뷰에 들어왔다. 따라서 이 검사 대상에는
   몸 회전/접근 단계를 추가하지 않았다. 실제 가림·서보 처짐·검출 성공을 뜻하지 않는다.
6. `SoloTeacher.diagnostic`의 carry/pickup 키, `SoloLookaround.record`의 carry 관련 키는
   carry를 켤 때만 쓴다. carry 도입 전 `4e387d394dbd1e81d1e7bdf4725df1c2d5616819`에서
   추출한 성공 명령 시퀀스·context·diagnostic **291,918바이트**와 기본 off 출력이 일치했다.
   실제 원본에서 만든 SHA fixture와 legacy lookaround JSON 비교를 함께 고정했다.

## 명령 오차 예산과 한계

기존 10% 오차를 틱 변위마다 제곱해 합산하면 같은 거리도 더 작은 dt에서 오차가 줄었다.
새 carry 전용 모델은 공분산 전파에 더해 마지막 수용 fix 이후 **누적 명령 거리의 25%**,
**누적 절대 회전의 25% + 거리당 0.10 rad**를 상관된 오차 예산으로 더한다.
0.50 m·20° 한도는 기존 값을 유지했다. 한도는 정밀 놓기 허용 오차나 안전 보증이 아니다.
25%는 측정 fit이 아닌 미보정 개발 가정이며, `uncertainty_calibrated=false`와 전체 계수를 기록한다.
이미지 수신만으로는 예산을 초기화하지 않고 수용된 RGB/명시적 AMCL fix에서만 초기화한다.

검토한 실패 93200 기록은 주행 명령이 없어 이동 오차 fit에 쓸 수 없다(`carry3.md`).
`experiments/2026-10-06-drive-friction/README.md`의 v7 기록도 기존 하중 gain/odometry를
승계하지 않고 하중·자세별 재보정을 요구한다. 이번 조건과 같은 GCP 기종·운반 자세의
명령 대비 이동 잔차 측정값은 확인하지 못했다. 다른 구동/하중의 수치를 이 계수로 옮기지 않았다.

0.35 wheel duty 명령만 재생한 반례에서 전진 1.626 m(명령 시계 9.1초),
제자리 회전 73.42°(0.9초)에서 실제 guard가 닫혔다. **물리 이동 측정이 아니다.**
0.08/0.12초와 0.10초 분할은 같은 총 명령에 같은 자세·오차 예산을 냈다.
현재 설정은 긴 무보정 접근/운반을 중단할 수 있다. 한도를 완화해 완주를 만들지 않았으며,
실제 계수 보정·중간 위치 보정의 충분성·운반 성공은 원격 승인 이후 검증 대상이다.

RGB 장애물의 평면 가정·색/크기 판별·명령 FK는 실제 깊이/측정 관절이 아니다.
거리 여유 0.06 + 0.08×거리 m, 미관측 peer 추가 여유 최대 0.20 m도 미보정이다.
거짓 검출·가림·원거리 누락을 새 실행 영상으로 점검해야 한다. 원본 성공률을 주장하지 않는다.

## 새 계획과 검증

- `diagnostic-plan-v4.json`: **93220–93227**, 4색×2, 모든 주차 검사 통과.
  새 시드로 시작 jitter·주차를 다시 생성했다. 기존 세 계획/대기열은 덮어쓰지 않았다.
- 추가로 드러난 정적 조건: `zone_wide_door_geometry_v3`의 문 0.50 m는 기존 운반 외경
  0.52 m보다 좁다. 그 지도를 배치 후보에서 거부하고, 실제 정적 경로가 있는
  `zone_wide_two_doors_final_v3`의 s2/s7/s8에서 8개를 뽑았다. 운반 반경을 줄이지 않았다.
  따라서 이전 8개와 동일 배치 비교가 아니며 합산하지 않는다.
- 새 8개 조건의 화물 표본 시야/평면 LOS 8/8, 시작 오차 모서리 시야 64/64.
  상세는 `carry4-geometry.json`; 명령 예산 반례는 `carry4-command-budget.json`이다.
- 관련 7개 파일 **121 passed in 65.88s**. 최종 출력 메타데이터·compact plan 저장 후
  핵심 **13 passed in 10.62s** 재확인. 명령은 아래, 출력은 `offline-tests-carry4.txt`와
  `offline-final-carry4.txt`에 있다. 새 반례 파일을 CI 오프라인 목록에도 등록했다.
- runner는 가짜 backend만 사용했다. 불규칙 틱·held 중 갱신·top decode 거부·held truth 읽기 0,
  기본 off 바이트, 거부 fix 복구, 동색 비-held 물체 유지, 경로 우회/차단을 검사했다.
- 확인 가능한 로컬 등록부 4개·열린 PR의 등록부 3개에서 시드 충돌 0건.
  다른 열린 PR 16개는 해당 등록부가 GitHub API 404여서 그 파일로 확인하지 못했다.
  VM 실행 이력상의 미사용 여부는 확인하지 않았다(`carry4-seed-check.json`).
- 새 물리·렌더·원격 제출·모델 호출 **각 0회**, 8개 모두 미제출.
  정확한 새 SHA의 독립 검토/승인, 원격 시드·예산·저장공간·속도 및 첫 영상 검증이 남는다.
  새 대기열은 `approved=false`, `ready=false`, 8개 `enabled=false`로 저장한다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_solo_carry4.py tests/test_grasp_act_solo_carry.py \
  tests/test_grasp_act_solo_lookaround.py tests/test_lookaround_localization.py \
  tests/test_grasp_act_solo_run_path.py tests/test_grasp_act_solo_teacher.py \
  tests/test_grasp_act_solo_recording.py
```
