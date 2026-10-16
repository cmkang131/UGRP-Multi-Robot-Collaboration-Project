# 게시 전 현재성: 7차 snapshot과 필수 정정

## 범위와 동결

2026-10-03 게시 재개 요청 뒤 GitHub 읽기 전용 metadata/compare/file/comments로 다음 snapshot을 확인했다. source cutoff를 한 번 정한 뒤 새 push를 무한 추적하지 않는다. GitHub 쓰기·브라우저·구현·테스트·모델·물리 실행은 하지 않았다. raw/blind/결과 원본은 열지 않았다. 공개 PR 본문/댓글의 수치는 저자 보고로만 취급한다.

| 대상 | 이전 freeze | 이번 snapshot | 변경 범위 |
|---|---|---|---|
| main | f2577bb5121748644df31eb0fc5a1c1b94b80d80 | b23fc0875b72f4b55f399a252a1575b7e8b43cb5 | 4 commits, AGENTS/disk/TensorBoard/ultrasonic 문서4개 |
| #363 | 81dbb3eb5c0a915b6b314e3c4898ea253f890267 | 73429982ea3088f2569c26cf7a4b5b74a1e6c1a6 | 4 commits/18 files; 관련 source·test source·공개 설명을 좁게 검토 |
| #371 | a1487266804860b88478fc68dbe3df6fea3a943d | 1883c56a749dc89597d57f570d4a2243cbb9595d | 2 commits/12 files; 별도 round7-pr371-currentness.md |
| #353 | 6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f | 동일 | 기존 opt-in tool finding source 변화 없음 |

#372/#293/#309는 이번에 최신 head를 다시 검토하지 않았으며 기존 범위를 확대하지 않는다. main 코드가 그대로라는 말은 compare에 source code 변경이 없다는 뜻이며, 전체 저장소를 다시 읽거나 실행했다는 뜻이 아니다.

## #363 해결/남음/미검증

- **해소 인정: staged loaded 전이 이력 미전달.** `harness/zone_pair_highpose_staging.py:132–157`의 `own_history`가 pre-close posture, close, 이후 raise를 순서대로 구성하고 `318–333`의 `StagedRuntime.initial_commands`가 actor.on_command로 보낸다. `tests/test_highpose_dev_pilot.py:555–583`는 fixed delay 뒤 loaded=True/최종 PWM을 구 single-row False와 비교한다. 새 테스트는 읽기만 했다. 과거81db 반례는 역사적 재현으로 유지하며 현재 P1으로 게시하지 않는다. 모든 row t=now 전달이므로 전체 원래 motion/camera/settle epoch 동등성은 미검증이다.
- **해소 인정: 공용 vision 바이트 회귀.** `harness/zone_pair_vision.py`를 원격73429982에서 읽어 main f257 로컬 원본과 byte 비교했다. SHA256 `cce72504edf01d119aafbefc8cb4ea1aa5a407196f9809f6cb5b8ec0bfecc9fc`가 같았다. 새 `zone_pair_highpose_frame_gate.py:1–18,137–139`는 원래 code object에 private import binding을 적용하고 `zone_pair_highpose_runtime.py:408–445`는 v98 actor에만 적용한다. 이 구조 확인이 전체 테스트 통과나 기능 안전성 인증은 아니다.
- **남음: same-tick abort 뒤 이미 수집한 non-hold dispatch.** exact compare에 shared `zone_final_pair_runtime.py`, `zone_pair_executor.py`, `zone_final_pair_skill.py`, backend의 변경이 없다. `zone_pair_highpose_runtime.py:431–445`는 shared Runtime.step 상속을 유지한다. 새 `Execution.step:370–373`은 기존 PairExecution.step code object의 frame gate import를 바꾸며 수집 후 terminal veto가 아니다. `scripts/run_pair_highpose.py:210–217`도 반환 batch를 바로 issue/on_command한다. 기존 offline port 반례를 현재 source에 연결한 판단이며 새 재현·physics 실행은 없다.
- **현재 공개 DEV 우선순위 이동.** 댓글 `5971355260`(17:01:31Z)은 실행3358372e/기록73429982에서 둘 다 opening look7.8초·합류 통과, approach `PAIR_COLLISION_GUARD`, align 경로 wait_close에서 `BEAM_UNCERTAIN→PREGRASP_NOT_READY`를 보고한다. HIGH staged는 loaded 오류 해소 후 gate 입장 전 명령0, floor staged2개는 폐기, P03미시작. 댓글 `5971618075`(17:23:43Z)의 CI 전체 통과도 저자 보고다. raw/CI 독립 실행으로 승격하지 않았다.
- **새 guard 미검증 범위.** `zone_pair_highpose_lookaround.py:1–23,47–55,155–175`는 own covariance의 obstacle-normal sigma margin과 duplicate hold 제거를 명시한다. 옛 busy 대 idle-admission 판별을 current 최초 blocker로 반복하지 않는다. 이번 범위는 실제 안전/효능을 독립 입증하지 않는다.

## main 보존 규칙과 #353

main `AGENTS.md:11,55`, `docs/disk_management.md:127–134,152`는 텍스트/원장/결과·trace/삭제 이미지 hash 목록 항상 보존, 이미지 원본은 진행 중 작업·최근3일·대표 영상·사전 등록한 본 연구 범위로 좁힌다. 허용된 과거 플랫폼 개발 이미지 정리를 막는 결론을 쓰지 않는다.

