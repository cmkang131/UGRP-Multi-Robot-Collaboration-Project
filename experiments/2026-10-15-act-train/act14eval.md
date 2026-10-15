# ACT14 — 고정 ACT13 체크포인트 검증·첫 폐루프 평가

사용자 요청 범위: p0/p02 각 검증5, 탐색3+새 시드20(본40). DEV이며 학생 성공의
독립 Haiku 재집계·채택은 별도다. 기존 체크포인트와 교사 원본은 보존한다.

새 `--teacher-start-v1`은 기본 OFF다. 켠 실행은 교사 `6f057f7e`의 고정 장면·물리·카메라
소스를 사용하고, `scene.setup` 직후 자기 발행 초기 PWM에서 시작한다. 기존 학생 경로의
추가 folded 명령/1초 대기를 사용하지 않는다. 교사 행동·IK·가시 정답은 학생에 넣지 않는다.
학생은 격리 CPU 프로세스에서 자기 RGB4장·발행 이력16개·고정 작업 번호표만 받는다.
시뮬레이션 시계 0.1초, chunk8·n_action_steps8·ensemble OFF는 기존 설정이다.
추가 교사 교정·외부 회복 외란은 없다. 계획은 노드/검사 수로 유한하며 학생은 경로 탐색을 하지 않는다.

계획은 [act14-plans](act14-plans/plan.json), 정적 관문/거부 분포는
[setup-funnel](act14-plans/setup-funnel.json)에 기록했다. 샘플러의 23개 시작 상태는
기존 교사 `make_solo_teacher_plan.episode`와 spawns/scenario/item/시도 수/추정오차가
전부 일치한다(물리 실행 없음). 시드91420–42는 act11/12와 분리한다.
이미 사용한 어려운 act11 시드를 재사용하면 새 시드 조건을 어기므로, 새 시드에서
같은 높은 시작 방위오차 층을 앞에 두었다. 본20개는 네 상자색 각5개다.

평가 funnel은 접근→정렬→집기→들기 확인의 누적 통과와 관문별 프레임 수를 기록한다.
기준은 **기존 고정 교사**의 station 오차8cm/정렬8mm·0.04rad,
기존 LiftScore의 양쪽 손가락0.5N·지면 이격12mm·기울기10°·3 SIM초 유지다.
새 수용 상수나 성공 기준을 도입한 것이 아니다. 기존 상수의 실기/분포 근거는 이번에
재보정하지 않았으며 이 표는 평가 기술용이다. 정답은 평가 원장에만 기록하고 phase/done/
학생 행동에는 사용하지 않는다. `cap_end`는 학생 done 없이90 SIM초에 닿은 실행이다.
거부표의 gap은 실제 손가락-대상 최소 거리다. 충돌 원인 미확인 시 `none_observed`로
표시하며 대상과 떨어진 거리를 장애물로 해석하지 않는다.

검증 손실은 고정 step10000 모델의 전체 train45와 validation5를 같은 eval/zero-latent
추론으로 계산한다. 이동 L1 + TRAIN 사전확률로 가중한 완료 BCE이며 VAE KL/학습 dropout은
제외한다. 기존 학습 총손실(KL·dropout 포함)은 별도 수치로 비교하고, 과적합은 동일 추정량의
train/val 차이로 평가한다. 체크포인트 선택이나 재학습에는 val을 쓰지 않는다.

실행 전 오프라인 시험: `tests/test_grasp_act_act14.py tests/test_grasp_act_pilot.py`:
13 passed, 1 skipped(Mac 환경에 torch 없음; L4에서 손실 검사를 수행 예정).
실제 수치·원본 위치·전체 해시·시도 실패/미완료·VM 종료 확인은 후속 요약에 기록한다.

탐색 소스 `3bd9e013` 뒤 본 시험 전 기록기만 보완했다. 정적 거부표의 가장 가까운 물체가
실제로 거부한 물체와 다를 수 있어, **실제 거부 predicate에 걸린 ID와 그 기준 대비 signed gap**을
기록한다(분포 start_blocked19, 후보42→통과23 그대로, 23개 계획 바이트 일치).
들기 funnel의 온라인 시각은 점수 갱신 뒤 기록해 1표본 지연을 없앴다. 원장 재집계기는
처음부터 현재 표본의 점수를 사용했다. 본 시험에는 비바닥 외부 접촉의 geom 이름/실제 contact
gap을 평가 전용으로 추가한다. 접촉을 측정하지 않은 이전 탐색의 blocker는 미측정으로 해석하며,
없음을 주장하지 않는다. 학생·장면·명령·완료/종료 선택 코드는 그대로다.

탐색 전체 원장의 평가상 안정적 들기는2/6, 그2개도 cap_end였다. 최초 funnel은 교사의
명목 자세를 학생의 필수 조건처럼 취급해 들기 통과와 불일치했다. 본 시험 전 기능 정렬을
명목 자세 **또는 기존 양측 접촉 기준의 충족**으로 정의했다. 양측 접촉/안정적 들기가
이전 관문의 기능적 통과 근거라는 논리적 포함이며 새 허용 오차를 넣지 않는다.
기존 들기 성공 기준·학생 코드·종료 선택은 바꾸지 않는다. 명목 자세를 재현하지 않았다는
이유로 실제 안정적 들기를 정렬 실패로 분류하지 않는다. 최초 표는 원본 경로/해시와 함께
보존하고 본 시험 큐에는 같은 원장으로 다시 센 수정 표를 연결한다.

참고: [고정 LeRobot ACT 구현](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/modeling_act.py),
프로젝트 `harness/grasp_act_loss.py`, `grasp_act_data.py`, `grasp_act_policy.py`,
교사 `6f057f7e:sim/grasp_act_solo_teacher.py`와 `scripts/make_solo_teacher_plan.py`.
인터넷 원문 도구 열람은 cache miss였으며 실행 호스트에 설치된 고정 구현을 확인한다.
