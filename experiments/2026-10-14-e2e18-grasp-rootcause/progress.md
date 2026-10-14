# 재개 기록

2026-10-14 범위 변경 후 첫 저장점. 작업 브랜치 `claude/e2e18-grasp-rootcause`; 시작 SHA `d7f13494b3673c0205266119fe082ed92b660f73`.

완료: 작업 지침/열린 PR 확인, PR #461 작업 범위 댓글, 기존 ACT/교사/IK 경로 열람, Azure 승인 구독 VM 목록·Korea Central GPU 할당량·공개 가격 읽기 전용 확인. 새 실행·학습·모델0. 원본 감사는 미완료.

다음: (1) 가벼운 기존 원장으로 깔때기·기하 오차 요약 (2) 새 입력 계약/교사/ACT adapter와 관련 오프라인 검사 (3) 커밋·push (4) VM 사용 허가 후 교사 20개 이상/16동시 게이트. 500 에피소드 수집은 교사 성공률을 확인한 뒤 정한다.

VM 사용 조건: **PR #483의 “VM3 비움” 코멘트 또는 조정자 확인 전에는 VM3를 사용하지 않는다.** 다른 작업은 변경/정지하지 않는다. GPU 자원 생성·크기 변경·할당량 변경·IAM 변경은 미승인이다.

로컬 원본 위치:

- `/Users/changmin/projects/ugrp-wt/e2e18/outputs/azure3-runs/`와 `azure4-runs/`: ownmap/commands/frames/trajectory/result 경량 원장. 읽기만 한다.
- `/Users/changmin/projects/ugrp-wt/e2e18/experiments/2026-10-13-e2e18-grasp1/`, `2026-10-14-e2e18-{approach-recovery,color-detector,reacquire,pose}/`.
- ARM `oracle:/home/ubuntu/ugrp-archive/runs/native-<run>/`.
- 본 작업 `outputs/grasp-rootcause/`: GPU 조회 응답, 대표 scene.xml/json, 공동 held 평가 원장. 비밀 없음.

분모 주의: approach-recovery24와 color-detector24는 각각 30초 예비12+본12. stage-track v434–439는 완료 gate만 조사한다. 10.65cm/11.15°는 별도40개 단계 실행(80개 로봇 궤적)의 이전 요약이고 재측정 전에는 독립 확인으로 쓰지 않는다.

후속 저장점: 기존 원본72실행(각24개)의 단계/오차 재집계 완료, `saved-audit.json.zst`에 원본별 해시·경로, `summary.json`에 표를 기록했다. 영상 두 대표 실패 각6프레임 직접 확인. r69/r76/r80 전 단계 독립 재집계 및 카메라/팔 영역 계산은 미완료로 명시. 교사/ACT 물리 실행0, 학습0.

확정 스킬 경계 구현: `harness/grasp_act_contract.py`, `grasp_act_skill.py`. 색 끝 one-hot, 정답 입력 거부, 이전 끝/스킬 청크 폐기, 종료와 자기 영상 확인 분리. 다음은 v3 정답 교사와 ACT adapter/데이터 loader, Kaggle 준비. VM3는 여전히 명시적 비움 확인 전 미사용. Kaggle private 업로드는 후속 사용자 승인됨.

2026-10-14 ACT 하나/멀티태스크 후속 결정: 입력 schema v2, `grasp|wait|regrasp|release` + 화물9종 + 자리8종, r1/r2/r3. 이전 beam-only schema v1로 새 모델을 학습하지 않는다. 교사/장면/데이터 export/재개 학습 코드 작성, 물리 실행 전이다. CPU 실제 ACT 검사2/2 및 오프라인23/23 통과. 첫 optional 검사 import 경로 오류는 수집 단계에서 실패했고 고친 뒤 통과했다.