그러나 #353 O14는 허용된 원본 삭제 뒤에도 필수 hash 목록과 이미 검증한 archive를 retry가 축소하는 source/합성 재현이다. hash 목록의 항상 보존과 재실행 안전성이 여전히 필요하므로 유효하다. O15의 leader 종료 뒤 descendant 잔존도 이미지 정책으로 해소되지 않는다. 실제 사용자 자료 삭제/정리/변환은 하지 않았다.

## #371

별도 담당이 두 SHA의 좁은 source delta를 읽었다. `round7-pr371-currentness.md`의 상세 줄을 근거로:

- `__CHARS__`는1883 prompts113–117/150–173에도 잔존. e0ad실행→a148source→1883source의 제한된 연결이다.
- image billing은 유지되며 billing83–119가 보관행 정책 v1/v2 검증, case130–133은 현재writer v2강제. canonical model_usage 보존도 유지.
- status23–33은 partner-caused 자기 결과/시간 신호가 양조건 공통 노출됨을 명시; builder 의미는 동일. 완전 비간섭·1bit 정보량 상한을 주장하지 않는다.
- prompt76–87은 look-around 회복을 보장하지 않도록 문구 완화. dispatch321–328/449–458/505는 SIM 시각 필드를 명시. 새 기록 필드가 그 자체로 clock 정합성/실제 복구를 입증하지 않는다.
- v100 DRAFT_UNSEALED/research_result=false, 물리·모델 미실행, #363 rebase대기는 유지한다.

## 본문 편집과 before/after

root의 명시 위임 뒤 기존11 payload 중10개만 현재성 관련 부분을 편집했다. references 댓글은 바이트 그대로다. 이슈/댓글 제목·대상은 유지했다. 과거 재현 코드는 수정하지 않았다.

| 파일 | 필수 정정 |
|---|---|
| final-index-issue.md | A1/A2 현재 DEV·staged해소, A3/D371새cutoff, main정책·coverage |
| final-execution-issue.md | E0구rendezvous 역사화, E1현재source앵커, E2loaded해소, E4최신371 |
| final-research-issue.md | 최신DEV보고,371status/look/billing설명·cutoff |
| final-optional-issue.md | #353 finding이 현재 보존규칙에도 유효함 명시 |
| final-reproduction-comment.md | E2과거재현/현재해소 구분, E1최신source연결 |
| final-peer-abort-reproduction-comment.md | 최신source상속/runner연결 |
| final-research-causality-comment.md | 371새cutoff와공통정보·회복미검증 정정 |
| final-pr363-comment.md | 구staged/공용vision차단 해소, 최신DEV와남은same-tick경계 |
| final-pr371-comment.md | 좁은delta의개선 인정·__CHARS__잔존 |
| final-pr353-comment.md | 현재보존정책하에서도hash유실/descendant문제유효 |

편집 전 13파일(11payload+JSON/MD manifest)은 `round7-before/`에 보존했다. 정확 before/after는 `round7-publication-before-after.diff`다. 원고 code fence 짝·workspace 링크 부재·해시/길이만 확인한다. 기존 QA 전체나 재현을 다시 돌리지 않는다.

이 메모의 최신성 정정 단계와 추가 round7 신규 발견의 독립 검증/보충댓글은 별개다. browser_publish는 최종 manifest SHA와 READY 신호를 받은 뒤 동일바이트를 게시하며, 로컬 편집은 게시 완료가 아니다.

## 2단계 신규 내용 통합과 보충 QA

root의 최신 배치 결정에 따라 base11 복구 snapshot 이후 execution E4a/PR371/index에 own_status clock-mix P2, optional O16에 catalog 기본값 불일치 P3를 추가했다. 추가사항은 round7-independent-validation.md의 actual caller 독립검증을 통과했다. catalog의 직접 sim_actions.run 무인자 default35 경로는 실패 범위에서 명시적으로 제외했다. 새로운 합성 재현은 source-only 최신성 단계와 분리했다.

신규 research 보충은 통신×선택적 sensing의 정책상호작용/준비근거 유효기간/평가 artifact-target-procedure 세 축이며 독립 QA의 F/W 비배타성·outer feedback규칙·finite trace와knowledge정리 구별을 반영했다. 문헌·소스 검토만 했으며 실제 연구 결과는 아니다.

신규 current-blocker 보충은 게시 editor가 source를 직접 교차 읽었다. exact734의 zone_final_pair_guards126–145는 BEAM_UNCERTAIN이 beam_track None뒤/wallclearance계산전임을 확인했다. unchanged pairguards756–794는 arm/recheck/base motion에 공통PAIR_COLLISION_GUARD를 쓰며, highposeprovider57–106과staging98–109는HIGH의settle/frame pipeline과look생략을 확인했다. beamtrack169–193의현재partialpoints요구도확인했다. 1200/3000은60/150초의.05tick수와일치하는분모비교이며독립image시도수측정이아니다. 공개reason이해당event라는조건을유지했고raw원인을확정하지않았다.

신규 공개 파일은 final-round7-research-comment.md(research댓글), final-round7-blocker-comment.md(execution댓글)이다. 최종13manifest만실제게시기준이고round7-base-publication-manifest.json/f55bc1…은1단계복구snapshot이다.

### 최종 공개문 QA 마감

독립validator가 E4a/PR371신규단락/O16/연구보충을 readback하여 게시가능 판정했다. last_end는reset-relative event delivery시각이라는 정밀도수정과 연구제목의단순비교한정을 반영했다. runtime담당은 현재blocker보충의3조건부진단을 승인했고 parent on_frame은항상호출되며observer시도에settle요건이적용된다는 한문장교정을 반영했다. 첫표7.8/54.1은absoluteSIM으로명시했다. 이후새조사·source head추적·테스트확장은없다.
