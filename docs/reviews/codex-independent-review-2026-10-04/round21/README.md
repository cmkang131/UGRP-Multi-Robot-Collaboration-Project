# R21 · #220 그림자·가림과 #225 교사 지원의 실제 범위

**새 결함은 올리지 않는다. #220은 남은 인수 계약·현재 호출 경로를, #225는 보존된 교사 TOP 인식 경로의 적용 범위를 확인했다. 두 이슈의 실제 영상 인수·교사 재시연은 계속 미검증이다.** 이 문서가 이슈 해결이나 전체 검토 완료를 뜻하지 않는다.

2026-10-04 공식 [#220](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/220), [#225](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/225) 본문과 각 전체 댓글 1개를 먼저 읽고, 관련 병합 PR [#193](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/193), [#207](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/207)의 본문·전체 댓글을 확인했다. 공개 본문에 적힌 과거 수치는 작성자 보고이며 이번 검토가 독립 채점한 값이 아니다. `shadow-teacher-official-sources.json` (Mac 전달본 증거).

소스는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`의 Git object에서 읽었다. 공유 checkout의 오래된 HEAD를 최신 코드로 간주하지 않았다. 선정한 12개 `.py` 파일은 세 pin에서 바이트 동일했다. `shadow-teacher-source-check.py` (Mac 전달본 증거), `shadow-teacher-source-evidence.json` (Mac 전달본 증거).

## 공식 요구와 앞선 검토

| 이슈 | 실제 요구 | 이번에 다시 세지 않는 항목 |
| --- | --- | --- |
| #220 | 자기 손목 카메라의 동료 판별·팀 화물·집게 예측 영역의 **그림자와 가림 영상 오류**를 줄이고, 사전 등록 기준과 표식 0개 최종 환경 렌더링에서 재평가한다. 여기서 shadow는 그림자이며 병행 정책의 noninterference 요구가 아니다. | 이미 이슈 댓글에 있는 `unknown_ratio or 1`과 검출기 자신의 `held_silhouette()`로 만든 시험 영상의 독립성 문제. R14 optional M1 reanchor와 R17 HIGH beam crop은 다른 caller의 증거다. |
| #225 | PR #169의 B2·B3·B4·B5·B8 교사 실행기 막힘을 지원한다. **시연·학습 표적·평가 전용**이며 연구 실행기·학생 성공으로 보고하지 않는다. 공개 댓글은 B2/B8 선언 순서와 TOP green 검출 N1을 open으로 남겼다. | R13 teacher planner의 convex part·route 검사는 source-only 반증이다. B3/B4의 과거 제한적 시연, B5의 오프라인 확인을 새 물리 성공으로 세지 않는다. |

R1 이슈 검토 (Mac: `evidence/review-notes/issues-review.md`)와 [R19 탐색표](../round19/issues.md)를 먼저 읽었으며, R19의 두 이슈 미확인 표시는 유지한다. R20 #213은 학습 segmentation의 랜덤화와 현재 provider 소비 여부를 다뤘고, 이번 own-perception/teacher TOP caller와 겹치지 않는다.

## #220: S1과 밝은 가림 A3는 같은 통과선이 아니다

선정한 남은 경로는 `scripts/eval_zone_own_perception_v3_1.py`의 원래 판정 producer/consumer와 `harness/zone_own_perception_v3_1.py`의 현재 직접 호출자다. 기존 프레임·라벨·summary·manifest는 열지 않았다.

| 현재 소스 계약 | 읽을 수 있는 뜻 |
| --- | --- |
| `score_views:265–291`은 tick 답들을 `outcome.track`으로 모아 `record='view'`를 만든다. | S1과 A3 모두 view×judgment 단위이며, 하나를 단일 프레임 오류·다른 하나를 다중 프레임 오류로 비교하면 틀린다. 원시 tick 수를 독립 표본 수로 읽지 않는다. |
| `compute_gates:448–449,498,520`의 S1은 view의 결정 답이 truth와 다르고 confidence ≥ .65인 수를 세며 **0건**을 통과선으로 둔다. | stress 조명들에 대한 명시적 gate가 존재한다. 원래 producer에서 unconfirmed view는 `unknown/0.0`이므로 이 오류 수에서 제외된다. `status`를 직접 검사하지 않는다는 이유로 정상 producer의 판정을 잘못됐다고 보지 않는다. |
| `compute_gates:477–478,494–497,523`의 A3는 밝은 부분 가림에서 `status='confirmed'`인 오답 수를 기록하지만 `report_only=['A3','S2']`다. | 공개 이슈의 밝은 가림 잔여항목을 S1 gate와 합쳐 “같은 사전 등록 통과선 실패”라고 쓸 수 없다. 이 evaluator에는 A3 별도 합격 문턱이 없다. 이는 명시적인 보고 전용 계약이며 새 구현 버그가 아니다. |
| `compute_gates:511–512`에는 기존 T3의 `unknown or 1` 표현이 남아 있다. | 이미 보고된 결함의 현재 소스 확인만 했다. 다시 재현하거나 새 finding으로 세지 않았다. |

따라서 #220을 닫을 때 필요한 것은 어떤 현행 detector/caller를 대상으로, S1·밝은 가림의 어떤 판정 단위와 사전 등록 문턱을 쓸지, 표식 0개 최종 환경의 어떤 독립 자료로 재평가할지의 연결이다. **이번에 읽은 공식 이슈·PR와 선정 evaluator에는 밝은 가림을 합격 판정으로 승격한 후속 계약이 확인되지 않았다.** 저장소 모든 미열람 문서에 없다고 단정하지 않는다. 기존 test 결과를 본 뒤 문턱을 소급 변경하거나 현재 HIGH가 예전 gate를 자동 상속한다고 취급하는 권고도 아니다.

현재 호출 범위도 제한된다. 세 pin의 `harness/`, `scripts/`, `sim/`에 있는 Python 소스에서 `zone_own_perception_v3_1` 직접 import를 찾으면 오프라인 evaluator와 `tile_own_vision.image_information`이 나온다. tile의 `inspect:123–128`은 정보 gate를 거친 뒤 자체 target/holding 판단을 한다(`tile_own_skill:179`에서 호출). **tile이 v3.1의 팀 화물·손잡이 판단 전체를 사용하는 것은 아니다.** 이 좁은 재사용을 #220 전체 기능의 runtime 채택·인수로 세지 않는다. import 검색은 명시적 소스 참조의 확인이며 임의 동적 로딩 부재에 대한 증명으로 확대하지 않는다.

#363 HIGH의 기본 provider는 `vision_pose_source_highpose.OpenCVObserver`로 연결된다. #371은 `pair_llm_case`→`zone_final_pair_runtime.Runtime`→기본 `vision_pose_source_pair_v3` 계열이고 기본 worker는 `VisionWorkerClient`다. #371을 HIGH OpenCV로 부르지 않는다. 두 실행 경로의 실제 위치추정/영상 실패가 #220의 과거 그림자 오류에서 생겼다는 근거는 이번에 없다. v3.1 손잡이 wrapper는 영상 정보가 충분하면 v3 답을 돌려주므로, 정보 gate의 존재만으로 “그림자에 의한 의미 오류가 모두 차단된다”는 주장도 할 수 없다.

소스: [view producer](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/eval_zone_own_perception_v3_1.py#L240-L291), [A3/S1 gate](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/eval_zone_own_perception_v3_1.py#L443-L523), [미확정 tracker 출력](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_own_outcome.py#L137-L152), [손잡이 wrapper](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_own_perception_v3_1.py#L259-L291), [tile helper 재사용](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/tile_own_vision.py#L123-L128).

## #225: TOP green 하한은 보존된 교사 경로에 여전히 연결된다

선정한 실제 caller는 `run_zone_teacher_fix`→`zone_dispatch_v2.run_v2`의 시작 TOP 라벨 생성이다. gate/teacher planner는 R13과 겹치므로 새로 검증하지 않았다.

1. `run_zone_teacher_fix:46–75`는 protocol v2만 허용하고, 기본 `feasibility_gate='enforce'`에서 `infeasible/order_constrained`를 실행 전 거부한다. 이후 `fix_run_class`를 주입해 기존 teacher runner를 호출한다. 소스 주석과 CLI 설명이 teacher feasibility 전용임을 명시한다.
2. `zone_dispatch_v2:300–312,348–353`의 기본 profile은 `top_cargo_v2`이며 두 시작 TOP capture에서 `detect_items`→`label_items`를 호출한다. `top_cargo_v2_track`은 opt-in이고 같은 detector를 쓰며 label tracking을 더한다.
3. `zone_perception_v2:59–65`→`zone_cargo_perception_v2:234–246,276–280`의 box 경로가 `zone_color_boxes.detect_top(...TOP_PROFILE_ZONE)`로 연결된다. `TOP_ZONE_HSV['green']`은 현재도 H 55–72, S **100**–255, V 40–255이고, area는 50–300 px다(`zone_color_boxes:78–88,220–251`).
4. `zone_dispatch_v2:400–407`은 referee 결과를 `physical_success_teacher_condition`으로 기록하고 `success`에도 복사하지만, scope가 teacher 조건의 referee goal count이며 RGB-skill/student 결과가 아님을 명시한다. 이 source의 출력 계약을 확인했으며 실제 결과 파일은 읽지 않았다.

이는 **공개 N1 보고에서 지목한 threshold와 consumer가 현재 코드에도 남아 있다는 확인**이다. 공개 댓글의 seed 22·채도 98을 이번 렌더 측정처럼 쓰지 않으며, threshold 한 줄만으로 당시 이미지 분포·오검출 원인·현재 물리 실패를 재현했다고 주장하지 않는다. 하한을 임의로 낮추면 해결된다는 처방도 하지 않는다. 색 gate·픽업 도색·다른 색/물체와의 분리·라벨 생성까지 검증해야 한다는 원래 인식 인수 범위가 남는다.

교사가 시연·학습 표적을 만들 때 정답 좌표·IK·접촉을 쓰는 것은 AGENTS의 교사 예외다. #220/#225 본문의 학생 계약은 자기 손목 RGB·정적 지도·주문서·자기 명령 이력이며 TOP/시뮬 정답은 학생에게 평가 전용이다. 일반 AGENTS의 과거 공용 TOP 기본 문장으로 이 좁은 학생 계약을 덮지 않는다. TOP을 읽는 이 teacher support path 자체를 새로운 학생 GT leak로 보고하거나, 교사 feasibility를 #363/#371 자기 카메라 성공으로 승격하지 않는다. 과거 teacher receipt L4도 원래 source에 알려진 경계이며 새로 보고하지 않는다.

소스: [교사 전용 진입점](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/run_zone_teacher_fix.py#L1-L75), [시작 인식 caller](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_dispatch_v2.py#L294-L353), [v2 box consumer](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_cargo_perception_v2.py#L234-L246), [TOP HSV 계약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_color_boxes.py#L78-L88), [teacher 결과 scope](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_dispatch_v2.py#L400-L407).

## 종료 범위

source/AST 검사만 실행했다. UGRP module import, pytest/전체 CI, 모델·학습·물리·렌더·실물·cloud·유료 작업은 없다. 실제 raw·heldout outcome·이미지·모델 가중치·dataset·실험 artifact 내용과 결과 manifest는 열지 않았다. source에 적힌 producer의 파일 읽기 코드를 검토한 것을 해당 데이터 열람으로 세지 않는다.

판정은 **#220: 명시된 기존 S1 계약과 보고 전용 A3의 차이 및 현재 caller 적용 범위 확인, 후속 최종 환경 인수 미확인 / #225: 보존 teacher TOP consumer·threshold 확인, 실제 N1 수정·시연 미확인**이다. 임의 합성 RGB나 malformed record 반례를 만들어 기존 known limitation을 새 결함으로 바꾸지 않았다. [독립 QA](validation.md)는 이 한정된 source/설계 판정을 통과로 확인했다. 새로운 실행 승인을 요청하거나 전제하지 않는다.
