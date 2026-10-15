# warp3: ACT 경로 MJWarp 후속 이식

진행 중. PR #534, `claude/warp-act`. Mac 물리·렌더·GUI/모델 호출 없음, gcp2 L4만 사용한다. 결과는 로컬 프로젝트와 해당 VM 영속 디스크에 보존한다.

1단계 **PASS**: source `e200c1e5a475cd510031f26fc7e9ed821db81a9b`, N16에서 시작 매니페스트/qpos/첫RGB가 각각16개, qpos 기대=실측16/16. RGB120쌍 모두 다름(최소213766픽셀·평균 채널 절대차 최소2.9452). [몽타주](distinct-first-rgb.jpg) 직접 확인·회수 SHA 검증. [정량 증거](distinct-proof.json). 한 물리 모델의 시작 진단이며 독립 교사 관문 n=0이다. 과거 N>1 결과는 제외한다.

2단계 **RUNNING**: 수치 경로 source `f0db6b1abb842ea65b71c433738210254f300a7c`. IK의51 pitch를 NumPy로 옮겼고 기존 SDK240입력의 PWM/거부 결과가 일치했다. ray는 GPU 묶음, transform은 GPU에서 직접 읽는다. 독립적인 Python 교사 상태 기계는 유지한다(전체 FSM 벡터화라고 보고하지 않는다). rollout에서 C ray/kinematics 호출을 금지한다. 고정 upstream sleep의 단 하나의 dof_length 읽기를 world별 원래 값으로 인덱싱해, 값을 버리거나 근사하지 않는다. 설치된 원본 SHA가 다르면 거부한다.

N16의0.1SIM초 배관 점검은 완료됐으나 성공 관문이 아니다. 새 장면 C312 참조40개를 만들고, 비배치 배열·스칼라가 완전히 같은7그룹으로 나눴다(7/3/12/10/6/1/1). 첫7개를 run-first로 제출했고 나머지33개는 첫 결과를 기다린다. 초기 target 가시성 C/GPU counts7/7 일치는 평가 전용 참고이며 C 물리 동등성 관문이 아니다. [승인 대기열](teacher-gate-queue-r1.json), [누적 통과 표](gate-rejection_table-r1.json), [모델 그룹](model-groups.json). 승인 기록은 `APPROVED_PINNED`, `REVIEW_SKIPPED_BY_USER (10/15 run-first rule)`이다.

3·4단계는 40회 자체 교사 관문 ≥95%가 확인된 뒤 진행한다. 기록 본실행·학생 평가·warm 처리량은 아직 미실행이다. [후속 API 계약](api-contract.md)은 설계 기록이며 실행 준비 완료가 아니다.

관련 비물리 시험20개 PASS. 실행 소스는 먼저 commit/push했고 원격 사본은 git-shared.git을 직접 reference한다. 공유 객체 저장소의 기존 누락26개 blob은 exact 객체 전송으로 복구했으며 다른 source/원본을 삭제하거나 gc/prune하지 않았다. bootstrap의 nearclip 이름/옛 벽 질감 오류2개는 [별도 사유 표](bootstrap-rejection_table.json)에 남겼다.

[참고 문헌·설치본 검증 범위](references.md). 모든 성공·실패·cap_end·HOST_ERROR를 별도로 집계하며 최종 판정은 진행 완료 뒤 갱신한다.