`teacher-gate-plan.json`: pair20개·고유seed20·r1 청록10/20·파랑10/20·벽근처1/20. 실제 s1/s3/s6 배경을 사용하며 원 화물은 모두 유지한다. s1–s8 v3는 구 하드웨어이고 v4가 같은 작업의 현재 v3 하드웨어 대응본이므로 v4를 선택했다. 중간 적재 상태·동작 중 짝·1대/3대 화물 교사는 아직 미구현이다. 등록 workflow `grasp-act-teacher@1.0.0` (기존 v숫자 번들 변경 없음).

다음: 학습/수집 코드 오프라인 회귀·Kaggle 인터넷 OFF GPU 패키지, own-RGB 학생 실행기/별도 종료 확인. VM3 명시 비움 대기 계속. VM3 허가 뒤 먼저 물리 교사20개와 속도게이트, ≥95% 통과 전 수집 규모를 늘리지 않는다.

2026-10-14 11:38 KST VM3 해제 확인. `4d0161ae` 커밋·push 완료 후 `grasp-teacher-pilot-4d0161ae` 30 SIM초 진단을 표준 원격 실행기로 제출했다. VM3 F16als_v6 running, 새 실행 전 복구/보관 확인 중. 20개×256 MiB 예산 검사 통과: VM3 47,591,608,320 B, ARM 39,683,833,856 B, Mac 106,941,198,336 B 여유(실행 전).

후속 배치 실행기: 16동시×30 SIM초, 중앙 wall/SIM≤3.5, 미완료 게이트 거부. 5분 감시 기록·물리 실패/HOST_ERROR 시 해당 파동 정지·시작/완료/중단 분모 분리. 대표 평가용 top 영상을 1 Hz로 원시 자료에 추가하며 학생 파일에는 넣지 않는다. 관련 오프라인6/6.

새 지도/전체 기록 결정: 절차 지도(벽·문 위치/폭, 집기/목적 구역, 방해 화물), 지도별 정적 파일/해시와 지도 수·지도당 시연 수를 남긴다. s1–s8 연구 지도는 평가용으로 옮기고 최소1개 지도는 완전히 학습 제외한다. 현재20개는 교사 진단용 연구 배경이며 학습 시연으로 자동 전환하지 않는다. 전체 주행/접근/집기/운반/놓기 기록을 보존하되 현재 학습은 근거리 집기/놓기만 쓴다. 운반/놓기 교사 및 절차 지도 생성은 첫 봉 교사의 물리 오류 수정 뒤 구현한다.

첫 진단4d0161ae: 30 SIM초/182.70 wall초, 공동0/1·로봇0/2(모두상한종료), 정식성공률코호트0회. r1 고정 사전 접근점이 지도 차체 여유 밖이라 경로 없음. 0–29.9초 균등6시점 자기 카메라 직접 확인. `teacher-pilot-4d0161ae.json` 참조. ARM archive-one 성공, 보관 영수증 verified. 첫 fetch-lite의 원본은 회수됐으나 동시에 바뀐 lifecycle 검증은 실패하여 재확인 필요.

수정: 차체 여유를 만족하는0.50/0.40/0.30/0.25m 사전 접근점 선택(이번 시작0.40m), 관련19/19. 영상은 카메라 위치/FOV/4:3 화면비를 유지한320×240·5Hz, 명령/라벨10Hz로 기록해 수집 비용을 줄이는 별도 후보다. 평가 top1Hz와 물리/렌더/교사 시간 분해를 추가했다. 다음16동시 게이트에서 실제 속도를 판정한다.

12:20 방향 반영: 기존 zone_teacher 연속 비례 주행을 공통 함수로 재사용, v3 IK/연속 ACT schema v3/공통 native 포트. 4 mm·1도 펄스와 긴 사전 후퇴 퇴역. 관련26/26 통과. 측정은 학생 RGB 끄고 검토 top1Hz, 학습 기록은 38/40 관문 이후에만 허용. `teacher-gate-plan.json` 40개로 교체, 가까운0.509m/먼1.925m 별도 진단을 먼저 수행. 중단16개 관문0/0(원시1/1 집계와 다름); 전체 펄스 감사와18시각 직접 본 범위는 interrupted-pulse-audit.json.
