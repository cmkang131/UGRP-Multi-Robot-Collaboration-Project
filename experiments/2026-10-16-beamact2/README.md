# beamact2 — 빔 짝 ACT 학습과 학생 평가 (진행 중)

beamact1 PR #540·같은 브랜치를 이어간다. TRAIN166/60,023행·validation19/6,908행·reserved20 분할과 정규화, batch8/chunk8/10Hz, seed20261015, balanced_bce_v1, wheel_pulse_train_mean, 최종10000step 고정 선택을 유지한다. validation/보류20으로 모델을 선택하지 않는다.

사용자 지시로 기존 gcp2 L4를 warp3와 공유한다. 2026-10-16 07:33 KST GPU 사용5817/23034MiB·util100%, 기존 ACT 예약 메모리2057306112바이트(동일 구조 actgpu1 기록)였다. 기존 /home/ugrp/ugrp-rl1b-act-env는 pinned LeRobot89236ea0·torch2.11.0+cu128과 일치했다. GPU 시간은 shared-load이며 속도 판정 자료가 아니다. warp3의 프로세스·VM·유휴/8h/budget-stop은 변경하지 않는다. 데이터20GiB·체크포인트/분석4GiB 예약, L4 제출 전38GiB 여유라8GiB 바닥을 보존한다. Mac에는 요약·실패 프레임/영상만 회수한다.

학생 실행기는 교사 객체를 만들지 않는다. 자기 RGB4장·실제 발행16명령·고정 스킬/물건/색 끝 토큰·자기 명령 시계만 격리 CPU worker에 전달한다. 정답은 evaluator의 결과 원장에만 쓴다. held_object_hidden_v1은 학생에게 화물 좌표 경로 자체가 없어 상시 충족하며 invisible_measurements/held_world_reads=0을 입력 allowlist로 검사한다. 근거리 명령은 ACT만 낸다. 통신은 pinned dependency26f84d0f의 GraspStartSync READY/GO/ACK를 그대로 쓴다.

ACT14차원에 READY head가 없어 자기 집게 닫기 proposal을 READY로 해석한다. OPEN2000/CLOSED1500의 방향에 따라 직전 발행보다 PWM이 감소하면1PWM이라도 READY다. 새 물리 수용 상수는 없다. 초기 구현의1750 최근접 분류는 평가 전 검토에서 제거했다(그 경계까지 부분 닫기를 먼저 발행할 수 있기 때문). GO/ACK와 원래0..1.5SIM초 지연을 통과할 때까지 ACT proposal을 보관하고 이전 PWM·정지 wheel을 발행한다. 허용 뒤 정확히 그 proposal을 발행한다. 대기 때 모델 추론/교사 동작/인식 보정은 없다. 완료는 학생 done과 기존3.1SIM초 관찰 창, 또는60SIM초cap뿐이다. 평가 정답으로 실행을 끝내지 않는다.

보류20은 기존 beampair8 heldout-plan을 그대로 쓴다. 원래 시작 분포(.5..2m)와 학습 local 선정(.8m 이내)의 범위 차이는 남기며 정답으로 시작 위치를 바꾸지 않는다. 평가 퍼널 접근(.8m)·명목 정렬(.203m station, .03m/.06rad)·READY·양 집게 접촉(.5N)·3초 들기(.012m/10도)는 기존 교사/평가기 수치를 재사용한다. 명목 정렬은 teacher의 대체/표본 자세 전체를 대표하지 않으므로 원시 geometry·단계별 독립 통과도 함께 남긴다. 최종 성공은 양 학생 완료+안정 공동들기3초+cap아님+감사0이며 교사와 합산하지 않는다.

실패 전10SIM초10Hz 자기 카메라 ring은 기록 전용으로 켠다. 전체2Hz overview/r1/r2를 보존하고 gcp2에서 영상·프레임 띠를 만든다. Mac GUI는 열지 않는다. 아직 학습/평가/Release 완료를 주장하지 않는다.

참고: [ACT 공식 코드](https://github.com/tonyzhaozh/act)의 chunk 예측/closed-loop 실행·batch8/lr1e-5 구조와 기존 프로젝트 adapter를 재사용했다(2026-10-16 확인). [원 논문](https://arxiv.org/abs/2304.13705)은 이번 웹 재조회 실패이며 기존 beamact1의 참고자료다. READY proposal 연결은 프로젝트의 출력 제약에 필요한 설계이며 ACT 논문이 보증하는 성능이 아니다.

## 검증된 smoke300

소스 `ee1e2275bc5cb4a15278220214ebf1861d131fe7`, 기존 L4에서 실제 optimizer300step 완료. 저장/재로딩 후 TRAIN probe chunk의 `torch.equal`을 확인했다. wall303.400초, 최대 할당1,549,413,888B·예약2,057,306,112B이며 warp3 공유 부하이므로 속도 수용 판정에 쓰지 않는다. [원본 요약](smoke-summary.json). 학생 물리 성공을 뜻하지 않는다. main은 이 smoke의 정확한 source/data/mask/summary 해시에 묶어 총10000step까지 optimizer/RNG를 복원한다.
