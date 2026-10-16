2026-10-03 독립 종합 검토입니다. **현재 가장 작은 다음 단계는 최신 후보의 approach collision guard와 닫기 전 시야/입장 경계를 구분하고, 같은-tick abort/dispatch를 offline에서 닫는 것입니다.** staged loaded 이력 복원과 opening rendezvous의 공개 개선은 인정합니다. 그 뒤 고정 소스의 작은 운반 전체 연결, 통신이 바꿀 수 있는 허용 결정 하나, 본실험 freeze 계약 순서입니다. 모든 레거시·통계 문제를 고칠 때까지 DEV를 기다리게 하자는 결론은 아닙니다.

관련 #216 #219 #221 #222 #223 #224 #226. 개별 결함 이슈를 과도하게 만들지 않도록 네 개의 논리적 묶음으로 편집했습니다.

## 읽는 순서

| 묶음 | 핵심 내용 | 적용 시점 |
|---|---|---|
| 이 글: 우선순위·최신 상태·검토 범위 | 무엇을 먼저 가르고 무엇을 기다리지 않아도 되는지 | 지금 |
| **실행·증거 신뢰성** | shared abort/staged history 해소/PF expiry, prompt, 새 live usage 개선, receipt/log/export/report | 현재 선택한 실행/기록 경계 |
| **연구설계·관측·통신 인과** + 참고 댓글 2개 | 관측 반례, legal-action witness, total/delivery/format 효과, PAR2·반복·분모·검정, primary 문헌 | DEV 해석과 본실험 freeze |
| **선택·레거시 경로** | v63 RGB/실물/ACT/relay/Kaggle/legacy runner·training·WS, #3532건, 통과한 기하/#293/#309 | 해당 경로 재사용 전 |

게시가 완료되면 위 묶음의 직접 링크를 이 이슈 후속 댓글에 연결합니다. 각 본문에 immutable source 링크·도달 조건·합성 재현 결과·수용 기준·반박한 의심을 남겼습니다.

## A. 최신 상태에서 먼저 판별할 세 가지

| 우선순위 | 공개 상태/독립 확인 | 다음 행동과 종료 기준 |
|---|---|---|
| **A1. 최신 후보의 최초 미도달 경계** | #363 `73429982` 공개 DEV는 opening look/합류 통과 후 approach collision guard 또는 wait_close의 preclose 거절을 보고. HIGH staged는 gate 입장 전 미도달 | 같은 source/조건의 own frame·command·guard receipt로 각 거절을 구분. 과거 rendezvous/영상 거절을 현재 최초 blocker로 되돌려 설명하지 않음 |
| **A2. 독립 입증된 command 경계** | staged loaded history는 새 순서 전달로 해소 인정. shared Runtime의 나중 peer abort 뒤 이미 모은 non-hold dispatch는 현재 source에도 잔존 | actor 상태 전파 후 최종 veto·같은 tick hold를 offline에서 확인. staged의 완전 시간동등성은 미검증으로 구분하고 실제 DEV 실패 원인으로 단정하지 않음 |
| **A3. 작은 고정 DEV 전체 chain** | 검토 동결 #371 `1883c56` v100은 live/model_usage에 더해 이미지 청구·own_status·idle-only look_around를 연결함. __CHARS__와 model-facing own_status의 absolute/relative 시각 혼용은 잔존, judge는 PROVISIONAL | prompt·status 시각을 닫고 기존 live의 request→message→own claim→paired job→판정을 연결. 접근→파지→운반→release의 첫 미도달 단계와 실제 심판 범위를 기록. 한 번 성공은 feasibility |

[17:01Z 공개 DEV 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5971355260)은 코드 `3358372e`/기록 head `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`에서 두 로봇의 opening look이 7.8초에 끝나 합류를 통과했다고 보고합니다. `raise_high`는 approach의 `PAIR_COLLISION_GUARD`, `raise_high_align`은 `wait_close`까지 진행한 뒤 `BEAM_UNCERTAIN → PREGRASP_NOT_READY`로 멈췄습니다. HIGH staged 두 경로는 적재 상태 오류가 사라졌으나 `gate_ok=false`/명령0으로 입장 전 미도달입니다. floor staged 두 경로는 폐기하고 정상 opening look을 유지하는 align 진입으로 바꿨습니다. P03은 미시작입니다. **저자의 공개 요약이며 raw 독립 검증·운반 성공 확인이 아닙니다.**

