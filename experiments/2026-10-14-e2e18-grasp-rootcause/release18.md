# release18 — 중복 명령 대기와 구역 안 추가 중앙 맞추기 (2026-10-15)

기준 `6b263c9beb14757f88b76edd01088c6a46182a2f`, 같은 worktree/브랜치, PR #491.
회수 원본 4실행의 result/plan/양쪽 teacher/eval 원장 **20파일**을 manifest의 저장·복원 SHA-256으로 검증했다.
기존 release17 재현은 **1/2**(74963 성공, 74976 timeout), release18 물리 실행은 **0회**다. 합산 금지.

## 직접 확인과 단계별 시간

74976 영상은 운영 montage 두 장의 **11시점 × 개요/r1/r2 = 33프레임**을 직접 봤다:
0, 6, 12.3, 18.3, 24.3, 30.3, 36.3, 71.3, 107.3, 143.3, 179.3초(실행 origin 기준).
먼저 관계를 확인했다: 표본에서 반대 끝 유지, 같은 끝 접근·상호 막힘 없음. 빈 집게 음성 코호트는 없으므로 오양성률은 미측정.
각 JPEG를 원본 manifest와 대조한 경로·해시는 `release18-visual-review.json`에 있다.

아래는 **동시에 움직인 양쪽 로봇을 중복 합산하지 않은 SIM초**다. 초기 prefix 파지 8.3초는 별도다.
release 시작(world t=10.1)부터 제어 종료(t=181.9)까지 **171.8초**;
prefix 포함 180.1초(0.1초 tick 경계), 별도 평가 2.5초가 붙어 result의 release_sim_s는 174.3초다.

| 구간 | 최초 내려놓기/관측 | 재파지·이동 1 | 재파지·이동 2 | 재파지·이동 3 |
|---|---:|---:|---:|---:|
| 시작 확인/ACK | 0.8 | 0 | 0 | 0 |
| 접근 전 선 정렬 | 0 | 7.9 | 7.7 | 7.5 |
| 접근 | 0 | 1.2 | 1.3 | 1.3 |
| 접근 후 선 재확인 | 0 | 5.9 | 5.9 | 6.1 |
| 파지 명령 | 0 | 6.1 | 6.1 | 6.1 |
| 순차 양단 들기 확인 | 0 | 13.8 | 13.8 | 13.8 |
| 재파지 ACK / 이동 | 0 | 0.1 / 1.8 | 0.1 / 1.8 | 0.1 / 1.8 |
| 낮추기 / ACK / 열기 | 2.4 / 0.1 / 1.5 | 2.4 / 0.1 / 1.5 | 2.4 / 0.1 / 1.5 | 2.4 / 0.1 / 1.5 |
| 재관측 전체 | 14.3 | 14.4 | 14.4 | 1.7 (미완료) |
| 합계 | 19.1 | 55.2 | 55.1 | 42.4 |

완료한 재관측은 지도 확보용 제자리 sweep 4.5초 → 지도 여유를 확인한 backoff → 새 sweep 4.5초다.
팔/후퇴/settle 3.6초와 관측/전달 1.7–1.8초가 더해진다. 세 회차 모두 localization accepted;
재시도나 회전 탐색이 길어진 것이 아니다. 마지막은 첫 sweep을 **0.6초만** 수행한 상태에서 잘렸다.

## 원인과 기본 off 수정 묶음

1. **3회는 파지 실패 재시도가 아니라 0.2 m 제한의 정상 위치 보정**이다. 각 선택의 r1 RGB 여유는
   −0.44085 → −0.24964 → −0.03726 m; 마지막도 요구 여유 +0.04 m 미달이다. 0.4 m만 옮겨서는 부족하다.
   release16 같은 74976도 첫 이동 뒤 −0.25583 m로 두 번째 보정을 골랐다. 첫 네 정렬 합계는
   release16 **18.4초** → release17 **13.8초**; release16은 두 번째 보정의 FOV 미진척으로 중단돼 이후 비교는 불가하다.
   release17 74976의 12정렬 중 yaw 명령은 **1회**, 요청 −0.006 rad → 하한 적용 공칭 −0.021 rad,
   다음 실제 RGB를 0.2초 뒤 확인하고 정렬 통과했다. 증폭은 있으나 부호 반전 연속 명령/진동은 **0회**다.
   yaw_cal·40 ms 하한·영상 확인 주기·데드밴드를 바꿀 근거는 없다.
