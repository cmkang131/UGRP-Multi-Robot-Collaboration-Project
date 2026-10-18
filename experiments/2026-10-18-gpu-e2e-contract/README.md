# GPU(MJWarp) E2E 실험 계약 v1 — 사용자 결정 정렬 (2026-10-18)

**상태: 제안(검증 전). 코드/설정 변경 없음. 이 문서는 다음 구현·관문의 기준 계약이다.**

계기: Codex 독립 리뷰(2026-10-18, 6/10)가 현재 `e2ewarp`(PR #570, `codex/e2ewarp` 718777118)가 최신 사용자 결정과 **계약 불일치**라고 지적했다. 이 문서는 최신 결정을 코드 기준으로 옮긴다.

## 1. 최신 사용자 결정 (우선)
1. **모든 시뮬레이션 흐름은 GPU/MJWarp**(2026-10-16 "모두 MJWarp로", 2026-10-18 "MuJoCo 안 쓰기로 / 모두 GPU로"). CPU MuJoCo 결과는 재생·비교용으로만 보존하고 새 결과와 합산하지 않는다.
2. **정적 지도 미사용·자기중심 기억**(2026-10-17 사용자: "정적 지도는 안 쓸 거야. 차라리 자기 위치를 항상 0,0으로 …"). 위치 추정·주행·판단 LLM 입력 어디에도 미리 만든 정적 지도(좌표계·벽·문·구역 배치)를 쓰지 않는다. 자기 위치 0,0, 주변 기억(문·구역 표시·화물·파트너·벽 모서리의 자기 기준 상대 위치)을 이동량만큼 반대로 옮기고, 다시 보이면 관측으로 고친다. **목적지는 보고 찾기**(바닥 표시·색). GT는 평가 칸만.
3. **미션은 두 로봇의 공동 운반**: 서쪽 픽업존 → divider 문 통과 → 동쪽 zone B 운반. heavy crate 제외, 공동 운반은 long_beam(2로봇). **3로봇 전제는 이 미션과 불일치**.
4. **근거리 실행은 ACT 학생**: 입력은 자기 RGB 이력, 자기 명령 이력, 스킬·물건 종류·자리 번호표. 정답 교사는 시연만, 학생 실행에 교사·정답 보정 없음. weld OFF.
5. **대화 언어: all English**(2026-10-11 `current_stack: dialogue_language peer_en`). 4조건 = `no_comm / peer_en / leader_en / structured`. 리더 교대(seed % 2), 허브-스포크.
6. **대화·사고 시간은 SIM 비용**: 모든 조건 동일 규칙. 통신 채널은 조건이 정한 것만, 짝 상태 채널은 고정 enum으로 4조건 동일.
7. **검증 관문**: 중간 결과 독립 verifier 1, 최종 2. 원본·SHA·funnel·거부표·no-pooling·정직 라벨.

## 2. GPU E2E 계약 v1 (제안)
### 2.1 실행 경계
- 물리·렌더: MJWarp `put_model/put_data → CUDA graph → step`, `noslip0`, **CPU `mj_step` 금지**. 장면: 최종 환경(벽 0.40m, AprilTag 0개) 기준의 2로봇 장면.
- 로봇 입력: **자기 RGB(robot_cam) 1장/이력**, 자기 발행 명령·시각, 시나리오에서 만든 주문서, **자기중심 기억(위치 0,0 기준 상대 목록)**, 해당 조건의 수신 메시지, 짝 상태 고정 enum. **정적 지도·GT·상대 로봇 raw·top 카메라 금지**.
- 행동: LLM이 무엇·어디로·순서·역할 판단 → 코드가 경로·주행·운반 실행 → ACT가 근거리 접근·정렬·집기·놓기(0.8s 청크). 완료는 자기 RGB 확인 + 완료 출력 함께.
- 평가: 별도 evaluator가 raw 디렉터리에서 실제 운반·도착(GT) 판정. GT/접촉/성공은 eval-only.

### 2.2 조건·시행·지표
- 조건 4개(2.1 참조) × 시나리오(서쪽 pickup → divider door → zone B) × seed. 1시드 1회 완주 파일럿 후 4조건 확장.
- 주 결과: **처음→끝 실제 운반 성공률**(n/N, 분모 유지). 보조: SIM 시간, 명령 수, 모델 호출·토큰·캐시, 한국어/영어 준수, 발화 사실성, 실패 사유 분포.
- no-pooling: 조건 간·호스트 간·CPU/MJWarp 간 합산 금지. 실패·HOST_ERROR·cap_end 구분.

## 3. 현재 e2ewarp와의 격차 (코드 근거)
| 항목 | 계약 v1 | 현재 e2ewarp | 조치 |
|---|---|---|---|
| 로봇 수 | 2 | 3 (`r1/r2/r3`, design.md·scenario orders) | 2로봇 시나리오·runtime lane 재설계 |
| 정적 지도 | **금지** | `static_map_registration`·`own_and_static_map=true` **필수** (`harness/e2e_warp_components.py` require_components, components manifest) | 자기중심 기억 기반 등록·주행으로 교체, static map gate 제거 |
| 위치 추정 | 자기중심(0,0)+기억 | static map 등록·map correction 전제 | nav owner 부품 신규(기억 기반) |
| 미션 | 서쪽→문→동쪽 B 운반 | smoke(운반 없음)·3로봇 주문 inspect | 2로봇 운반 미션·evaluator 구현 |
| 대화 언어 | English 4조건 | peer_en 등 조건 골격 있음 | leader_en·structured 프롬프트/채널 검증 |
| 물리 | MJWarp noslip0 | 일치 | 유지 |
| ACT | 선택된 act16w v3 10k | artifact 미충족 | 실패원인 연결 후보로 소규모 관문(별도 결정) |

## 4. 최소 변경 순서 (Codex 권고 반영)
1. **계약 문서·스키마 고정**(이 문서 + `components` 계약에서 static map 항목 제거, 2로봇 스키마).
2. **navigation owner(자기중심 기억 기반)**: 서쪽 시작→문 통과→zone B 도착을 MJWarp에서 실제 명령으로 주행·자기 RGB 확인. wheel hold 제거.
3. loaded FK·release·evaluator: MJWarp 물리 관문 순차 통과.
4. ACT: 실패 원인(물리 grasp 기하/데이터 규모/행동형식)에 연결된 후보 1개로 소규모 물리 관문 → peer_en 1조건·1시드 처음→끝 → 성공 시 4조건 확장.
5. 각 단계 기본 off·원본/SHA/funnel·실패 기록·독립 검증.

## 5. 폐기·격리
- CPU MuJoCo zone-study 경로·`prereg_v3`·GCP CPU VM 실행: **ABANDONED_NONCOMPLIANT**(결과 폐기·비합산, 파일 제거).
- e2ewarp 기존 R4/4조건 스모크: **배관·키프레임 스모크로만 보존**(연구 결과 아님, static map 계약 위반 상태). 새 계약 실행과 합산 금지.
- PR #595: 기록 전용 close(대형·CONFLICTING). 증거는 브랜치 `dsh/e2ewarp-components-v1` 보존.

## 6. 미결정(사용자)
1. 계약 v1 승인 여부(2로봇·정적 지도 없음·English 4조건·MJWarp).
2. ACT 경로: 실패원인 연결 새 후보 / act16w 10k 재현 / 통합 마감(비권장).
3. 파일럿 예산: peer_en 1조건·1시드 완주 1회의 모델 호출 상한·기간.
