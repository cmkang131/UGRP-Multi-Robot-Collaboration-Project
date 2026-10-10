# 본 연구 사전 등록 문서 작업 기록 (2026-10-06)

- 산출물: [PREREG_DRAFT.md](PREREG_DRAFT.md), [검정력 계산](POWER_ANALYSIS.md).
- 문서만 작성했다. **DRAFT 유지 / 병합 금지 / 해시 미동결 / 실행 금지**. 실행기·설정·기존 사전 등록·다른 worktree·PR·프로세스·raw는 변경하지 않는다.
- 작업 브랜치 `codex/main-study-prereg-draft`, 자기 worktree `/Users/changmin/projects/ugrp-wt/prereg-draft`.
- 읽은 저장소 출처: base `da92d91dbf4af193d3aa3559de9efe55653ec5c0`. 이는 작성 출처이며 향후 실험 실행 SHA의 고정 선언이 아니다. primary main을 변경하지 않았다.

## 조사와 설계

`AGENTS.md`를 먼저 읽고 README·current_status·CONTRIBUTING·ROADMAP·10/5 E2E 격차, v4 JSON 8종과 관련 정적 시험, pair 3조건 계약·비용·평가 경로를 확인했다. `git grep -il prereg -- experiments docs`에서 기존 ZC3·9/28 본 연구 초안·b-v6h 기록을 찾아 읽었다. 역사적 결과를 현재 검증으로 재사용하지 않았다.

주 비교는 peer_nl/no_comm, rule은 별도 기준선이다. v4의 3대·8시나리오와 기존 pair 개발 경로의 2대·단일 빔을 구분했다. 144블록·432회는 조건 순서 균형과 가정한 짝 효과 d_z=.25의 검정력 .845848에 근거한 제안이다. 가정·한계·새 seed·실패 분모·HOST_ERROR/ENOSPC·stop-ON·보존 기간과 결정 목록을 문서화했다.

문헌 조사와 확인 수준은 [초안 §11](PREREG_DRAFT.md#11-문헌-조사와-채택한-설계)에 있다. 고전 통신 비교·HRI 시간 지표·RoCo·CoELA·MineCollab·표본 크기 방법을 참고했다. 외부 원문 일부 접근 실패는 미확인으로 표시했고 반복 다운로드하지 않았다. 공개 코드는 README만 읽었고 설치·실행하지 않았다.

## 작업 공간과 권한

1. primary의 깨끗한 main·origin URL·원격 차이와 열린 PR을 읽고 `git fetch origin`을 수행했다. gh가 보여 주는 저장소 URL은 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`이고 기존 origin URL은 그대로 두었다.
2. 요청한 `python3 scripts/agent_worktree.py new prereg-draft --branch codex/main-study-prereg-draft`는 Codex 등록 worktree 17개/상한 8개로 한 번 거절됐다.
3. 다른 worktree를 건드리지 않고 지정된 새 공간을 만들라는 요청을 따르기 위해 같은 관리 스크립트의 `--allow-over-cap --reason`을 사용했다. 새 공간 메타데이터에 사유가 남았고 생성 성공했다. 상한 자체·다른 worktree·보존 자료는 변경하지 않았다. 같은 원인으로 두 번 막힌 상태는 없다.
4. 시뮬레이션·물리·렌더·실제 모델 호출 0회. 잠금 acquire/release, viewer 변경, 프로세스 종료, raw 삭제, Google Drive 작업 0회.

## 검증 기록

코드 모듈 변경은 0개이므로 해당 모듈의 pytest 파일도 없으며 pytest·넓은 회귀 검사는 실행하지 않는다. 문서의 검정력 코드 재계산, v4 표 대조, 내부 파일 링크, 필수 항목, 문서 전용 CI 경로, diff 공백·변경 범위를 검사한 뒤에만 커밋·push한다.

- **PASS:** Markdown 3개, 내부 파일/디렉터리 링크 17개, v4 시나리오 표 8행의 이름·지도·주문/물건 수·DEV seed를 실제 JSON과 대조했다.
- **PASS:** 문서 안 검정력 코드를 실행해 표 5행과 산술 assertion 5개를 확인했다(Python 3.12.13 / SciPy 1.17.1). 귀무효과에서 α=.05도 확인했다. 실제 모델·로봇 결과를 생성한 검사는 아니다.
- **PASS:** 필수 범위·마지막 결정 목록·코드 fence·공백을 검사했고, 기존 `scripts.ci_paths.requires_full_suite`는 이 3개 Markdown을 문서 전용으로 판정했다. pytest 0회(바뀐 모듈 없음).
- **PASS:** staging 후 `git diff --cached --check`와 변경 목록을 확인했다. 새 Markdown 3개만 포함되며 실행 코드·설정·기존 기록 변경은 없다.
- 커밋에는 `Co-Authored-By: Codex <noreply@openai.com>`을 넣는다. 커밋·push 뒤 DRAFT PR과 원격 SHA·문서 전용 CI 상태를 확인하고 사용자에게 보고한다. 병합은 하지 않는다.

## 남은 범위

독립 검토·최종 결정·분석 구현·전체 시나리오 인수·실행 권한·새 최종 등록은 남아 있다. 새 실험 결과가 없어 TensorBoard 변환/서버 실행을 하지 않았다. 초안만으로 어떤 코호트도 실행·승격하지 않는다.
