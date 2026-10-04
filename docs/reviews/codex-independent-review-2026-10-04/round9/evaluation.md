# 9차 평가 무결성 검토 — 초기 실패도 고정 SIM cap을 대조해야 한다

**새로 확인한 것은 P06 후보의 조건부 무결성 틈 1건이다.** 고정된 bundle의 horizon과 다른 cap을 `write_outputs`에 넘겨 초기 HOST_ERROR를 기록하면, 심판이 아직 없다는 이유로 bundle cap 대조가 생략된다. 같은 자료가 실제 inspector에서 PAR2 scalar로 재도출되고 cohort에서 `VERIFIED`/`VALID`로 받아들여진다. 실패 분모가 사라지는 오류는 아니며 현재 v100 pilot의 실행 결과가 잘못됐다는 발견도 아니다.

고정 소스는 main **`b23fc0875b72f4b55f399a252a1575b7e8b43cb5`**다. 공식 GitHub main 조회로 현재성을 확인하고, 재현이 직접 의존하는 13개 파일의 로컬 바이트를 해당 Git object 및 스크립트의 SHA-256 guard와 대조했다. 현재 기본 checkout의 이전 `f2577bb`와 해당 코드 바이트는 같다. 구현·설정·기존 기록을 수정하지 않았고, 새 임시 합성 기록만 사용했다.

## R9-E1 — 심판 생성 전 실패에서 고정 horizon 검증이 우회된다

**우선순위: P2, P06 후보의 입력 검증 결함. 현재 pilot blocker로 분류하지 않는다.** 발생 조건은 외부 admission에 담긴 bundle의 cap과 writer의 명시적 `horizon_s` 인자가 서로 다른 경우다. 정상 factory/CLI가 이 불일치를 현재 만들어 낸다는 증거는 없다. 잘못 연결된 향후 caller나 서로 다른 설정원에서 온 cap을 evidence verifier가 거부하지 못하는 경계다.

### 계약과 도달 경로

