# 새 등록용 실행 의존성 계약 v2

**후속 상태 (PR #301 두 번째 검토 뒤):** 정적 분석 보강을 중단하고
[오프라인 실행 관측 추적기와 검사 결과](RUNTIME_PROVENANCE.md),
[native 실행의 후속 설계](../../docs/runtime_provenance.md)로 전환했다.
아래 적용 순서·절감 추정은 최초 제안 당시 기록이다. 정적 v2 단독 도입이나
무관한 catalog 편집 허용을 현재 완료 기능으로 해석하지 않는다.
새 경로의 실제 물리 실행 연결과 독립 재검토는 남아 있다.

후속 재현성 검사는 [301c 답변](REVIEW_RESPONSE_301c.md)과
[301d의 출력 제외·환경 복사 수정](REVIEW_RESPONSE_301d.md)에 기록한다.

기준 main: `d17ca4345affef8cf027e121cf1f3197b36c23e0`.
읽기 전용으로 조사한 #292 HEAD: `3afc61b00f2c127ac3fbe2be5e7bb57da989b15a`.
이 작업은 `codex/seal-dependency-decouple`에서만 수정한다. #292 브랜치·봉인·
정책·물리·과거 기록은 수정하지 않는다. PR은 draft로 제출하고 병합하지 않는다.

## 확인한 결합과 결정

`scripts/zone_pair_v6_contract.py`의 현재 v6e 계약은 이전 grasp/scene 소스 목록을
상속하며 계약 모듈 자체와 `configs/simulation_workflows.json` 전체도 해시로 고정한다.
과거 v6~v6d는 원래 commit blob으로 감사하고, v6e는 현재 tree와 직접 비교한다.
현재 계약 모듈을 수정하면 v6e 자체가 깨지므로 이 파일과 기존 검증기는 건드리지 않는다.
RGB v63의 `harness/rgb_execution_bundle.py`와 JSON 봉인도 그대로 둔다.

#292의 `candidate_contract`는 104개 목록을 AST로 넓혀 268개를 고정한다.
`build_prereg_v6h.py`는 이 계약과 scene 계약을 포함한 DRAFT preview를 만들고,
`verify()`는 현재 tree에서 다시 만든 전체 preview와 비교한다. runtime·자산·분류기뿐
아니라 builder·등록 계획도 같은 목록에 들어 있다. 기존 AST를 깎아 파일 수를 맞추면
리뷰에서 복구한 `scripts/zone_teacher.py`의 ArmSequence 같은 실행 입력을 놓칠 수 있다.

따라서 v2를 새 모듈/API로 추가한다. 새 빌더의 기본값은 v2이며 기존 빌더는 기존
revision을 계속 검증한다. 새 revision은 v2 빌더와 verifier를 명시적으로 연결한다.
등록용 설명/연구 계획은 외부 연구 봉인에, 실행 의존성은 v2 digest에 둔다. 실제 import가
등록 모듈까지 닿으면 해당 Python 파일도 그대로 pin한다. 공용 Python 파일 내부의
일부 함수만 떼어 해시하는 방식은 도입하지 않는다.

## 구현 경계

- `harness/execution_dependency_contract.py`와 `harness/python_source_closure_v2.py`:
  v2 전용 보수적 import 추적, 동적 모듈 선언, 데이터 입력, 순서 보존 JSON 항목 hash,
  외부 승인 digest와 재대조. 기존 AST 구현과 기존 봉인은 바꾸지 않는다.
- `scripts/build_execution_dependency_contract.py`: 새 등록용 v2 build/verify CLI.
  stdout preview 또는 새 파일만 작성하며 승인·실행·등록 번호 발급은 하지 않는다.
- workflow의 `entry`/`runner`와 공통 manager·CLI·session/shell launcher를 필수로
  고정한다. 목록의 배열 번호 대신 `id`로 행을 고르며 선택 행 내부 키 순서도 보존한다.
  전체 카탈로그는 실제 runner의 validator로 검사하므로 유효한 무관 행 편집만 허용한다.
  공용 defaults/interface는 필요한 경우 별도로 선언한다.
- import되는 코드·자산·입력에 바뀐 내용이 있으면 새 digest가 필요하다. 비상수 동적
  import 선언 누락·중복/삭제된 registry 행·자기 digest만 바꿔 누락한 소스는 거부한다.
- Python의 임의 실행/loader를 완전 분석하거나 비선택 분기가 실제로 실행되지 않음을
  증명하지 않는다. 조건부 import도 보수적으로 포함한다. 동적/자료/외부 라이브러리
  입력 선언은 독립 검토 대상이며 환경/실행 SHA 검사는 기존 runner의 책임이다.

## #292 적용 순서와 봉인 전 도입 판단

1. #292 조정자가 이 PR을 받아들이면, `candidate_contract('v6h')`의 새 dependency
   필드에 v2 receipt를 연결한다. 기존 revision의 `contract()`/역사 감사는 변경하지 않는다.
   v6h의 `build_prereg_v6h.py`와 admission이 **같은 스키마**를 선택하게 한다.
2. `scripts/run_pair_stage_probes.py`의 실제 worker, 제어/host/scene, teacher ArmSequence,
   provider/skill, 최종 classifier/analysis 진입점을 선언한다. 지도·보정 fit·배치·
   render profile·contact/PF 기록 설정 등 비 import 입력도 유지한다. 선택하지 않은
   모듈이라는 근거 없이 기존 268개에서 지우지 말고 old/new 경로 차이를 검토한다.
3. workflow `pair-stage-probes`(연결 후 사용되는 항목)와 실제 사용할 통합 workflow,
   provider 등 registry 항목을 고정한다. builder/등록 설명을 실행 closure에서 빼도
   `PREREG_DRAFT`, 판정 정의, 표본과 인수 계획은 연구 봉인에 남긴다. scene 계약의
   실행 소스 hash도 누락하지 않는다. 과거 source_sha256 필드로 v2를 위장하지 않는다.
4. v6h worker admission이 물리 import/출력 생성 전에 외부 등록에 고정한 digest로
   `verify_contract`를 호출하게 한다. 기존 실행 SHA/승인/72 cases/배치/seed/환경/
   contact trace 검사는 그대로 유지한다. whole-catalog 체크가 남아 있으면 그 새
   revision 경로에서만 v2 entry 체크로 바꾸되 전체 catalog 유효성 검사는 유지한다.
5. #292의 기존 309개 관련 검사와 추가 registry 변조 검사를 수행하고, 최종 classifier
   독립 검토·5건 실제 인수 재생을 별도로 완료한 뒤 조정자가 봉인한다. 이 PR의 오프라인
   pass는 #292 인수 통과나 제어기 성공을 뜻하지 않는다.

**판단:** #292는 아직 미봉인이므로 적용할 시점으로는 적절하다. 다만 268개 대부분이
실제 전이 의존성일 수 있어 축소 폭을 약속할 수 없다. 단순히 빌더만 교체하면 기존
admission의 whole-file 비교가 남는다. 위 연결·독립 검토가 classifier/인수의 일정과
함께 끝날 때 도입할 가치가 있으며, 이 작업을 핑계로 이미 필요한 안전 검토를 생략하거나
확정된 인수 일정을 미룰 근거는 없다. #292 브랜치에는 이 작업에서 어떤 수정도 하지 않았다.

## 예상 절감 — 측정값과 구분

[측정 보고서](../2026-09-30-process-review/MEASUREMENTS.md)의 pin 수는
v6c/d/e **77/80/85**, v6h **104→268**이다. 뒤 증가는 누락 보완이므로 되돌리지 않는다.
workflow 전체 파일 1개를 entry pin으로 대체할 때 **전체 파일 pin의 최소 감소 추정**은
각각 1/77=1.30%, 1/80=1.25%, 1/85=1.18%, 1/268=0.37%다. 이는 전체 의존성 수나
해시 계산 시간의 감소가 아니다(선택 항목 hash와 verifier 소스가 추가되고 다른
전이 의존성이 발견될 수 있다). 완전한 #292 v2 manifest의 파일 수는 아직 측정하지 않았다.

**효과 추정:** 입력 경계가 맞게 연결된 v2 등록에서는, 사용하지 않는 workflow 추가만
있는 변경 1건당 실행 의존성 재봉인·소스 재검토가 1회에서 0회로 줄어든다. 연구 등록
내용이나 실행 의미의 변경 검토는 계속 필요하다. #256의 **270.9분** 보류 중 무관한
카탈로그 결합 몫은 계측되지 않았고 runner 변경도 포함되어 전체 절감을 주장할 수 없다.
가령 그 구간의 10–25%가 이런 재작업이었다고 **가정하는 계획용 추정**은 27.1–67.7분
절감이다. 실제 절감 관측값이 아니며 0분도 가능하다. 후속 등록에서 변경 원인·시작/종료·
dependency digest가 같은지 기록해야 이 추정을 검증할 수 있다.

## 검증과 보존

최초 검증 결과는 [VALIDATION.md](VALIDATION.md), 독립 검토 6건의 수정과 재검증은
[REVIEW_RESPONSE_301.md](REVIEW_RESPONSE_301.md)에 남긴다. 새 테스트는 기존 CI 목록에
추가한다. 새 물리·학습·모델/연구 평가 실행이 없으므로 TensorBoard 변환·서버 시작을
하지 않는다. 프로젝트 예외에 따라 Google Drive는 사용하지 않는다. Git에 남기는
문서와 코드/테스트 결과만 있으며 raw 실험 증거를 삭제하거나 덮어쓰지 않는다.

## 참고 자료

- [프로세스 측정 #296](https://github.com/kcm0127-dotcom/ugrp/pull/296), [측정 원문](../2026-09-30-process-review/MEASUREMENTS.md).
- [절차 제안 #295](https://github.com/kcm0127-dotcom/ugrp/pull/295), `origin/codex/process-research:experiments/2026-09-30-process-review/LITERATURE.md` 4.3절: content addressing, 선언된 입력, 짧은 후보 등록, AST 한계.
- [미봉인 등록 #292](https://github.com/kcm0127-dotcom/ugrp/pull/292), 위에 고정한 HEAD의 `scripts/zone_pair_v6_contract.py`, `experiments/2026-09-30-pair-v6h-carry/build_prereg_v6h.py`.
- [실행 버전 관리](../../docs/execution_versioning.md), [v2 구현](../../harness/execution_dependency_contract.py), [기존 AST](../../harness/python_source_closure.py).
