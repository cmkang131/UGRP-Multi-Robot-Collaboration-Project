# search16 — 압축 결과 reader 수정과 새 속도·교사 관문 대기열

2026-10-15 · PR #484. 기준 교사 소스 `c0a8875b1ff71fbf4f92f7f7c0b7f8d140ec8147`,
reader 구현 커밋 `fcd13939`.
실행용 최종 SHA·승인 시각·파일별 SHA-256·명령은
`outputs/e2e18-admin/vm3-queue/20261015-grasp-search-<최종 SHA8>-gate.json`에 고정한다.
[기계 판독 요약](search16-summary.json), [교사 실행 파일 해시](search16-execution-sha256.json).

## 수정·검증

`scripts/run_grasp_act_batch.py`의 하나의 reader를 결과 집계·진행 감시·repeated_cause·
종료 정리에 공통 사용한다. `result.json`과 `result.json.zst` 모두 읽고,
둘이 함께 있으면 JSON 의미가 아닌 해제 바이트 전체가 같아야 한다.
압축 결과는 manifest의 저장 SHA-256·`decoded_sha256` 모두 대조하며,
압축 manifest도 `manifest-compression.json`의 두 해시를 확인한다.
이 두 해시와 원본 result 경로를 배치 행에 보존한다. 불일치는 HOST_ERROR다.
교사가 manifest를 마지막에 쓰므로 자식 종료 전에는 미발행 증명을 기다리고,
종료 뒤에는 압축 결과 증명이 없으면 HOST_ERROR로 기록한다.

- `test_grasp_act_batch.py`, `test_grasp_act_resume.py`: **22 passed**, 물리·렌더·네트워크 없음.
  실제 zstd fixture로 complete/EXIT0·핸드오프 분모 유지, 두 독립 압축 실패의 반복 원인 정지,
  압축/해제 해시 오류·두 표현 불일치·압축 manifest·종료 전후 증명 경계를 확인했다.
- 회수된 c0a8875b 원본을 로컬에서 새 reader로 다시 읽었다:
  정상 **6/6**, 신규 **6/6**, 옛 실패+hard **3/7**(옛 실패3/6·hard0/1 유지).
  전체 **19 complete/EXIT0, HOST_ERROR 0, 중단 0**.
  압축 ep6/7/11의 두 해시를 확인해 기존 3/4 오집계의 분모를 7로 복원했다.
- 입력 감사0/0·342프레임 검토는 **운영 워커의 기존 기록**이다. 이번 작업에서 새 영상은 보지 않았다.
  원본 요약 `outputs/e2e18-admin/gcp-reports/search15-diagnostic-c0a8875b.json`과
  로컬 재집계 `search16-local-reader-audit.json`의 경로·해시를 요약 JSON에 기록했다.

교사·액추에이터·지도·장면·물리·카메라·학습 코드는 c0a8875b와 바이트 동일하다.
`harness/`, `sim/`, `scripts/`, `configs/`, `maps/`의 Git tree를 전수 비교하여
reader/감독 파일 하나만 바뀜을 확인하고, 나머지 파일 각각의 SHA-256을 위 해시 파일에 보존했다.
최종 `git diff c0a8875b..HEAD --stat`·변경 파일별 SHA-256은 대기열에도 기록한다.
다른 워커의 미추적 감사 문서는 수정·커밋하지 않았다.

## 운영 워커 인수 조건

사용자 이번 지시가 **새 SHA의 speed16·gate40 두 단계 승인**이다.
승인 근거는 `c0a8875b diagnostic normal 6/6 + novel 6/6; diff limited to result reader`다.
운영 워커만 원격 재고 확인·제출·회수한다. 이번 작업의 실행호스트 접속·새 물리·렌더·모델 호출은 **0회**다.

1. 계획/프로필/3옵션·깨끗한 실행 snapshot·최종 SHA와 해시를 확인한다.
   `visible_only`, 자기 명령 pose, `align_relook_v1`, `search_body_scan_v2`,
   `progress_view_recovery_v3`, coordination off와 search15의 세 옵션 ON을 그대로 고정한다.
   그 외 goal-set·nominal-handoff·progress·visible-handoff 옵션도 search15와 같다.
   학습 RGB off·weld off·repeated_cause_v1, GCP gcp1/n4-highcpu-64·기존 비용/시간/디스크/부하 가드를 유지한다.
2. [speed16 계획](teacher-search16-speed16-plan.json): 신규 **315600–315615**, 16동시×30 SIM초.
   **16/16 완료**, 해시·종료 정리 확인, wall/SIM 중앙 **≤3.5**, 우회 없음일 때만 속도 통과다.
3. [gate40 계획](teacher-search16-gate40-plan.json): 신규 **315700–315739**, 동시16·최대60 SIM초.
   같은 SHA/프로필/머신의 위 속도 결과를 명시적으로 연결한 뒤에만 운영자가 이 승인에 따라 제출한다.
   **40회 중 ≥38 성공**, 핸드오프는 실패, HOST_ERROR·중단은 별도 집계한다.
   HOST_ERROR로 완료 분모가 40 미만이면 관문 완료/통과로 표시하지 않는다.

두 seed 집합은 서로 겹치지 않고, 동결 전 로컬 가용 계획/대기열 **971파일**과
기존 experiments/configs/scripts/tests의 정확한 정수 검색에서 사용 이력이 없었다.
**원격 전 재고·타 작업 예약은 미확인**이다. 운영자가 옛87000–87039·옛 실패6/hard·
지금까지의 모든 진단/학습/다른 작업 및 대기 예약과 대조·예약한 증거를 남기기 전에는 제출하지 않는다.
충돌하면 실행하지 말고 계획/해시를 다시 동결하며, 임의 seed 치환은 금지한다.
speed16 결과와 gate40 분모를 합치지 않는다.

시작 분포는 search15 신규 진단과 동일한 visible-start/static nominal-goal 필터다.
초기 static 차단 시작은 speed16 **0/16**, gate40 **1/40**이며, gate40의 해당 제안은
같은 seed 안에서 다시 생성됐다(제외 제안1개). 넓은 시작 분포 전체의 관문으로 일반화하지 않는다.
학습 카메라 기록을 켜거나 다음 코호트·학습으로 자동 승격하지 않는다.
`gate_promotion_authorized_if_all_conditions_pass=false`, 자동 제출/승격 없음.
이전 c0a8875b 진단 대기열은 완료로 닫고 모든 재실행 플래그를 끈다.

## 참고 자료

2026-10-15 원문 확인:
[Zstandard 공식 CLI](https://github.com/facebook/zstd/blob/dev/programs/README.md)의
표준 스트림 해제 방식과 [Python hashlib 공식 문서](https://docs.python.org/3/library/hashlib.html)의
SHA-256 바이트 digest를 사용했다. 새 압축 라이브러리는 추가하지 않는다.
원장 형식은 기존 `scripts/run_grasp_act_teacher.py::compress_logs`를 그대로 따른다.
