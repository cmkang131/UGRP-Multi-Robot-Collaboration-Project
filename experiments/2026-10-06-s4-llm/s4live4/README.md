# s4live4 — 빔 LLM 공동 출발 준비 (2026-10-10)

상태: **오프라인 준비 / 실제 모델 0 / 물리 0 / research_result=false**. PR #425는 감독용 draft를 유지한다. 이전 실제 네 조건 r3 운반은 [s4live1 기록](../s4live1/README.md)에 그대로 보존한다(감독이 s4live3으로 지칭한 이전 결과와 합산하지 않는다).

## 변경과 검증 범위

기본 `--pair-mode off`는 기존 r1/r2 claim-only 경로다. `mutual_go_v1`에서만 두 LLM claim을 모은 뒤 각 S3 own executor의 정렬·집기를 시작한다. S3 자동 claim/runtime.step을 호출하지 않는다. 각자 `wait_carry`에 도달하면 자기 grasp epoch+segment에 묶인 go → 받은 peer_go_ref를 지정한 ack_go를 요구한다. 둘 다 확인해야 기존 저수준 동시 GO barrier에 들어가며, 실제 출발 명령에 claim/go/ack call_id를 붙인다. 기존 barrier의 timeout은 이 시점부터 시작한다.

상위 GO/ABORT 고정 안전신호는 네 조건에 공통이며 좌표·접촉·타 로봇 RGB·자유 문자열을 포함하지 않는다. no_comm은 모델 messages=[]만 허용한다. peer_ko는 mesh 자유 한국어, leader_ko는 기존 seed 회전 star(601은 r2), structured는 기존 폐쇄 형식이다. 통신 모델은 GO/ACK/이탈 응답에 해당 채널 메시지를 함께 내야 한다. 채널의 거절/예산/전달 내역을 보존하고, 대화 내용을 파싱해 자동으로 상대 행동을 만들어내지 않는다. 고정 안전신호와 대화 원장을 별도로 판정한다.

집게 이탈은 **해당 로봇의 요청 RGB를 본 LLM의 grip_lost 판단**으로 연결했다. held/unknown도 모델의 시각 판단이며 실제 접촉 성공이 아니다. 기존 신뢰도 미검증 `zone_pair_highpose_grip.relation`의 log-only 결과를 승격하지 않았다. 모델 시각 판독의 민감도/오탐률은 이번에 검증하지 않았다. 운반 중 unknown도 관측 불능으로 두 로봇을 정지한다(물리 실패와 별도 분류).

시간 계약: GO+ACK 합계 20 SIM초(각 응답 단계 10초), 응답을 반영할 때 요청 RGB 나이 <10 SIM초, 고정 신호 전달 0.1 SIM초, 운반 중 자기 RGB 모델 관측 요청 간격 2 SIM초. 마지막 승인 시각부터 10 SIM초 안에 새 held 판독이 없으면 두 로봇 abort. 따라서 가장 오래된 허용 영상은 승인 나이까지 합쳐 <20 SIM초이며 연속 영상 검출기가 아니다. 실제 HTTP wall 지연은 기존 scheduler의 SIM 비용과 별개다. 단일 call당 provider timeout/실패는 기존 원장대로 보존한다.

잘못된 JSON·출처 누락·no_comm 메시지·잘못된 epoch·과거 요청·못 본 GO ACK·중복 GO는 출발을 허가하지 않는다. 기한 만료/모델 오류/이탈 때 두 실행기의 arm queue·schedule·port queue를 지우고 같은 tick에 먼저 모은 상대 명령까지 hold로 바꾼다. 누락/잘못된 통신 메시지를 가진 답은 전체 형식 오류로 남고, 갱신이 없으면 기한 만료로 정지한다. S3 실제 guard는 유지하며 dev_light의 위치 추정 관련 보수적 정지는 기존 규칙대로 기록한다.

## 선행 S3 고정점

이번에 `git fetch origin`을 완료했다. 읽은 #416 HEAD는 `5e78ab3c049f37b6d9a7aa6b5e688e613a5cef8a`이며 s3fix13 결과/채택 SHA로 간주하지 않았다. S4 시작 HEAD `ec1145d79745b4121c7d8ea1b6ac6d0976615e72` 위에서 준비했다. 아직 merge/물리/실제 모델 호출을 하지 않았다.

`release.json`은 `waiting_for_s3fix13`, S3 SHA·설정·번들 ID는 null이다. `--execute`와 batch `--submit` 모두 이 상태에서 물리/모델을 만들기 전에 거부한다. 확정 후 할 작업:

