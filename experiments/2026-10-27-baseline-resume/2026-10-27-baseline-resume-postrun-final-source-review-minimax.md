# 종료 후 집계·모델 수집 최종 추가 범위 MiniMax 검토

첫 요청은8turn Read 단계에서 error_max_turns로 판정 없이 종료했고 원문을 보존했습니다. 재요청16turn에서 아래 판정을 받았습니다. 원 실행 정책과 동결33/처치10파일은 변경하지 않았습니다.

## 판정: **CONDITIONAL_PASS** — 추가 범위 구조 검토 PASS, 미해소 구조적 차단 **0건**, 추가 범위 등록 불일치 **0건**(경미 공시 4건). 실측 대기는 별도 항목.

**구조 확인(추가 범위, 읽기 기준)**
- **trace cadence**: `issued` 누적 inference/discard==tick_index(:260), metric↔trace stage/hold/wheel 원장 대조(:286-290), metric cadence(:177-180).
- **READY**: policy/protocol × tick·robot-tick 4카운터 분리(:211-227, :324-325), GO/ACK/START·permit 별도 열(:228, :330).
- **close proposal**: C만 issued PWM감소 기준 집계, S는 null+scope 명시(:262, :334-337).
- **event_gate_funnel**: propose→discard→inference→stage→acceptance 순차, proposal 경로 한정(:387-396). rejected도 hold 명령이 나가므로 issued/nonzero_wheel은 별도 회계로 scope 명시(:416).
- **모델 수집**: receipt 존재·폐쇄와 GPU compute 프로세스 0 게이트 통과 후에만 SCP→동결 bytes/SHA 대조·overwrite 거부, receipt에 policy_forward_calls=0·training_steps=0·checkpoint_reselected=False(:23-50). plan 10파일 bytes/SHA가 동결표와 전건 일치, status는 PLANNED_NOT_COLLECTED.
- **motion**: 전20 무결성 관문 제거, 첫4 파일럿 재계산 대조만(:303-307, :364-371).
- **종료대조**: 미완료 sim/cap 포함(:422-430), protocol 관측원 태그(:331, :386).
- **state**: 250·251 두 값만, index252 없음(:279-284).
- **P14/P19**: sampled 접촉 첫 시각/틱과 `original_joint_hold_t` 분리(:318-321), 물리 이동은 진단 산출(:303-307).

**경미 공시(차단 아님)**: ①`close_proposal_ticks`는 PWM감소 대리치수이고 제안수준은 `treatment_close_gate_bypassed` 원장에 별도 계산되며 동일성 단정은 미수행 ②수집 게이트는 receipt 폐쇄만 요구하고 exit_code==0은 판정하지 않음 ③P-19 4열 산식은 `audit_cpu.read_physical_motion` 소관으로 이번 4개 파일 범위 밖 ④SHA 29792450… 동일성은 Read 제한으로 재계산 불가(경로 파일 내용 기준).

**실측 대기(미래·구조 아님)**: 종료 후 집계에서 issued 누적·READY 4카운터·stage/hold/wheel·close 수·event_gate 수치·sim/cap·파일럿 4월드 재계산·`termination-crosscheck.json`·`source-sha256` 바인딩, 그리고 모델 10파일 실제 SCP bytes/SHA 대조 결과.

## 공시 범위

C close 수는 원 C issue의 current proposal 무변환 코드와 실제 발행 PWM 감소를 결합한 도출값이며 별도의 원 proposal PWM 로그 독립 측정이 아닙니다. S의 전체 proposal PWM은 원 기록기에 없어 null입니다. G1 bypass는 withdrawal stage의 부분 관측입니다. 모델 수집은 실패·중단 실행에서 사용한 모델도 보존하는 목적이므로 exit0을 요구하지 않고 폐쇄 receipt와 GPU compute0을 요구합니다. 이는 실험 성공 판정이 아닙니다. 물리 이동 원4열 산식은 동결 audit_cpu.py와 첫4 실측 재계산으로 확인하며, 검토 Read 도구는 SHA를 재계산하지 않았으므로 실제 배포 바이트 해시는 운영자가 별도로 확인합니다.
