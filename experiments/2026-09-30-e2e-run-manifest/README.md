# P07 실행 없는 E2E 계획과 증거 관문

**DRAFT / 미봉인 / 실행 승인 없음.** 이 작업은 READINESS §4의 계획을 검토 가능한
JSON과 읽기 전용 admission 검사로 옮긴다. 실행기·제어기·기존 사전 등록을 바꾸지
않으며 `execute`, 봉인, 모델 호출, 예산 DB 생성 기능이 없다.

감사 기준은 `a8094cc14e098a55483f53a3c49bf6a0b116043d`, 배정된 작업 브랜치의
시작 main은 `d17ca4345affef8cf027e121cf1f3197b36c23e0`이다.
`planning_base_sha`는 이 역사적 기준이고 **실행 source SHA가 아니다**.
현재 읽은 runtime 소스·설정·지도·시나리오·근거 파일은 각각 SHA-256으로 기록한다.
생성 뒤 파일이 바뀌면 초안 검사는 실패한다. 최종 합성 SHA는 코디네이터가 별도로 고정한다.

## 파일과 사용법

- [계획/admission](../../harness/zone_e2e_manifest.py): AST로 runtime 의존성을 읽고
  실행 없이 해시와 순서를 만든다. 물리/worker/모델 모듈을 import하지 않는다.
- [CLI](../../scripts/plan_zone_e2e.py): `draft`와 `dry-run` 두 명령만 제공한다.
- [claim 근거표](../../configs/zone_e2e_plan/claims_v1.json): S01–S15와 #292 인수,
  #293 확증, M1/M2 최종 검증, C5a/C5b/C6/C7을 각각 연결한다.
- [검사](../../tests/test_zone_e2e_manifest.py): 분모·출처·enum·필수값·거짓 완료·충돌과
  World/worker/network/process/DB/write sentinel 반례를 다룬다.

```sh
# 새 검토 파일 1개만 생성한다. 부모 디렉터리는 이미 있어야 한다.
python3 scripts/plan_zone_e2e.py draft --plan-id p07-review-NEW \
  --output /tmp/p07-review-NEW.json

# 아무 파일/폴더/DB도 만들지 않고 JSON 요약을 stdout에 출력한다.
python3 scripts/plan_zone_e2e.py dry-run /tmp/p07-review-NEW.json
```

종료 코드 **3**은 문법/해시/계획 검사는 통과했지만 실행 관문이 남은 정상 DRAFT다.
종료 코드 **2**는 파일/필수값/출처/지도/claim/enum/경로가 잘못되어 거절한 경우다.
이 버전에는 실행 준비 완료를 반환하는 경로가 없다. CI 테스트 성공도 실행 승인이 아니다.
승인·봉인 칸을 채우거나 `physical_ready:true`, `completed:true`로 바꾸면 재해시해도 거절한다.
제안을 바꾸려면 코드/명세를 검토한 새 버전에서 초안을 다시 생성한다.

`draft_content_sha256`은 **초안 내용 식별값**이며 `bundle_sha256`과 다르다.
실행 source/번들 번호/등록 시각/실행 승인/비용 승인은 모두 null이다.
`--render-profile`, `--memory`, `--ultrasonic-front`는 알려진 enum만 받고 초안 해시를
바꾼다. ON/다른 렌더 프로필은 네 조건 공통이며 별도 코호트다. 지원 검증을 생략하지 않는다.

## 분모·순서·제안 상한

| 단계 | 제안 | SIM cap | claim 경계 |
|---|---|---:|---|
| C0 | 합성·검토·최종 구성 선택 | 0 | 정적/가짜 검사만 |
| C1 | reset 3×30 + 실제 출발 3×300 + 실패 2×60 | 1,110 | 단축 연결 |
| C2 | 등록 인수 5×180 + 문 연쇄 3×300 + 목적지 leg 3×60 | 1,980 | 처음부터 전체 E2E 아님 |
| C3 | D1 정체 30×120 + 정상 60×120 + 중단 흐름 3×120 | 11,160 | #293 최종 사전 등록 뒤 재산정 |
| C4 | 최종 M1/M2 각각 새6×900 | 10,800 | 같은 최종 후보, 실패·미도달 포함 |
| C5a | cyan1+봉1, 고정 r1/r2 pair+r3 solo, fixture 4조건 | 7,200 | 작은 개발 연결만 |
| C5b | C5a 구성으로 실제 다회 한국어 4조건 | 7,200 | 작은 한국어 파일럿만, 최대360호출 제안 |
| C6 | 정식6시나리오×새 smoke seed1×4조건, no-LLM24회 | 43,200 | #224 정식 smoke만 |
| C7 | 정식6시나리오×3seed×4조건, 실제 LLM72회 | 129,600 | #254 외부 파일럿; 확증 H1–H3에서 제외 |