1. 감독이 지정한 S3 SHA를 이 worktree에 merge(충돌은 S3 정의 우선). 알려진 실제 정렬 수정의 설정을 `settled_servo`에 그대로 고정하고 해당 S3 실행 bundle의 전체 source_sha256을 `s3_file_sha256`에 보존한다. 후보 어댑터는 `zone_s3_settled_servo.Options/attach_endpoint`; 최종 S3가 다른 인터페이스이면 그 차이만 통합 후 관련 시험을 다시 한다.
2. main/열린 PR의 최댓값을 확인해 새 실행 bundle/workflow 번호를 예약하고 release.json에 등록한다. 현재 v157 과거 증거/정의를 새 실행으로 재사용하지 않는다. release에 S3 SHA와 새 버전을 적고 status=ready로 고정, 관련 시험 후 commit/push한 **S4_SHA 하나**로 아래 네 행을 한 묶음 제출한다. 표의 `<S4_SHA>`만 같은 실제 HEAD로 치환한다.
3. 기존 Mac proxy/유한 SSH loopback relay를 검사하고 공개 identity receipt를 `/home/ubuntu/ugrp-sim/s4live4-relay.json`에 준비한다. 인증 비밀은 서버 파일/명령/로그/커밋에 저장하지 않는다. 기존 인증이 없거나 전달 방식이 불명확하면 제출하지 않는다. 이번에는 relay·SSH·서버 작업도 시작하지 않았다.

현재 작업은 준비만 승인되었으며 위 단계는 **후속 실행 라운드용**이다. 실제로 검증된 S3 성공을 이 준비 코드의 물리 성공으로 승계하지 않는다.

## 고정 실행 묶음

`dev_s1lite`, seed **601 하나 × 네 조건 = 4개**, 각90 SIM초(≤120), dev_light, heading 기본 on(빔 공동 운반만 옆걸음), weld off. 기존 합성 정렬 입구를 재사용하며 탐색/완주 연구가 아니다. 모델/이미지/기본 프롬프트/물리/seed/응답 유효기간/호출예산은 조건 공통: 로봇당 최대30·총90호출, retry0, 총1,100,000토큰 상한. 실제 사용량은 별도 보존한다. 모델 요청·응답 원문, 이미지 원본과 sha256, 원장, 응답 wall 시간·토큰·실패·dispatch·공동 출발/정지 명령 인과를 보존한다. raw 회수 위치는 기본 checkout outputs/oracle-runs/<name>이며 서버 raw와 전파일 해시를 대조한다.

| 이름 | 조건 | seed | 서버 명령 (`oracle_run.sh <worktree> <name> --` 뒤) |
|---|---|---:|---|
| `s4live4-no_comm-s601-pair-go` | no_comm | 601 | `.venv-sim/bin/python -m scripts.run_s4_live --expected-source-sha <S4_SHA> --output outputs/s4live4-no_comm-s601-pair-go/raw --condition no_comm --cap-s 90 --relay-receipt /home/ubuntu/ugrp-sim/s4live4-relay.json --pair-mode mutual_go_v1 --pair-release experiments/2026-10-06-s4-llm/s4live4/release.json --execute` |
| `s4live4-peer_ko-s601-pair-go` | peer_ko | 601 | `.venv-sim/bin/python -m scripts.run_s4_live --expected-source-sha <S4_SHA> --output outputs/s4live4-peer_ko-s601-pair-go/raw --condition peer_ko --cap-s 90 --relay-receipt /home/ubuntu/ugrp-sim/s4live4-relay.json --pair-mode mutual_go_v1 --pair-release experiments/2026-10-06-s4-llm/s4live4/release.json --execute` |
| `s4live4-leader_ko-s601-pair-go` | leader_ko | 601 | `.venv-sim/bin/python -m scripts.run_s4_live --expected-source-sha <S4_SHA> --output outputs/s4live4-leader_ko-s601-pair-go/raw --condition leader_ko --cap-s 90 --relay-receipt /home/ubuntu/ugrp-sim/s4live4-relay.json --pair-mode mutual_go_v1 --pair-release experiments/2026-10-06-s4-llm/s4live4/release.json --execute` |
| `s4live4-structured-s601-pair-go` | structured | 601 | `.venv-sim/bin/python -m scripts.run_s4_live --expected-source-sha <S4_SHA> --output outputs/s4live4-structured-s601-pair-go/raw --condition structured --cap-s 90 --relay-receipt /home/ubuntu/ugrp-sim/s4live4-relay.json --pair-mode mutual_go_v1 --pair-release experiments/2026-10-06-s4-llm/s4live4/release.json --execute` |

읽기 전용 계획: `python -m scripts.submit_s4_pair_batch`.
후속 일괄 제출: `python -m scripts.submit_s4_pair_batch --oracle-runner "$S/oracle_run.sh" --output /Users/changmin/projects/ugrp/outputs/s4live4-admission.json --submit`.

소스 archive를 먼저 한 번 끝까지 전송하고 네 제출을 동시에 시작한다. 자체 최대4개(허용6 이내). runner exit3만 같은 SHA/argv로30초 대기 후 재제출하며120회 이내 유한 대기한다. 일반 실행 실패는 자동 재실행하지 않는다. 이미 있는 raw 실행 디렉터리를 덮어쓰지 않는다. memory 대기/host 종료는 정책 실패와 분리한다. 소스 archive가 이미 있거나 전송 실패한 경우 자동 삭제하지 않고 사전 상태를 확인한다. 실행 중 계획·seed·설정 변경 없이 네 raw를 회수한 뒤 한꺼번에 판정한다. 이번 준비 라운드의 스모크도 0회다.

