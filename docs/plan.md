# UGRP 작업 계획 (DSH 조정자 유지)

최종 갱신: 2026-10-18 14:45 KST. 이 파일이 **단일 계획표**다. 상세 원본·수치는 `outputs/e2e18-admin/ops-alert.md`(로컬), 실험별 README, PR을 따른다.

## 0. 이번 세션 목표
- 미션: 두 로봇이 서쪽 픽업존 → divider 문 → 동쪽 목적 구역으로 짐(빔/박스) 운반. 근거리 파지·놓기는 ACT.
- 입력 경계: 정적 지도·좌표계·top 카메라·정답 금지. 자기 RGB·자기 발행 명령·자기중심 기억만. GT는 평가 칸만.
- 검증 관문(2026-10-18 사용자 결정): 병합·사용자 보고 전 독립 verifier(원본 재계수·조건 감사). 최종 관문 2, 중간 1.

## 1. 작업 스레드 상태 (2026-10-18 14:45 KST)
| 스레드 | 상태 | 다음 |
|---|---|---|
| act18 (PR #575, merged) | R8/R100 100k fp32 **TRAIN4 0/4 NOT_READY**(Release 재현용). 튜닝 트랙: B1 done 양성배치(h=0 학습 실패) → B2 표준축 20k(실패) → B3 h=0 라벨(실패) → **B4 done cmd-history GRU 헤드(4/4 issued_done 성공, 물리 lift 0/4)** → **co-r2 70k TRAIN4 0/4**(issued_done 4/4, lift 1/4, release 0/4). gcp2 TERMINATED·CLEAN. | 데이터 규모/새 녹화 / closed-loop 제어 / 평가계약(물리 성공 정의) — **사용자 결정** |
| beamact5 (PR #585 merged, #588 draft) | r4c 검색축 수정(10 회귀 해결) → r10–r13 **align breakaway**(align 정체=40ms pulse static friction) → case27 단독/batch 통과 일부. **두 39-gate attempt 모두 37/40 FAIL**(27 flaky 1/3·37 expected). gcp6 TERMINATED·CLEAN | 27 안정화(align 이전 상류) 또는 margin-aware 재승인 — **사용자 결정** |
| visgoal (PR #582, #592 draft) | 후보 B/C 종료. **Stage A FAIL**(GT 문통과 1/16, gap 주장 9/9 허위) · **Stage B FAIL**(적재 16/16 유지했으나 문통과 0/16, 화물이 하단 화면 가림) · fix v1 FAIL(문 0, 원인 분해) · **fix2 gate 진행 중**(12:58 시작, ETA 15:15 KST) | fix2 결과 → 재계수·PR #592 → gcp3 정리 |
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
- **fix v2 진행 중**: paint 필터 range 조건부·gap 양쪽섹터·approach escape. 12:58 시작, ETA **≈15:15 KST**. 원본 `runs/crossroom-stageA-fix2`.
- 기록: `experiments/2026-10-18-crossroom-carry/{stageA,stageB}`·PR #592. **다음**: fix2 결과 후 재계수·PR, loaded `crossroom-stageB-fix` 설계.

## 6. 인프라·비용 (2026-10-18 14:45)
- VM: gcp2 **TERMINATED**, gcp6 **TERMINATED**, gcp3 **RUNNING(fix2 gate)**; gcp4·gcp5 off.
- DeepSeek 잔액 **≈USD 23.8**(충전 반영 후, 감시 중). GCP 예산 정지 장치 유지.
- 노트북 덮개 슬립 가드(`SleepDisabled=1`+launchd heartbeat 자동 복구) 유지 중 — 작업 종료 시 자동 복원.
- PR: 오늘 병합 #533·#537·#545·#563·#575·#585·#586·#587·#589·#590·#591. 열린 draft #588(beamact5)·#582/#592(visgoal). #570·#566·#564 등 과거 draft 유지.

## 7. 다음 이벤트
- visgoal fix2 gate 결과(~15:15 KST) → 재계수·PR #592·gcp3 정리.
- 사용자 복귀(15:00) 후 결정: act18 데이터/closed-loop/평가계약, beamact5 27 안정화 vs 재승인, visgoal fix2 이후 방향, crossroom Stage B.
- 핸드오프 상세 수치·원본 SHA: `outputs/e2e18-admin/ops-alert.md` 및 각 실험 README.
