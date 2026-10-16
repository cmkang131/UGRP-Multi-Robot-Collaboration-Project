# warp3: ACT 경로 MJWarp 후속 이식

**1–3단계 완료, 4단계 L4 단독 warm 측정 대기.** PR[#534](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/534), `claude/warp-act`. 기본 off인 MJWarp 경로다. Mac 물리·렌더·GUI/모델 호출 없이 gcp2에서 실행했다. 결과는 로컬 프로젝트와 VM 영속 디스크에 보존한다.

| 단계 | 확인 결과 |
|---|---|
| 서로 다른 시작 | N16 매니페스트/qpos/첫 RGB 각각16개, 기대 qpos=실측16/16. RGB120쌍 모두 다름(최소213766픽셀). [정량 증거](distinct-proof.json), [직접 검토한 몽타주](distinct-first-rgb.jpg). 복제 부하를 독립 교사 n/N에 세지 않는다. |
| 교사 수치 경로·자체 관문 | **40/40 PASS**, 40개 서로 다른 시드·4종 상자 각10/10. cap_end0/HOST_ERROR0, invisible_measurements=0·held_world_reads=0, weld off. 원본8254파일 해시 불일치0. [관문 인수](teacher-gate-qualification-r1.json), [원본 재계수](teacher-gate-raw-recount-r1.json.zst). |
| 기록·학생 평가 API | **RECORD_API_READY**. 선택 world의 새 시작 reset/terminal 상태·시계·이력 정지, 자기 RGB 실제 ACT15 step, 기록 JPEG/표적30/30 짝 확인. [영수증](RECORD_API_READY.json), [지원 범위·제한](api-contract.md). |
| warm 처리량 | CPU C16 단독 재측정 **8.181462972 SIM/s**. 첫 공유 시도는 제외. L4 N64/256은 다른 작업 종료를 기다리는 유한 대기열. [프로토콜과 측정 범위](throughput-protocol-draft.md). |

교사·물리는 source `f0db6b1abb842ea65b71c433738210254f300a7c`로 고정했다. IK51 pitch의 NumPy 이식은 원래 SDK와 Mac240/240, 실제 L4 NumPy2.5.2에서480/480 PWM/거부 결과가 일치했다. ray는 GPU 묶음, transform은 GPU에서 읽고 rollout의 C ray/kinematics를 차단한다. upstream sleep의 dof_length 읽기 한 곳을 세계별 원래 값으로 인덱싱하며 설치본 SHA가 다르면 거부한다. Python 교사 상태기계는 세계별 독립 실행한다.

장면은 `walls_floor_contrast_v5_indigo110_s80` + 원래v1 바닥 + `no_mip_v1`, 실제 카메라640×480/10Hz/K,D/FOV/마운트 그대로다. 비배치 배열·스칼라가 완전히 같은7그룹(7/3/12/10/6/1/1)에서 관문40개를 실행했다. [새 장면 승인 대기열](teacher-gate-queue-r1.json)은 rejection_table·소스·plan·reference 해시와 `APPROVED_PINNED`, `REVIEW_SKIPPED_BY_USER (10/15 run-first rule)`을 검사한다. 이전 cap 시드를 먼저 배치했고 첫 라운드에40/40이어서 행동 수정 라운드는 없었다.

성공1개의 전체0–44SIM를 실제2Hz89프레임, 마지막10SIM를10Hz100프레임으로 직접 검토했다([타임라인](success-playback-review.md)). 실제 자기 RGB 둘러보기6회가 있었고 위치 추정 성공은 미검증이다. 완료 실패 시드가 없어 실패 영상은 해당 없음이다. 영상≤8MB와 프레임 띠는 primary `outputs/e2e18-admin/playback/warp3-g0-w000/`에 회수·SHA 확인했다.

기록 API는 통과한 교사를 수정하지 않고 같은 JPEG를 캡처하며 controller SHA와 adapter SHA를 분리한다. 실제 fresh train seed88960의3SIM pilot은 cap_end이며 데이터셋 승인·성공 시연이 아니다. 학생은 실제 ACT15 체크포인트로2step×2world와 부분 chunk reset을 확인했다. **학생 전체 임무 성공률·ACT 학습·기록 본실행은 아직 측정하지 않았다.** reset은 초기화한 고정 모델/seed/task 안의 새 free-body 시작을 지원하며 다른 모델/task는 새 owner가 필요하다. 즉시 경계 보존과 terminal freeze는 검증했으나 다음 물리 궤적의 bitwise 일치는 보장하지 않는다. 실패 probe r1–r4도 원본에 보존한다.

비물리 관련 시험25개 PASS(실제 Mac 기존 환경, 물리/렌더 없음). GitHub CI는 과거 커밋e97464a3에서33/33 PASS([영수증](ci-receipt-e974.json)); 최신 소스 CI는 별도로 확인 중이다. [단계별 누적 통과/거부 표](stage-funnel.json), [운영 기록](operations.json), [참고 문헌·설치본 검증 범위](references.md).

L4 현 boot의8h 상한14:01:09Z·유휴20분·budget-stop을 유지한다. 다른 작업이 main L4를 다시 시작했으며 warp3는 외부 작업/VM을 중지하지 않았다. 별도 L4 생성은 프로젝트 전체 GPU 한도1로 거절됐고 추가 instance/disk가 남지 않았음을 확인했다. [비용·자원 제한 기록](warm-resource-blocker.json). 현재 대기열은13:59:09Z까지만 기다린다. 원격 소스는 canonical git-shared.git을 직접 reference하고 그 저장소를 gc/prune하지 않는다. 기존 COORDINATOR_NOTE.md는 건드리지 않았다.