**과거 rendezvous 진단의 위치:** 7623/81db의 busy opening 대 idle admission 분기 검토는 당시 기록으로 보존합니다. 새 [v98 look-around](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_lookaround.py#L1-L23)는 장애물 법선 방향 불확실성 margin과 중복 hold를 바꿨습니다. 최신 합류 통과 보고 이후 이 과거 분기를 현재 최우선으로 반복하지 않습니다. rendezvous5초는 첫 accepted submit 기준이며 heartbeat와 다르고, 명령 개수·absolute/elapsed 차이는 clock skew 증거가 아니라는 source 해석은 유지합니다.

과거 scan400/measured0은 admitted absolute fix0이며 likelihood weighting/resampling0이 아닙니다. 과거 SELF_INVALID_IMAGE가 현재도 blocker라는 표현은 철회합니다. #359 clipping 수치도 그 기하에서만 의미가 있어 별도 staged 실패 원인으로 합치지 않습니다. PF expiry 결함은 sub-grid duration/다른 prediction partition이 실제 trace에 있을 때 추가합니다.

## B. 본실험 freeze·결과 주장 전

1. **심판→배정 분모→통계를 한 계약으로 연결합니다.** 역사적 4조건 DRAFT의 primary는 PAR2, label-blind delivery fallback, binary success는 핵심 보조입니다. v99/v100의 2로봇/one-beam 가능성 pilot와 같은 본실험이 아닙니다. 기존 P06 fixed denominator를 새 writer/runner/분석까지 연결하고 repeat·attempt·missing을 보존합니다.
2. **검정 질문과 설계 가정을 고정합니다.** 반복 성공 평균.5는 McNemar binary pair가 아닙니다. mean-null과 sign-flip exchangeability null은 다릅니다. cap108/산술144를 보장된 N으로 쓰지 않고 실패 atom·discordance·반복ICC·순차/다중절차 전체를 검산합니다. 이번 합성 계산은 실제 UGRP 성능/Type-I/FWER 추정이 아닙니다.
3. **통신 효과를 정직하게 한정합니다.** no_comm에도 공통 sync/executor 조정이 남고 v100의 허용 idle 재관측 선택도 구분합니다. peer total효과는 내용·prompt·추가 호출·timing·비용을 포함합니다. sender의 사적 증거가 receiver의 현재 허용 행동을 바꾸는 witness가 없으면 claim/timing/intent 조율로 질문을 좁힙니다.
4. **완전성·미정의를 표시합니다.** directory 내부 symlink bytes·console 저장 실패·export 중 외부 source 변경을 보존합니다. provenance unknown을 단일 bundle 확인으로, 단계 진입 분모0을 단계 성공률0%로 표시하지 않습니다. unknown 비용은 새 model_usage completeness로 읽습니다.

## C. 선택 경로에서만 먼저 고칠 것

일반 v63 own+TOP realtime open carry의 detached `planned` 누락, 실물 stop_all/servo settle, ACT pipe write deadline, relay/Kaggle 연속 인계, legacy cleanup/late usage, ACT split guard, 선택 RL reset, 퇴역 WS/미사용 snapshot은 해당 경로의 조치입니다. 현재 wrist-only 영상 원인으로 합치지 않습니다.

특히 **#353 `6fc4`의 opt-in 도구 2건**은 사용 전 조치가 필요합니다. pack_frames의 원본 일부 삭제 실패 뒤 retry가 기존3-frame archive를 남은2-frame으로 덮어써 프레임/hash를 잃는 P1, standalone cap guard가 leader 종료만 보고 TERM 무시 descendant를 남기는 P2를 temp fixture에서 독립 확인했습니다. 실제 사용자 outputs를 삭제/변환한 것은 아닙니다. 원본 JPEG 의무 제거 정책 자체를 뒤집는 리뷰도 아닙니다.

최신 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 [보존 규칙](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/AGENTS.md#L55)은 진행 중 작업·최근3일·대표 영상·사전 등록 본 연구 범위 외 과거 이미지 원본의 정리를 허용하면서 텍스트·원장·결과/trace·삭제 이미지 sha256 목록은 항상 보존합니다. 이 정책을 존중합니다. O14는 원본 삭제 허용 여부와 별개로 이미 검증한 archive와 필수 hash 목록까지 retry가 축소하는 결함이며, O15의 descendant 종료 경계도 정책 변경으로 해결되지 않습니다.

## D. 개선·통과·반박은 그대로 인정합니다

- #363 `73429982`의 staged loaded 이력 복원과 공용 `zone_pair_vision.py`의 main 바이트 복구를 확인했습니다. 전용 gate/둘러보기 변경의 전체 인수나 운반 성공을 대신하는 확인은 아닙니다.

- #371 v100 `1883c56`는 e0ad의 live/model_usage 실패·unknown 보존을 유지하고, 이미지당 1490의 요청 모양 보정 청구와 닫힌 own_status·idle-only look_around를 추가했습니다. ‘live 전체 비용 소실’, ‘이미지 비용 미연결’, ‘LLM은 claim만 조절’이라는 옛 범위는 최신에 적용하지 않습니다. __CHARS__는 남으며 새 회복/운반 효과·완전한 정보 비간섭을 검증한 것은 아닙니다. 1883은 비용 버전·SIM 시각 기록을 명확히 하고 own_status의 partner 영향도 양조건 공통 신호로 명시합니다. #363 staged 복원은 별도의 변경으로 인정합니다.
- v3 nominal FK/camera/source pin과 현재 3개 map의 정적 연속 sweep은 검사 범위에서 통과했습니다. actual loaded sag·contact·실물 calibration·E2E 인증은 아닙니다. shared planner endpoint는 주요 caller 보완을 확인해 새 current blocker에서 제외했습니다.
- #293 수정 후 causal-window/분모 22개 표적 합성 unit, #309 최신 stream pending/resume/보호 12개 unit은 한정 통과했습니다. 전체 PR 승인·실험/삭제 승인이 아닙니다. 과거 이미 수정된 지적을 반복하지 않습니다.
- P06 고정 분모·ledger unknown·유료 요청 후 retry 금지·일반 RGB fresh/own 입력 경계는 이미 방어가 존재합니다. test 수를 물리 성공이나 전체 통계적 타당성으로 승격하지 않습니다.
- #344는 병합 상태, #372는 기존 독립 승인과 후속 보완이 있습니다. 무근거 재차단하지 않고 블라인드 채점 절차를 유지합니다.

## 검토 범위·현재성·제한

원래 재현 기준 main은 `f2577bb5121748644df31eb0fc5a1c1b94b80d80`입니다. 게시 전 snapshot은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`(4commit/4문서 변경), #363 `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`(81db 이후4commit/18file), #371 `1883c56a749dc89597d57f570d4a2243cbb9595d`(a148 이후2commit/12file)입니다. 해당 최신성 대조는 관련 source/config/test-source와 공개 설명만 좁게 읽었으며 새 테스트·실험·raw 열람은 없습니다. #353 `6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f`는 동일 head입니다. #372 `b4cd1336d3b5a77785314b69dad64f42625fd73f`, #293 `d86cc82eedbe0c6693eaf808c54ce43387723f1d`, #309 `c8379bbe16492687af9d7b2d04f85e4ae4c610cc`의 기존 검토 범위는 유지하며 이번에 새 head 재검토로 확대하지 않습니다. 과거 재현과 최신 해소/잔존을 구분하고 이후 head/rebase에 자동 승계하지 않습니다. 별도7차의 own_status 시각 혼용은 원문 함수/AST와 fake event로 재현하고 caller를 독립 검증했으며, legacy catalog와 추가 연구 검토의 범위는 해당 본문/보충댓글에 표시합니다.

- 첫 스냅샷의 열린 이슈 16개·본문/댓글 121개, 열린 PR 9개·본문/대화/리뷰 26개, 병합 #344 대화 7개를 읽고 이후 주요 PR의 최신 metadata/변경을 재조회했습니다. 이 수치는 시점별 inventory이며 게시/현재 총계가 아닙니다.
- tracked tree 분류와 Python 1,585개 AST inventory(harness395/scripts459/sim86/tests641/examples4), config/docs/notebook entry를 조사한 뒤5차에 걸쳐 핵심 및 독립 모듈을 심층 추적했습니다. workflow 48개 entry 존재·ID 중복 여부도 확인했습니다. **약 38만 LOC를 전부 한 줄씩 정독하거나 전체 테스트를 실행한 것은 아닙니다.**
- 깊게 본 경계는 current owncam/command/scheduler/ledger/provenance, 일반 RGB/perception/navigation, calibration/static geometry, real/WS/ACT IPC, dataset/split/checkpoint, source packaging, output/admission/report, 열린 PR 변경 계약입니다. 일부 큰 파일은 caller/관련 함수만 읽었습니다. 실물 hand-eye/dynamics fit·generic nonconvex sweep·일부 legacy UI/recovery 등 미심층 영역은 남습니다.
- 검증은 source 읽기, 순수 산술/AST 메서드, fake transport·worker, 기존 허용 portable/synthetic fixture, 작은 temp Git/JPEG/프로세스로 제한했습니다. 일부 정상 경계의 실제 ffmpeg/OpenCV/child process 테스트를 수행했으나 새 physics/렌더/LLM/학습·실기기 접속은 없었습니다. repo 코드·prereg·원본 데이터는 바꾸지 않았고 heldout raw/outcome을 열지 않았습니다.
- 통신 14편·로보틱스 8편의 첫 검토에 더해 가까운 선행의 primary 본문/공식 구현, 관측·의사결정·통계 근거를 추가 대조했습니다. preprint/초록만 확인한 범위·외부 재현 없음은 참고 댓글에 명시합니다. ‘최초/유일’ 기여 또는 문헌 성능과 직접 우열을 주장하지 않습니다.

고정 wrist RGB·OpenCV·정적 지도/보정·자기 발행 명령·실제 메시지, tags0·weldOFF, grip 기록 전용과 조건 공통 sync 결정을 유지합니다. 새 모델학습·mapless SLAM·카메라/FOV·태그·대규모 코호트를 이번 검토의 선행조건으로 추가하지 않습니다.
