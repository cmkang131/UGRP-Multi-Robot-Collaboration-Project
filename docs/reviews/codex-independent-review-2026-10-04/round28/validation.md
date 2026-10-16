# R28 · 오프라인 색·화물 평가 연결의 독립 QA

**최종 v2 fixture 재실행과 source 해석은 PASS다. 새 결함은 특정하지 못했다.** 원래 writer/score 함수와 작성한 협력자의 연결을 확인했으며 실제 렌더·검출·물리·현재 HIGH·기존 점수를 검증하지 않았다.

`reproduce_offline_envelope.py`를 새 임시 디렉터리의 별도 Python subprocess에서 실행하고 `--output`도 존재하지 않는 새 파일로 지정했다. exit 0, stderr 없음, 최종 `offline-envelope-result-v2.json`과 전체 JSON bytes가 같았다. 결과 SHA256은 `5e0deba094843acb2a22cadca69bb4c60aec1f26e6c7674e65a61c2d2996bccf`, script SHA256은 `c5374c1445bb2aef732ab2c603ed43e42f99bd9bf29dc02713a3afcecc2a58d8`다. source manifest의 20개 파일을 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` Git object와 독립 byte/hash 대조했다. `offline-envelope-independent-check.json` (Mac 전달본 증거).

## 실제 실행과 대역의 경계

원래 CLI parser와 render writer·score_views·matching/summary·출력 writer의 AST body를 사용한다. world·placement·평가 geometry·static map·detector·cv2·Git identity·clock은 작성된 대역이다. RGB byte token은 JPEG가 아니고 cv2 대역이 저장한 NumPy 배열도 실제 PNG 인코딩이 아니다. cargo hull 대역은 작성한 직사각형에 한정된다. CLI의 기록 source SHA가 주입한 값으로 이어지는 동작과 20개 원본 source의 독립 Git hash 대조는 서로 다른 확인이다.

| 대조 | 독립 확인 |
| --- | --- |
| 원래 writer→정상 score | 색 1 view/12 skip에서 own 3·TOP 4·merged 1, 화물 v1 plan 1 view/10 skip에서 camera 4·merged 1의 분모와 GT 검출 집계가 일치했다. |
| 평가 입력 경계 | 작성한 eval-only sentinel은 관찰한 fake detector 인수에 들어가지 않았다. 이는 선정 함수/작성 입력의 경계이지 실제 영상·검출기·모든 dependency의 비간섭성 증명이 아니다. |
| 원본 보존·재채점 | 기존 score 디렉터리는 거부되고 기존 summary bytes가 보존됐다. 새 디렉터리에서 fake detector를 빈 응답으로 바꾸면 원래 score가 검출 0을 다시 계산했다. |
| 잘못된 색 | 빨강 GT를 초록으로 반환하는 작성 입력에서 색 평가의 TOP FP 4/merged FP 1, 화물 평가의 해당 FP 0/0과 별도 camera 혼동 4가 확인됐다. |
| 관리 입력 helper | 원래 `_workflow_inputs`가 `--frames` 디렉터리를 선택하고 `path_receipt`가 색 17파일·화물 11파일을 기록했다. 정상·혼동·빈 응답 score 전후 receipt는 같았다. |
| 결과 의미 helper | 두 score 출력에 원래 `_reported_outcomes`를 적용한 결과는 빈 사전이었다. 이 출력의 offline 지표를 물리 성공 boolean으로 승격하지 않았다. |

108회는 fake detector 입력 경계 호출 수이며 독립 실험 수나 영상 정확도 표본 수가 아니다. 기존 분할·held-out seed·출력·이미지·weights를 읽거나 실행하지 않았다.

## source 해석 challenge

색 `score_views:644–725`는 eval label로 채점하면서 detector에는 JPEG와 정적 TOP 보정 또는 자기 발행 PWM을 넘긴다. `score:839–868`은 skip 및 비대상 scene을 제외하고 label의 camera 목록을 세어 분모를 만든다. 화물 `score_views:728–784`와 `_score_merged:787–870`도 detector와 truth matching을 분리하고, `score:966–987`은 정상 view당 4개 camera와 merged 1개의 분모를 쓴다. `zone_arena.LAYOUTS['zone_wide']`의 카메라 4개와 `build_authored_map`/`authored_map`의 정의 일치 검사를 source로 대조했으므로, 지원 renderer의 이 계약에 반하는 임의 camera 삭제를 반례로 올리지 않았다.

두 evaluator의 동명 필드 차이도 원래 함수와 일치한다. 색 `summarize:791–836`은 `fp_` 접두사의 색 혼동과 배경 오류를 FP로 합친다. 화물 `summarize:882–963`은 배경 FP만 그 필드에 넣고 혼동을 별도 행/표로 보존한다. 색 `top_merged`는 매치한 검출을 GT record에 표시하고 unmatched 검출만 detection record에 남겨 정상 검출의 `detections=0`이 가능하다. 화물 merged는 TP도 detection record로 남긴다. 화물 confusion matrix의 혼동과 missed가 같은 GT에 함께 생길 수 있으므로 일반적인 서로 배타적 분류표의 행 합으로 읽지 않은 원고 해석을 수용한다. 두 평가기의 필드를 잘못 합쳐 소비하는 실제 caller를 이번에 특정하지 않았으므로 새 비교 버그로 세지 않는다.

관리 wrapper는 `sim_cli:491–492`→`workflow_cli`로 연결된다. `_input_paths`의 기존 경로 인식, `_workflow_inputs`와 `path_receipt`, `_base_manifest`의 inputs_before 및 `_finish`의 inputs_after/변경 flag를 source로 확인했다. 실제 managed subprocess/전체 finalizer는 fixture에서 실행하지 않았다. 전후 receipt는 전송 중 모든 순간의 불변성·원본 진실성·임의 symlink·동시 변경·백업 완전성의 증명이 아니다. summary 단독 필드가 적다는 점과 표준 관리 경로의 별도 입력 receipt 존재를 구분한 원고가 적절하다.

R21의 S1/A3는 `eval_zone_own_perception_v3_1.py`라는 별도 caller이고, R13의 stale calibration 승격 및 R18의 replay source-filter 문제도 이 score 경로의 새 실행마다 재계산하는 계약과 다르다. 기존 문제를 새 finding으로 반복하지 않았다. source manifest 20개 일치를 모든 함수/테스트/검출 알고리즘의 심층 검토로 확대하지 않는다.

## 최종 원고

[검토 원고](README.md) SHA256 `58487be87c216bd86541de670cd136eb6b4dec5530544518cd54e0fb569a5aae`의 대역·분모·동명 지표·wrapper 미실행·현재 HIGH 제외 한정을 최종 대조해 PASS로 판정했다. 공개 현재성 API와 과거 실험 수치는 이 QA에서 재조회하지 않았다. 추가 실행이나 구현 수정은 필요하지 않았다.
