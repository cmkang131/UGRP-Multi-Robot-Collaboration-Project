# 28차: 색·화물 오프라인 평가의 writer→score 계약

검토 기준은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`다. 이번 범위에서 새로 확정한 결함은 **0개**다. 등록된 두 CLI의 원래 출력 작성·채점 함수를 작은 작성 fixture로 연결해, 정상 입력의 분모와 출처 연결을 확인했다. 현재 HIGH 실행이나 과거 held-out 점수를 다시 평가한 결과가 아니다.

별도 평가기의 같은 이름 필드는 바로 합치면 안 된다. 특히 `false_positives_total`과 merged 수준의 `detections`는 두 평가기에서 뜻이 다르다. 이 차이는 원래 채점 코드의 명시적인 집계 방식이며, 그 자체를 새 버그나 기존 수치 오류로 계수하지 않았다.

## 선택 이유와 지원 범위

27차의 registry 후보 조사에서, 직접 작성한 기존 검토와 대조해 아직 render→score 연결을 닫지 않은 두 진입점을 골랐다. 이름 검색의 미적중을 전체 코드의 미검토 증명으로 사용하지 않았다.

| 등록 ID | 실제 runner | 버전·adapter | 범위 |
|---|---|---|---|
| `zone-color-eval` | `scripts.eval_zone_color_detection` | `1.0.0`, `managed_legacy_cli` | 자기 RGB·TOP RGB의 상자 색 검출 평가 |
| `zone-cargo-perception-eval` | `scripts.eval_zone_cargo_perception` | `1.1.0`, `managed_legacy_cli` | TOP RGB의 색 상자·화물 종류·자세 평가 |

둘 다 registry에서 `render --split … --output …`과 `score --frames … --output …`을 지원한다. `managed_legacy_cli`라는 adapter 이름은 현재 등록에서 사라졌다는 뜻이 아니다. 반대로 등록돼 있다는 사실도 현재 HIGH 제어기나 해당 논문의 주 평가기라는 뜻은 아니다.

- 색 평가: 기본 `baseline`은 `own_production_v1`/`zone_perception_v1`, 선택 `zone`은 `own_zone_v2`/`top_zone_v2`다. `zones/zone_wide`가 본문 집계이고 `dispatch/open`은 별도의 beam confusion 부록 그룹이다.
- 화물 평가: 기본은 `top_cargo_v1`, `top_cargo_v2`, `top_zone_v2`, `zone_perception_v1`을 모두 비교한다. 문서는 실제 연동에 v2를 쓰고 v1은 평가 기준으로 남긴다고 구분한다.
- R21의 `eval_zone_own_perception_v3_1.py`, S1 view×judgment gate, A3 report-only 지표와 **별도 caller**다. 그 acceptance 기준을 여기에 가져오지 않았다.
- 자기 RGB+TOP을 허용하는 이 오프라인 평가와 자기 카메라 기반 현재 HIGH의 입력 계약은 별개다. TOP 사용을 이 평가의 정보 누설로 판정하지 않았다.

## 원래 writer와 consumer의 연결

| 단계 | 색 평가 | 화물 평가 | 이번 확인 |
|---|---|---|---|
| 분할 입력 | 고정 `SPLIT_FILE`의 `splits[dev/test]` | 기본 분할 또는 `--split-file`; `view_plan` v1/v2 | 실제 분할 파일 대신 작성한 dev 분할만 사용 |
| render manifest | split 이름·분할 파일 SHA-256·render Git SHA/dirty·scene XML hash·view/skip 목록 | 왼쪽에 분할 경로·view plan·scene별 catalogue hash 추가 | 원래 writer가 작성한 필드와 실제 작성 분할 바이트 일치 |
| 검출 입력 파일 | JPEG 경로 + `actor-inputs.json`의 자기 발행 arm PWM·TOP 목록 | TOP JPEG 경로; 정적 TOP 보정 | 이번 fixture의 RGB는 이미지가 아닌 명시적 byte token |
| 평가 정답 | `eval-labels/`의 camera별 상자 위치·가시성·분할, robot pose | `eval-labels/`의 item pose·가시성·분할·grip truth | 평가 전용 sentinel이 fake detector 인수에 전달되지 않음 |
| score | profile별 `score_views`→record JSONL→`summarize` | 동일 구조, camera/merged 수준 | 원래 parser·score·record writer·summary 계산 실행 |
| 출력 보존 | `mkdir(exist_ok=False)` | 동일 | 기존 score 폴더 재사용은 거부하고 기존 summary 바이트 유지 |
| 재채점 | 새 출력 폴더에서 검출·채점 다시 실행 | 동일 | fake detector가 빈 응답으로 바뀌자 새 summary의 검출 수도 0으로 바뀜 |

색 평가 source: `scripts/eval_zone_color_detection.py`의 `render`(510–587), `score_views`(644–725), `_merged_top`(741–788), `summarize`(791–836), `score`(839–868). 화물 평가 source: `scripts/eval_zone_cargo_perception.py`의 `render`(551–621), `score_views`(728–784), `_score_merged`(787–870), `summarize`(882–963), `score`(966–987).

실제 검출 함수의 서명·선택 분기도 함께 읽었다. 색 검출에는 RGB·발행 PWM 또는 작성 TOP 보정, 화물 검출에는 TOP RGB·작성 보정·정적 목록이 들어간다. fixture에서는 이 함수의 이미지 처리 내부를 실행하지 않았다. 따라서 이 결과는 detector 품질·실제 PNG/JPEG 정합성·물리 카메라 보정의 확인이 아니다.

## 분모와 동명 지표의 뜻

아래 수치는 실제 실험 점수가 아니라, 상자 하나가 보인다고 작성한 작은 fixture의 **집계 동작**이다. 원래 render 반복문에서 한 view만 만들고 나머지 placement를 실패시키는 fake planner를 사용했다. 원래 view-plan 상수와 skip 기록 로직은 유지했다.

| 작성 fixture | 정상 view / skip | 실제 score의 분모 | 맞는 색 응답을 줄 때 검출된 GT 수 |
|---|---:|---|---|
| 색 평가 | 1 / 12 | own 3장, TOP 4장, merged 1 view | own 3, TOP 4, merged 1 |
| 화물 평가 v1 plan | 1 / 10 | camera 4장, merged 1 view | camera 4, merged 1 |

색 평가는 label의 camera 목록을 세어 own/TOP 분모를 만들고 정상 view당 merged 분모를 하나 늘린다. 화물 평가는 정상 view당 camera 분모를 `4×views`로 고정한다. 지원 renderer가 `zone_wide`의 네 TOP을 쓰는 범위에서는 일치한다. 임의로 camera를 지운 artifact로 이를 새 결함으로 주장하지 않았다. 기존 분할 seed의 독립성·장면 대표성·skip이 어떤 난도에 편중되는지는 확인하지 않았다.

같은 빨강 GT에 fake detector가 초록을 응답하게 바꾸되, render 산출물은 수정하지 않고 새 폴더에 채점했다.

| 같은 혼동 입력의 집계 | 색 evaluator | 화물 evaluator |
|---|---:|---:|
| 카메라 수준 색 혼동 | TOP 4건 | camera 4건 |
| `false_positives_total` | TOP 4 | camera 0 |
| merged `false_positives_total` | 1 | 0 |
| 올바른 응답에서 merged의 `detections` | 0 | 1 |

이 차이를 해석할 때는 다음을 지켜야 한다.

1. 색 평가의 `false_positives_total`은 `fp_colour_confusion`과 `fp_background`를 모두 센다. 화물 평가의 같은 필드는 `fp_background`만 세고, 종류 혼동은 `confused_as_this_from`·`box_cargo_confusion`·confusion matrix에 따로 남긴다. 따라서 화물의 해당 필드가 0이어도 종류 혼동 0을 뜻하지 않는다.
2. 색 평가의 `top_merged`는 일치한 검출을 GT record의 `detected`에 쓰고, detection record에는 일치하지 않은 검출만 남긴다. 그래서 올바르게 하나를 검출해도 그 수준의 `detections`는 0이고 `tp`는 `null`이다. 화물의 merged는 TP도 detection record로 남긴다.
3. 화물 confusion matrix는 detection의 TP/혼동과 미검출 GT를 함께 넣는다. 다른 클래스로 혼동한 GT에는 정답 클래스 검출이 없으므로 missed도 남을 수 있다. 행 합을 곧바로 서로 배타적인 GT 표본 수로 해석하거나 일반적인 단일 정답 분류 confusion matrix처럼 정규화하지 않았다.
4. 색의 상자 instance·camera·merged view와 R21의 S1 view×judgment는 분석 단위가 다르다. 이 수치를 현재 HIGH 임무 성공률·통신 효과·독립 표본 수로 바꾸지 않는다.

이 관찰은 값이 숨겨지거나 계산이 stale하다는 finding이 아니다. 서로 다른 evaluator의 명시적인 집계 계약을 한 표로 합칠 때 필요한 설명이다. 실제 보고서에서 이 필드를 잘못 합쳤다는 증거도 이번에는 확인하지 않았다.

## provenance는 summary 한 파일보다 넓다

직접 CLI의 score summary는 색/화물 모두 split 이름과 render/score Git SHA를 남기지만 `split_file_sha256`을 복사하지 않는다. 색 summary는 render dirty도 복사하지 않고, 화물 summary는 이를 보존한다. 색/화물의 원래 render manifest에는 분할 hash가 있으며, 화물은 scene별 render catalogue hash와 score 시점 catalogue hash를 서로 다른 위치에 기록한다. 따라서 summary의 한 hash나 `frames_dir` 경로만으로 모든 입력 바이트의 동일성을 입증했다고 쓰면 안 된다.

그러나 이 관찰만으로 지원 관리 경로에 provenance가 없다는 결론은 틀린다.

- `scripts.sim_cli.main`은 `workflow …`를 `sim.workflow_manager.workflow_cli`로 연결한다.
- 원래 `_workflow_inputs`/`_input_paths`는 명시한 `--frames` 디렉터리를 입력으로 잡는다. `path_receipt`는 그 디렉터리의 일반 파일 경로·바이트 수·SHA-256과 집합 digest를 만든다.
- `_base_manifest`는 `inputs_before`를 기록하고 `_finish`는 `inputs_after`, `inputs_changed_during_run`, 출력 receipt와 source 변경 여부를 남긴다.
- 문서도 직접 스크립트 호출은 공통 실행 기록을 자동 생성하지 않는 호환 경로이며, 신규 실험은 표준 관리 진입점으로 연결한다고 구분한다.

이번 fixture에서는 원래 입력 선택/receipt 함수만 작은 임시 render 폴더에 실행했다. 색의 17파일, 화물의 11파일이 입력 receipt에 포함됐고 정상·혼동·빈 응답 재채점 뒤 입력 receipt가 같았다. 실제 `run_workflow` subprocess나 before/after finalizer 전체를 실행한 것은 아니다. 관리 계층의 임의 symlink·동시 수정·파손·네트워크 저장소·원격 백업까지 재검증한 것도 아니다.

관리 계층의 `_reported_outcomes`를 작성한 두 score 출력에 적용하면 빈 사전이다. offline detector summary를 물리 성공으로 승격하는 bool 필드는 없었다. 이 역시 성공 판정의 일반적 부재 증명이 아니라 선택한 두 출력 계약의 확인이다.

## 재현·한계·중복 검토

재현 파일은 `reproduce_offline_envelope.py`, 최종 결과는 `offline-envelope-result-v2.json`이다. `--output`으로 **존재하지 않는 새 경로**를 주면 기존 evidence를 덮어쓰지 않고 실행된다. `offline-envelope-result.json`은 혼동 지표 control을 추가하기 전 checkpoint로 보존했으며, 최종 증거에는 v2를 사용한다.

- exact main에서 선택한 20개 source/docs/test.py의 바이트 수·SHA-256은 `source-manifest.json`에 있다. 20개 파일 전체의 모든 경로를 실행하거나 모든 줄을 심층 감사했다는 뜻은 아니다.
- 원래 parser/render writer/score/summary 함수 본문과 원래 상수를 AST로 불러 썼다. fake world·placement·평가 geometry·static map·detector·cv2·Git identity·clock은 `reproduce_offline_envelope.py`에 공개했다.
- RGB는 `AUTHORED_R28_RGB:` 토큰이다. 가짜 cv2 저장은 PNG 인코딩이 아닌 20×20 NumPy 배열 저장이며, hull은 작성한 직사각형만 다룬다. 이 대역을 실제 RGB 렌더나 OpenCV 검출 검증으로 세지 않는다.
- 원래 두 writer의 정상·잘못된 색·빈 응답 채점을 합쳐 fake detector 입력 경계 호출 108개를 관찰했다. 반복 view를 108개의 독립 실험으로 해석하지 않는다.
- 실제 split JSON·held-out seed 목록·raw/기존 결과·이미지·dataset·weights를 의도적으로 열거나 분석하지 않았다. 관련 test.py의 분할 분리 assertion과 fixture 사용 코드만 읽었고 그 기존 test suite를 실행하지 않았다.
- 실제 renderer·physics·model·training·유료 호출·전체 CI·관리 subprocess·외부 저장을 실행하지 않았다. 구현 파일도 수정하지 않았다.
- R13의 calibration holdout 수정 후 stale metric 승인은 이 CLI의 재채점 경로와 다르다. 여기서는 새 score마다 metric을 다시 계산했다.
- R18의 replay source-filter 누락은 여기서 사용되는 render/score provenance의 승인 절차와 별개다. summary 단독 한계나 관리 receipt가 같은 것처럼 재발견하지 않았다.
- R21 S1/A3 acceptance 또는 teacher TOP hue 조건의 중복 검토로 계수하지 않았다. detector algorithm 전체, Hungarian/global matching 최적성, 실제 seed 독립성은 이번 범위 밖이다.

이번에 새로 닫은 범위는 **현재 등록된 두 오프라인 evaluator에서 정상 writer→score가 어떤 입력·분모·지표 정의로 이어지는가**다. 다음 사용자가 확인할 것은 해당 실행의 manifest와 record를 함께 보존했는지, 비교 표에서 지표 정의를 맞췄는지다. 여기서 현재 HIGH를 막는 새 원인이나 구현 수정 필요를 도출하지 않는다.