1. [candidate writer 31–56](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_evidence_writer.py#L31-L56)는 bundle 해시·frozen admission을 대조하지만 `horizon_s`를 bundle의 `horizon_s`와 비교하지 않고 summary에 쓴다. host/trial이 없는 실패에서는 [87–92 및 111–126](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_evidence_writer.py#L87-L126)의 실제 경로가 그 cap으로 incomplete record를 만든다.
2. [저장 검사 138–150](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_evidence_writer.py#L138-L150)는 record와 summary cap만 대조한다. 둘은 같은 인자에서 왔으므로 서로 맞는다. `seal_new_evidence`가 원본 body의 논리 identity·해시를 정상적으로 봉인한다.
3. 실제 inspector의 [export_study 112–154](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/tensorboard_tools/zone_study.py#L112-L154)는 `verify_referee_derivations`에 frozen policy와 admitted bundle을 전달한다. 그런데 [contract 197–204](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_evidence_contract.py#L197-L204)는 명시적 초기 실패·무배송·심판 없음이면 바로 metrics를 반환한다. **bundle horizon 대조는 심판이 있는 경로의 [214–220](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_evidence_contract.py#L214-L220)에만 있다.**
4. 이후 [export_study 173–192](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/tensorboard_tools/zone_study.py#L173-L192)는 manifest terminal·result·record가 같은 cap인지 확인하고 PAR2를 포함한 scalar dictionary를 만든다. 모두 writer의 같은 인자에서 왔으므로 통과한다. [cohort.collect 124–139](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_evidence_cohort.py#L124-L139)는 이 inspector의 결과를 관계 테이블로 받아 source를 `VERIFIED`로 표시한다.

여기서 cap은 실제 종료 시간과 다르다. [efficiency_metrics 980–1005](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/zone_study_eval.py#L980-L1005)는 실패에 `penalty_factor × budget.sim_horizon_s`를 부과한다. [문서의 고정 admission·실패 PAR2 계약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/tensorboard.md#L154-L173)도 실패의 짧은 관찰 종료와 cap을 구분한다. 잘못된 cap을 실패의 빠른 종료로 정당화할 수 없다.

### 재현과 대조

`evaluation-horizon-repro.py`는 새 임시 폴더마다 candidate writer의 실제 `write_outputs → incomplete_record → save_evaluation → seal_new_evidence`를 호출한다. 계획의 bundle cap은 언제나 12초이며, writer 인자만 바꾼다. host/trial/referee는 `None`, failure는 `infra:HOST_ERROR`다. 이어 실제 `inspect_study`와 `cohort.collect`를 호출한다. 저장 후 원본 JSON을 다시 편집하거나 검사 함수를 monkeypatch하지 않았다.

| frozen bundle H | writer 인자 H | inspector PAR2 scalar | source / trial | admitted / successes |
|---:|---:|---:|---|---|
| 12 | 12 | 24 | VERIFIED / VALID | 1 / 0 |
| 12 | 6 | **12** | VERIFIED / VALID | 1 / 0 |
| 12 | 24 | **48** | VERIFIED / VALID | 1 / 0 |

불일치 자료의 올바른 처리는 registered H에 맞춘 성공/실패 점수를 임의로 덮어쓰는 것이 아니라, **불일치를 표시하고 그 자료를 적격 evidence로 받지 않는 것**이다. 실제 적용 cap도 별도로 보존해야 한다. 표의 24는 고정 계획 H12에 대한 실패 벌점이며, 실행 H6 기록에 그 값을 몰래 대입하라는 뜻이 아니다.

추가 음성 대조는 같은 초기 실패 record에 유효한 빈 referee stream과 빈 `departed_unsettled` 관계를 제공한다. H12는 통과하고 H6/H24는 기존 `referee horizon differs from admitted bundle` 검사에서 거부된다. 오류가 JSON 손상이나 일반 horizon 검사의 부재가 아니라 **심판 부재의 조기 반환**에 국한됨을 확인했다.

성공 분모와 실패 분류는 세 경우 모두 보존된다. `cohort.collect`는 이 반례에서 PAR2 코호트 평균을 만들지 않는다. 확인한 물질적 출력은 inspector가 반환한 `result/par_makespan_sim_s`, `result/sim_horizon_s`, source `VERIFIED`, trial `VALID`다. 실제 TensorBoard event 파일이나 공용 대시보드·새 실험은 만들지 않았다.

### 현재 실행과의 경계

[writer 모듈 설명](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/zone_study_evidence_writer.py#L1-L7), [현재 문서 137–140](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/docs/tensorboard.md#L137-L140), [기존 test 421–422](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/tests/test_zone_study_evidence.py#L421-L422)는 P06 writer가 기존 runner와 별도인 후보임을 명시한다. 소스 caller 검색에서도 현재 `run_zone_study_integration.py`는 자체 `write_outputs`를 사용한다. v100 two-arm 가능성 pilot에서 이 결함을 관측했다거나 main-study H1800 벌점이 실제 잘못 집계됐다고 주장하지 않는다.

기존 R7의 “P06이 있는데 실제 runner/본실험 분석 연결은 아직 별도”라는 판단은 바꾸지 않는다. 새 지적은 **이미 있는 후보 verifier를 동일한 frozen plan으로 호출했을 때 초기 실패만 불일치를 허용하는 코드 분기**다. 이전 unknown provenance 표시, partial archive, R8 과거 발화 truthfulness 문제와도 별개다.

### 작은 수정과 수용 기준

- candidate writer에서 `horizon_s`와 admitted bundle horizon을 비교하거나, 별도 실제 cap을 보존하면서 불일치 상태로만 봉인하도록 명시한다.
- reader의 referee 유무와 무관한 bundle/record cap 검사를 early-failure 반환 앞으로 옮긴다. referee absence를 허용하는 초기 실패 예외는 유지한다.
- 정상 H12 초기 HOST_ERROR는 1개 실패로 남고 PAR2=24를 유지한다. H6/H24 불일치는 source/trial INVALID로 기록하며 admission 1은 유지한다. referee-present 불일치 거부도 유지한다.
- current pilot의 모든 기본 horizon을 1800으로 바꾸거나 missing raw를 성공/실패로 새로 덮어쓰지 않는다. 각 실행의 고정 계획 안에서 일치성을 검증한다.

## 재현 파일과 환경

```bash
python evaluation-horizon-repro.py --repo /path/to/UGRP-at-b23fc087 \
  > evaluation-horizon-local-result.json
```

Python 표준 라이브러리와 저장소의 pure Python 평가 모듈을 사용한다. 저장소 소스는 필요하지만 특정 `/workspace` 절대 경로는 필요하지 않다. 스크립트는 stdout만 결과로 쓰고 자신 옆의 보존 JSON을 덮어쓰지 않는다. 기존 evidence/raw를 열지 않으며 임시 synthetic 기록만 읽는다. 네트워크 연결과 MuJoCo/Torch/OpenCV import는 차단한다.

이 환경에는 선택적 camera 의존성 `cv2`가 없어 writer의 top-level runtime import는 실행하지 않았다. 대신 **writer 4개 함수 본문을 변경 없이 AST compile**하고, 선택한 no-host/no-trial 분기의 globals는 실제 pure 모듈 또는 원본 literal 값/`file_sha256` 함수에서 가져왔다. 전체 writer 모듈 import·물리 runner 통합 test 통과로 표현하지 않는다. 실제 seal·inspector·cohort는 원본 함수 그대로다.

- 재현 스크립트 SHA-256: `dc58a21e54f1455b16c49e2380d5f51b86763c84a8a0c7690ccc37bab07a92b1`
- 보존 결과 SHA-256: `16cd2cd96d79a48ecf847f9f226e3c74e5d72bee8015b509272d3d84b5dcc7c2`
- `evaluation-horizon-result.json`에는 source 13개 해시·입력 cap·실제 판정·scalar·음성 대조를 기록했다.

## 함께 확인한 정상 경계와 다음 범위

P06의 `validate_plan`은 논리 trial/run 중복과 retry 분모 확대를 거부한다. `aggregate`는 주문별 relation 누락·중복·unknown orphan을 INVALID로 남기며 admitted 수를 고정한다. `collect`는 invalid source의 선언 소유자를 유지해 다른 파일명으로 실패를 숨기지 않는다. 이 존재하는 방어를 부정하거나 새 finding 수에 합산하지 않았다.

첫 타깃을 마친 뒤에는 별도 분석 경로에서 nested 집계·pairing·자료 회수의 경계를 이어서 검토한다. raw·heldout·outcome을 보지 않는 범위는 유지한다.