C1–C5b 합계 **39,450 SIM초**, C6/C7까지 **212,250 SIM초**다.
시나리오 축소 24회 파일럿은 이 버전에 넣지 않았다. 작은 개발 4/4회, 정식24회,
외부72회는 분모를 합산하거나 대체할 수 없다. 성공률·wall 시간 추정은 하지 않는다.
기능 확장·수정 후 재실행·새 보정/학습 비용은 포함하지 않았다. S15 staging audit가
별도로 필요하면 60초가 추가되지만 학생 E2E 분모에는 넣지 않는다.

순서는 고정 난수 seed `20260928 + cohort_index`로 블록과 블록 내 네 조건을 섞는다.
leader는 `robots[seed % 3]`다. C6은 r1/r2/r3 각2회, C7은 각6회다.
C5a/b는 같은 seed17001이므로 각각 r1 한 번뿐이며 leader 균형 주장이 없다.
C5a/b의 제안 지도는 `zone_wide_door_geometry_v3`다. P02의 기존 v2 개발 명세는
참고 계약으로만 쓰고 최종 v3 혼합 시나리오는 새 버전으로 합성해야 한다.
C6 제안 seed17100–17105는 아직 기존 시나리오에 등록되지 않았다. **원본 v2를
고치지 않고 새 버전에서 등록해야 한다.** C7은 #254의 기존601–653, 시나리오별3개를 쓴다.

dry-run 출력은 순서·총 cap·leader 분포·raw 목적 경로·미충족 관문 다섯 항목뿐이다.
raw는 기본 체크아웃 `outputs/<plan_id>/...`의 새 경로를 계획하며 생성/예약하지 않는다.
기존 빈 디렉터리·raw·파일·dangling symlink도 거절한다. 동시에 같은 이름을 계획하는
경쟁을 잠그는 도구가 아니므로 실행 직전에 코디네이터가 충돌을 다시 검사해야 한다.

## 지원과 해시 경계

로봇 v3, walls_v3/tag0, 렌더/카메라, provider/분할 모델, 보정, 기억, 센서 OFF/ON,
pair 정책/역할/상태 채널, 지도/시나리오/seed, contact/weld, 실효 인식 지연,
LLM/발화/호출/예산, 생각·발화 SIM 비용, 평가 profile을 초안 해시 입력에 넣는다.
실효 인식 지연은 wrapper0.16 + worker0 = **0.16 SIM초**이며 현재 host 프레임은0.2초다.
지연과 프레임 주기는 다른 필드다. 모델 해시는 worker가 선언한 자산 해시이며 이 작업은
가중치 로딩·성능/Release 검증을 수행하지 않는다. GT/TOP/접촉/성공은 평가 전용이다.

P01/P03 계약이 없거나 지원 조합을 확인하지 못하면 **차단**한다. 현재 시작 main의
provider allow-list는 문1개 geometry-v2이고, 최종 로봇v3 보정은 선택하지 않았다.
P01은 `configs/zone_final_environment_registry_v1.json`의 공개된 v1 스키마를
읽으며 파일이 없으면 `unavailable`이다. P03은 기존
`configs/zone_study_integration/pose_providers.json`을 읽는다. 새 계약 파일명을
추측하지 않는다. P01 catalog/보정 hash와 P03 source/보정을 pin하고 지도별 불일치를
남긴다. 두 등록부의 기존 생성 계약만으로 최종 v3/render/model/camera 조합을
허용하지 않는다. 지원 목록/새 계약 합성은 코디네이터의 후속 검토 항목이다.
`pending_p03_final_v3`는 알려진 미해결 표지이며 runtime 기본값으로 해석하지 않는다.
P02의 작은 혼합 명세도 별도 합성이 필요하다. v2/태그/밝은 바닥/정지 프레임의 옛 성공을
최종 v3/tag0 실행에 승계하지 않는다. 지원하는 선택지가 없는 상태를 숨기려고 허용 목록을
넓히거나 공용 registry를 변경하지 않는다.

## 반드시 남는 증거 관문