2. **같은 열린 집게/hover의 대기를 다시 시작**한다. `settled_command_v1`은 접근 전 이미 1.2초 이상
   열린 명령이면 open 대기만 생략(hover 1.4초 유지), 접근 후 전체 PWM이 2.6초 이상 그대로면 2.6초를 생략한다.
   정확한 현재 명령·fresh 이력·빈 명령 큐·바퀴 정지·holding=false를 요구하며 retry에는 적용하지 않는다.
   새 RGB와 **0.3초 시각 안정**, 지도/이동 한도·짝 정지·들기 확인은 유지한다. 명령 경과는 측정 관절 상태가 아니다.
3. **구역 안에서도 중앙을 맞추느라 추가 재파지**한다. 실제 저장된 74963의 두 번째 선택은
   여유 **0.22790/0.54904 m**인데도 0.16057 m를 더 옮긴다. `inside_margins_v1`은 기존 축·측면·양단 slack
   일치 검사 뒤 두 여유가 모두 기존 **0.04 m** 이상이면 lower를 선택한다. GT fit을 제어에 넣지 않는다.
   74976의 마지막 sweep 이후 새 보고는 없으므로 그 지점의 완료 판정/추가 이동 여부는 **미확인**이다.

두 옵션은 `release18_v1` 전용이며 CLI/API 기본 off다. 새 진단 계획만 둘 다 켠다. **180초 상한 유지**.
용량 예산 96 MiB/회·9회 864 MiB, 학습 카메라 기록 off, 기존 원본 보존. 새 입력은 자기 RGB·명령 이력뿐이다.

## 오프라인 검증과 재현

`release18-replay.json.zst`: 동일 저장 특징열을 원래 순서로 실제 LineAlign에 공급한 scheduler 재생에서
74976 **12/12** 정렬 판정/바퀴 요청 동일, 대기 **22.8초** 생략(접근 전 6×1.2 + 접근 후 6×2.6).
74963 **8/8**, **15.2초**. 기존 명령 원장의 실제 margin_report로 pair_choice도 재생해
74963의 위 1건만 shift→lower로 바뀌고 74976의 저장된 세 보정은 모두 유지됨을 확인했다.
시각 입력을 앞당겨 공급하는 조건부 재생이며 새 물리 궤적·시간·성공률의 측정이 아니다.
관련 시험은 `release18-tests.txt` 참조. 물리/렌더/학습/원격 접속 0; held_world_reads/invisible_measurements는 네 원본 모두 0.

```sh
python3 -m scripts.replay_release18 --root /Users/changmin/projects/ugrp/outputs/gcp1-runs --out /private/tmp/release18-replay.json.zst
python3 -m pytest -q tests/test_release18.py tests/test_release17.py tests/test_release16.py tests/test_release15.py tests/test_grasp_act_release_run.py
python3 -m scripts.prepare_release18_queue --verify /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-release-gate-$(git rev-parse --short=8 HEAD).json
```

큐는 커밋 뒤 `python3 -m scripts.prepare_release18_queue`로 새 파일만 만든다.
재현 74963/74976 + 새 78520–78526, **승인·실행·준비 플래그 모두 false**. 이전 큐 불변.
main/열린 PR 22개/HEAD의 seed 설정·계획·Markdown과 로컬 큐에 새 시드 사용 없음;
원격 이력 점검·독립 Claude 검토·조정자 승인·재현 2/2 확인·새 7회·관문은 남아 있다.

## 참고 자료 (수정 전 확인)

- [ViSP 공식 IBVS 예제](https://github.com/lagadic/visp/blob/master/tutorial/visual-servo/ibvs/tutorial-ibvs-4pts-wireframe-robot-viper.cpp):
  매 반복 특징 갱신 → 제어 계산 → 다음 sampling 주기의 구조를 확인했다. 새 RGB 확인을 생략하지 않는다.
- [OMPL GoalRegion 공식 정의](https://ompl.kavrakilab.org/classompl_1_1base_1_1GoalRegion.html),
  [공개 헤더](https://github.com/ompl/ompl/blob/main/src/ompl/base/goals/GoalRegion.h):
  목표를 허용 영역의 포함 판정으로 정의한다. 4 cm 경계·시간 상수는 이 프로젝트의 기존 조건이며 외부 자료가 보장하는 수치가 아니다.
- Chaumette/Hutchinson 2006 논문 원문 URL은 접근 차단으로 읽지 못했다. 논문 내용을 검증 근거로 쓰지 않았다.