## 판정 사전등록

통과는 실제 모델 call_id → 두 claim → 각 S3 명령 → GO/ACK → 두 로봇 출발 명령 연결로만 판정한다. 각 단계 도달 수와 실패를 전부 보고한다. 빔 정렬 미완은 `alignment_not_reached`, 모델 유효 응답 부재는 `pair_go_timeout`, 자기 영상 unknown/lease 만료는 관측/응답 불능, 자기 영상 이탈 판단은 별도 보고하며 사후 평가와 대조한다. simulator pose/contact/success는 eval_only에만 둔다. 모델 시각 검출 정확도는 정답을 제어에 주입하지 않고 나중에 평가한다. raw의 no_comm 자유 메시지0, peer mesh/leader star/structured 형식 준수, 동일 공통 경로·한도도 확인한다. 연구 결과/배송/E2E 성공은 주장하지 않는다. ENOSPC는 HOST_ERROR다.

## 표준 방법·선행연구 (2026-10-10 확인)

- [Gray & Lamport, Consensus on Transaction Commit](https://www.microsoft.com/en-us/research/publication/consensus-on-transaction-commit/): 참여자별 준비와 최종 결정 분리, 실패 시 commit 금지라는 표준 방식을 참고했다. 본 구현은 단일 호스트의 유한 handshake이며 Paxos/분산 내결함 합의 구현이 아니다.
- [Colledanchise & Natale, Improving the Parallel Execution of Behavior Trees, IROS 2018](https://arxiv.org/abs/1809.04898): 병렬 행동의 진행/자원 동기화 관점. 기존 `PairCarrySync`와 S3 저수준 GO barrier를 유지하고 LLM 준비 단계만 그 앞에 추가했다. 논문의 수학적 보장을 이번 구현에 승계하지 않는다.
- [RoCo, ICRA 2024](https://arxiv.org/abs/2307.04738), [저자 공개 코드](https://github.com/MandiZhao/robot-collab): 로봇별 LLM 대화와 계획 실행의 분리를 참고했다. 환경 collision feedback/waypoint 입력 등은 우리 관측 경계와 달라 가져오지 않았고 API-key 파일 예시도 따르지 않았다.
- [SMART-LLM](https://arxiv.org/abs/2309.10062): task decomposition/coalition/task allocation을 분리한다. 이번 고정 역할 DEV claim은 일반적인 coalition 성능 검증이 아니다.
- [Scalable Multi-Robot Collaboration with LLMs, ICRA 2024](https://arxiv.org/abs/2309.15943): 통신 구조별 성공·토큰 비용 비교를 참고해 채널 외 실행기를 공통화하고 호출·토큰을 함께 기록한다. 해당 논문의 hybrid 성능을 우리 네 조건에 외삽하지 않는다.
- [DynaHMRC, 2026-06 preprint](https://arxiv.org/abs/2606.14882): 최신 decentralized/role-aware 동적 협업 관련 검색 결과로 포함. 제목·arXiv 초록 수준만 확인했으며 상세 구현/코드/재현은 미확인, 이 후보의 근거로 채택하지 않았다.

기존 공개 코드를 설치하거나 타 저장소의 물리 실험을 실행하지 않았다. 새 임계값은 개발용 시간 계약이며 물리 검증값이 아니다.

## 오프라인 검증 결과

관련3파일 `test_pair_llm_s4_pair.py`, `test_pair_llm_s4_host.py`, `test_s4_live_stage.py`: **52 passed / 0 failed**. 네 조건 각각 stub 출발 허가1, 이탈 보고1; 허가 전 움직임0·이탈 반영 이후 움직임0. 가짜 actuator 이동 명령은 no_comm74 / peer96 / leader96 / structured120이며, 메시지 처리비용으로 달라지는 논리 시간에 따른 합성 수치다. 효율 비교나 실제 운반량이 아니다.

기본 off 및 기존 S4 회귀, 늦은/과거/다른 epoch/못 본 ACK 거절, 한쪽 GO만 있을 때 timeout, 같은 tick 후행 로봇 실패 때 앞서 수집한 명령 제거, 원격 memory exit3 동일 argv 재제출과 일반 오류 재시도 없음, pending release 실행 차단을 확인했다. 표준 CLI와 batch 계획 읽기 전용 출력도 확인했다. 처음 작성한 시험의 pytest 예약 인자명과 structured 메시지 fixture 형식을 고쳤고, GO 신호가 도착하기 전 중복 질의되던 문제 및 응답/handshake 기한 구분을 한 묶음으로 수정했다. 이 수정 과정에도 실제 실행0이다.

[전체 수치·소스 파일 SHA256·raw204파일 해시](offline-validation.json). raw `/Users/changmin/projects/ugrp/outputs/s4live4-offline`, 별도 fixture 요청·응답·자기 이미지 해시 보존. fixture 원장의 호출/usage는 합성값이며 실제 모델 호출 분모는0이다. 새 물리 영상은 없다. S3 최종 SHA와 설정/새 번들 번호 확정, 그 위의 통합시험·원격 제출은 아직 남아 있다.
