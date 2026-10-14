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