모든 claim에는 기존 소스·검사·결과 문서·그 결과의 조건·미측정 목록·빈 실행 승인과
`completed:false`가 있다. 결과 링크는 역사적 근거이며 현재 코호트의 완료 증거가 아니다.

- **#292 인수:** seed911 tS/S01·S07, tR/hR2_04, tX1/X01, tX1b/X06의 명령 bytes/hash,
  leg 결과, 전체 연쇄 접촉/하드 판정이 같아야 한다. classifier/정의 pin, 일반 setdown와
  teacher 준비 경계, 독립 검토도 필요하다. 원본 해시 확인과 단위 검사는 인수 통과가 아니다.
- **#293 D1:** 새30정체+60정상, 시작부터 막힌6건을 제외하지 않는 분모, 주 설정의 수용
  기준, staging 성립, 검출 지연/오경보와 실제 중단 흐름이 필요하다. 보조 설정이나
  NumPy 합성 검사로 확증 통과를 대신할 수 없다.
- **M1/M2:** 최종 v3/tag0/보정/정책 후보에서 각각 새6회 전체 임무가 필요하다.
  M1≥5/6·거짓 성공0, M2의 최종 수용 문턱 별도 고정과 checkpoint 상태 연속성을 확인한다.
- **C6/C7:** P09의 비청록 물건·heavy_crate·can/tile·역할 재배정·회전/순서·숨은 사건
  지원을 먼저 검증한다. cyan+봉 개발 연결로 기존6종 완료를 표시할 수 없다.

## 코디네이터 인계

1. P01–P06/P09, #292/#293 최신 변경을 합성하고 독립 검토한다. 최종 로봇/지도/보정/
   렌더/가중치/기억/센서와 실패 판정을 확정한다. 모델 변경 시 옛 근거를 승계하지 않는다.
2. main과 열린 PR의 최댓값 다음 새 bundle/workflow 번호를 예약한다.
   **v83/2.16.0는 #292 소유**다. 이 작업은 어떤 새 번호도 예약하지 않았다.
3. 승인·최종 source/해시를 새 봉인 파일로 별도 커밋한다. 이 초안의 승인 칸을 채워
   실행 파일로 재사용하지 않는다. 실제 모델/실효 모델/토큰 상한/비용 승인 뒤 새 DB를 만든다.
4. 자기 worktree에서 소유 잠금·10 GiB 여유·부하·raw 경로 충돌을 재확인하고 표준
   `sim_cli` workflow로 유한하게 실행한다. 다른 작업 프로세스를 중단하지 않는다.
5. 실패·미도달·HOST_ERROR/ENOSPC·미상 사용량도 분모/비용에 보존한다. 완료 후 원본/
   요청/원장/평가 해시, TensorBoard event/영상/pin/HParams를 확인한다.

이번 작업은 새 물리/학습/평가 코호트를 만들지 않아 TensorBoard 변환·서버/화면 기동을
하지 않는다. raw·기존 snapshot·모델·봉인 bytes를 보존한다. UGRP 규칙상 Drive 작업은 없다.
병합과 봉인은 코디네이터 작업이며 이 PR은 draft로 남긴다.

생성물은 시작 SHA의 referee v2를 명시한다. P06 #303의 referee v3 또는 P01/P03 등
소스가 합쳐지면 기존 JSON 검사에 실패해야 정상이며, 최종 명세를 검토하고 다시 생성한다.
#292의 기록된 head도 감사 당시 참고값이다. 이후 `3c4fe30e` 인수 실행/결과는 이
작업의 검증으로 합산하지 않고 코디네이터가 별도로 대조한다.

## 참고 자료

- [READINESS §4](https://github.com/kcm0127-dotcom/ugrp/blob/codex/e2e-readiness/experiments/2026-09-30-e2e-readiness/READINESS.md#4-가장-짧은-실행-순서와-예산)
- [#254 본연구 초안](../2026-09-28-main-study-prereg-draft/PREREG_DRAFT.md)
- [#285](https://github.com/kcm0127-dotcom/ugrp/pull/285),
  [#292](https://github.com/kcm0127-dotcom/ugrp/pull/292),
  [#293](https://github.com/kcm0127-dotcom/ugrp/pull/293),
  [#294: #285 feature 병합](https://github.com/kcm0127-dotcom/ugrp/pull/294)
- [실행 버전](../../docs/execution_versioning.md), [공용 pytest 보호](../../CONTRIBUTING.md)
