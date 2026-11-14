# UGRP 작업 계획 (DSH 조정자 유지)

최종 갱신: 2026-10-18 20:20 KST. 이 파일이 **단일 계획표**다. 상세 원본·수치는 `outputs/e2e18-admin/ops-alert.md`(로컬), 실험별 README, PR을 따른다.

## 0. 이번 세션 목표
- 미션: 두 로봇이 서쪽 픽업존 → divider 문 → 동쪽 목적 구역으로 짐(빔/박스) 운반. 근거리 파지·놓기는 ACT.
- 입력 경계: 정적 지도·좌표계·top 카메라·정답 금지. 자기 RGB·자기 발행 명령·자기중심 기억만. GT는 평가 칸만.
- 검증 관문(2026-10-18 사용자 결정): 병합·사용자 보고 전 독립 verifier(원본 재계수·조건 감사). 최종 관문 2, 중간 1.

## 1. 작업 스레드 상태 (2026-10-18 14:45 KST)
| 스레드 | 상태 | 다음 |
|---|---|---|
| act18 (PR #575, merged) | R8/R100 100k fp32 **TRAIN4 0/4 NOT_READY**(Release 재현용). 튜닝 트랙: B1 done 양성배치(h=0 학습 실패) → B2 표준축 20k(실패) → B3 h=0 라벨(실패) → **B4 done cmd-history GRU 헤드(4/4 issued_done 성공, 물리 lift 0/4)** → **co-r2 70k TRAIN4 0/4**(issued_done 4/4, lift 1/4, release 0/4). gcp2 TERMINATED·CLEAN. | 데이터 규모/새 녹화 / closed-loop 제어 / 평가계약(물리 성공 정의) — **사용자 결정** |
| beamact5 (PR #585 merged, #588 draft) | r4c 검색축 수정(10 회귀 해결) → r10–r13 **align breakaway**(align 정체=40ms pulse static friction) → case27 단독/batch 통과 일부. **두 39-gate attempt 모두 37/40 FAIL**(27 flaky 1/3·37 expected). gcp6 TERMINATED·CLEAN | 27 안정화(align 이전 상류) 또는 margin-aware 재승인 — **사용자 결정** |
| visgoal (PR #582, #592 draft) | 후보 B/C 종료. **Stage A FAIL**(GT 문통과 1/16, gap 주장 9/9 허위) · **Stage B FAIL**(적재 16/16 유지했으나 문통과 0/16, 화물이 하단 화면 가림) · fix v1 FAIL(문 0) · **fix2 FAIL(미션)**: GT 1/16·declared 1·GT-inside 0(margin −0.0162m), v2 gap 규칙 너무 엄격(confirmed 0)·paint v2 true zone 133 수용. CLEAN·gcp3 TERMINATED | 문 gap v3·선언 전 zone 경계 확인·loaded stageB-fix mask 반사실 — **사용자 결정** |
| egonav (PR #587, merged) | 완료·CLEAN | 없음 |
| crossroom Stage B+ | Stage B(적재) baseline FAIL 기록. 오클루전 대응 loaded 후보 설계 필요 | fix2 결과 후 `crossroom-stageB-fix` 설계 |

## 2. 사용자 결정 (날짜)
- 2026-10-17: 정적 지도 미사용, 자기 위치 0,0, 대략 기억.
- 2026-10-17: bf16 새 ACT 학습 기본(fp32와 합산 금지, 프로브 1.10배).
- 2026-10-18: 검증 관문(병합·보고 전 독립 검증).
- 2026-10-18: **벽 너머(반대편) 짐 운반이 실제 과제** → crossroom 관문 필요.
- 2026-10-18: 서브에이전트 수 감축(작업자 4명 유지).
- 2026-10-18: act18은 비교 실험 최종 마감 후 **튜닝/연구표준 트랙만** 진행.
- 실행 시간 상한 없음, 유휴 20분·프로젝트별 예산 정지 유지.

## 3. act18 트랙 결과 (2026-10-18 야간)
**원인(시각+수치)**: R8/R100 TRAIN4 4/4가 t≈9.7–12.4s에 base·arm 전체 정지, 목표 0.20m 간격, 화면 파란 바닥 — 상자 하단 이탈. 교사 시연은 같은 시점부터 close→lift 5–8s 지속(post-visibility 예시 존재).

**연구표준 감사(`RECIPE_AUDIT.md`)**: 버그급 1 = **done 감독 학습 불가**(72,572행 중 양성 200, prior 0.28%, batch8 양성 포함 확률 2.19%; balanced BCE로 미해결). batch 8은 표준(act-plus-plus)임 확인. 편차: action 벡터 구조·base 이동평균 부재·10Hz/chunk100=10s·best-val 없음·co-training 없음·평가가 issued_done 요구.

**실험 결과**
- B1(done 양성배치 50%): done이 **미래 horizon(h≈99)에서만** 학습(0.999), 현재 h=0은 ~1e-4 → 실행 신호 없음.
- B2(표준축: chunk20·base smooth·best-val·20k from scratch): TRAIN4 0/4, 병리 동일.
- B3(h=0 완료표적만·B3a/B3b): done 확률 max 0.0009/0.0018, 미발화.
- **B4(done 전용 cmd-history GRU 헤드, AUC .9967·발화 오차 median .2s)**: **issued_done 4/4 성공**(cap_end 해소), but 물리 lift 0/4 → 성공 정의(물리+done) 0/4.
- **Phase C co-training(act16w 40+act17 v7 240+근거리, 조건토큰, 100k 계획)**: gcp2 `ugrp-idle-guard`가 학습 중 guest shutdown → co-r1 HOST_ERROR(step 51.6k), guard 수리 후 **co-r2 resume(40k+30k=70k, best-val 68k val .0947)** → **TRAIN4 0/4**, issued_done 4/4·cap_end 0/4, 물리 lift 1/4·release 0/4.
- closed-loop 진단: 초기 접근 일치, **grasp 10–15s hold 전환과 release 물러나기**에서 분기(모델 base 이동 지속·gripper closed .24, teacher .98). 행동형식·클램프는 비주원인(open-loop MAE 작음).

**다음 카드(사용자 결정 필요)**: (1) 데이터 규모 확대(새 녹화 승인) (2) closed-loop 제어 후보 (3) 평가계약(물리 성공 정의) — `EVAL_CONTRACT_CANDIDATES.md` 완성·실행 금지.

## 4. beamact5 트랙 결과 (2026-10-18 야간)
- r4 ablation: 검색 revert는 10 회귀, r4c(조건부 far→close→mid circles)로 10 해결·6/20 유지.
- case27: refresh/commit-plan 실패 → **align 원인 확정**(40ms pulse가 static friction 못 깨 pose 고정) → r13 modal breakaway(동일축 visible error 3틱 불변 시 full-period pulse)로 단독·batch 일부 PASS.
- **39-gate attempt1·attempt2 모두 37/40 FAIL**(27 align_no_progress 26.0/26.3s + 37 expected). 27 flake 1-world 반복 FAIL·FAIL·PASS(1/3) — 성공/실패가 align 이전 상류에서 갈림.
- attempt1/2·flake 전부 공개(선택·pooling 없음, attempt2만으로 38/40 주장 금지). PR #588 draft(head 376c006f1)·margin-aware 재승인 제안서(실행 금지).
- **다음(사용자 결정)**: 27 안정화(align 이전 선택 단계) 또는 승인 starts(15/27/37) margin-aware 재승인 deviation.

## 5. visgoal / crossroom 트랙 결과 (2026-10-18 야간)
- 후보 C FAIL(선언 회귀·서쪽 악화) → **Stage A(무적재, 16 west starts, 180 SIM)**: GT door_crossed **1/16**, gap_cross 주장 9/16 전부 허위(e02만 GT 통과 — lateral -0.1634m·문틀 겹침 -0.1084m·margin -0.028m), found 4/16(3건 beam blue end-band 오탐), cap_end 13·STOPPED_NO_ARRIVAL 2. 독립 검증자 재계수 일치·정정 3건 반영.
- **Stage B(적재 red box)**: funnel 16→…→cargo_held_at_start 16→**GT door 0/16**, cap_end 16/16. 화물 유지 **28,816/28,816틱**(무 weld·낙하 0). 원인: 들고 있는 box가 자기 RGB 하단 밴드(y400–463, 25k px)를 가려 근접 바닥·장애물 검출 0 → 허위 gap 16/16. 독립 검증자 재계수 일치(라벨/범위 정정 3건).
- **fix v1 FAIL**: 문 통과 0(GT door 0), gap claim 6 전부 허위, paint filter는 클래스 분리는 정확(beam band ≤.099 vs zone .205–1.236)했으나 문 못 넘어 zone 미관측.
- **fix v2 결과: FAIL(미션)** — funnel 16→…→GT door 1→post-cross found 1→declared 1→**GT-inside 0**. e02: cross 58.0s·decl 79.9s·lateral −0.1628·min jamb −0.1078·**margin −0.0162m(1.6cm 밖)**. v2 gap 규칙이 실제 문을 너무 엄격히 거부(606 reject·confirmed 0·align 미실행), paint v2는 true zone 133 수용/beam 548 거부, approach escape 10회. wall 8732.72=3.0322. v1이 잃었던 GT 통과·진짜 found·선언 회복.
- 기록: `experiments/2026-10-18-crossroom-carry/{stageA,stageB,stageA-fix2}`·PR #592. **다음(사용자 결정)**: 문 gap v3(전방 foot+side loss+jamb 폭), 선언 전 zone 경계 own-RGB 확인, loaded `crossroom-stageB-fix`(mask on/off 반사실 2-arm).

## 6. 인프라·비용 (2026-10-18 14:45)
- VM: gcp2·gcp3·gcp6 **전부 TERMINATED**; gcp4·gcp5 off. (원본 디스크 보존)
- DeepSeek 잔액 **≈USD 23.7**(충전 반영 후). GCP 예산 정지 장치 유지.
- 노트북 덮개 슬립 가드: 작업 종료 후 **원복 완료**(SleepDisabled=0, launchd·heartbeat 제거). scoped pmset sudoers(`/etc/sudoers.d/ugrp-pmset`)만 남음 — 제거: `sudo rm /etc/sudoers.d/ugrp-pmset`.
- PR: 오늘 병합 #533·#537·#545·#563·#575·#585·#586·#587·#589·#590·#591. 열린 draft #588(beamact5)·#582/#592(visgoal). #570·#566·#564 등 과거 draft 유지.

## 7. 다음 이벤트
- 사용자 결정 대기: (1) act18 데이터/closed-loop/평가계약 (2) beamact5 27 안정화 vs margin-aware 재승인 (3) visgoal 문 gap v3·선언 전 경계 확인·loaded stageB-fix.
- 전 스레드 CLEAN, 실행 중 작업 없음. 신규 실험은 사용자 결정 후 착수.
- 핸드오프 상세 수치·원본 SHA: `outputs/e2e18-admin/ops-alert.md` 및 각 실험 README.

## 8. GPU(MJWarp) 전환과 Codex 독립 리뷰 (2026-10-18 20:20)

### 8.1 사용자 정정과 폐기
- 사용자: "내가 MuJoCo 안 쓰기로 했었잖 / 모두 GPU로 하기로 했었잖" (2026-10-18). **모든 연구 실행은 GPU/MJWarp만** 사용한다 ([AGENTS.md](../AGENTS.md) 정적 지도·결과 규칙, 2026-10-16 "모두 MJWarp로").
- **폐기(ABANDONED_NONCOMPLIANT)**: CPU MuJoCo zone-study 통합 경로(`experiments/2026-09-26-zone-study-integration`의 CPU 실행·`prereg_v3`·GCP CPU VM 실행). 수행 결과·파일은 폐기하고 어떤 새 결과와도 합산하지 않는다. 미추적 `prereg_v3.json`은 작업트리에서 제거했다.

### 8.2 GPU 경로 현황 (e2ewarp, PR #570 draft)
- source `718777118`, `mjwarp_batch_v1`, `warp_native_contact_v1`, noslip0, `elapsed_sim_v1` 채택.
- **R4**: self-map funnel 1806→48→**48 keyframes**(R3 0), 6스트림×8, off-modulo 48/48; LLM 18/18; 독립 검증자 "확인됨".
- **4조건 GPU 스모크**: keyframes 48/48/54/46(peer_en/no_comm/leader_en/structured), LLM 18/18·18/18·17/18; `E2E_success=false`, `student_execution=false`, `cap_end`; 독립 검증자 "일부만 확인됨"(structured timeout=journal 늦은 200, wall 두 기준 병기, queue rejection_table cross-ref, structured rejection 누락, run dir `sha256.json`).
- **부품 어댑터(기본 off·Mac 비물리)**: release(e2ewarp release_factory, 13 tests), map correction+loaded FK(24 tests), zone visdet+GPU 외관 캘리브레이션 gpu_calib_v1(35 tests, zone 33/33·floor FP 36/180→0).
- **components manifest**: `components.r4-integration-v1.json`(ready=false). mission prepare → `DEPENDENCY_WAIT:navigation`.
- **PR #595**: 통합 기록용 draft였으나 base 대비 324파일·+54k, CONFLICTING으로 검토/병합 불가 → **기록 전용으로 닫고**, 최소 PR을 main에서 새로 만든다.

### 8.3 Codex 독립 리뷰 요지 (2026-10-18, 6/10)
- 잘한 것: CPU 중단·비합산, R4/4조건 원본 재계수·정직 라벨, timeout/ wall 정정 공개, fail-closed 유지, VM/원본 관리.
- 문제: (1) 최신 결정 지연 준수(CPU 경로·전원 HOLD), (2) **e2ewarp 통합 코드가 정적 지도 등록(`static_map_registration`,`own_and_static_map=true`)을 필수로 강제** — 2026-10-17 "정적 지도 미사용·자기중심 기억" 결정과 **계약 불일치**, (3) e2ewarp는 **3로봇** 전제 — 현재 목표(2로봇 서쪽→문→동쪽 B 운반)와 미션 불일치, (4) "ACT가 blocker" 설명 불완전 — **첫 blocker는 navigation**(wheel hold), 이후 loaded FK·registration·release·evaluator·ACT, (5) ACT 10k 재현·통합 스모크 마감 옵션의 가치/목표 부합성 문제, (6) 계획표 stale·미추적 CPU prereg·checkout 브랜치 상태 등 위생, (7) 검증 완료 전 확정적 요약 지양.
- 제안: 최신 main에서 최소 PR로 계약(2로봇·영어 4조건·정적 지도 없음·자기중심 기억·MJWarp/noslip0) 고정 → navigation·loaded FK·release·evaluator MJWarp 관문 먼저 → ACT는 실패 원인에 연결된 새 후보 1개로 소규모 물리 관문 → peer_en 1조건·1시드 처음→끝 운반 성공 후 4조건 확장.

### 8.4 다음 작업 (정렬)
1. **계약 정렬 결정(사용자)**: (a) e2ewarp를 2로봇·정적 지도 없음·자기중심 기억 계약으로 재설계, 또는 (b) e2ewarp를 과거 설계 기준선으로만 유지(연구 결과 아님).
2. **navigation owner 부품**을 MJWarp에서 구현/이관해 wheel hold 제거(서쪽→문→동쪽 B 실제 주행·자기 RGB 도착 확인).
3. loaded FK·static registration·release·evaluator MJWarp 관문 순차 통과.
4. ACT는 실패 원인(물리 grasp 기하/데이터 규모/행동형식)에 연결된 후보 하나를 골라 소규모 물리 관문 → peer_en 1조건·1시드 처음→끝 → 성공 시 4조건 확장.
5. 최소 PR·계획표·위생 유지(검증 전 요약 확정 금지).

