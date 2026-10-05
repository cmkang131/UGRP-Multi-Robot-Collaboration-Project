# R9-E2 — 완료를 선언한 phase의 회수 실패가 전체 회수 완료로 바뀐다

**P2 · 선택적 Colab/Jev 회수 경로.** 원격이 5개 phase에서 각각 1개 시행 완료를 선언했는데, 한 phase의 checkpoint 목록이 `FileNotFoundError`이면 collector는 그 phase를 건너뛴다. 그 결과 **계획 5개가 로컬 계산에서 4개로 줄어 4개만 회수하고도 `cohort_complete=True`, `collection_complete=True`, exit 0**가 된다. 이 flag를 실제 controller가 읽으면 deadline 전에 런타임 stop을 허용하는 조건도 충족한다.

고정 소스는 main **`b23fc0875b72f4b55f399a252a1575b7e8b43cb5`**다. 실제 Colab·모델·물리 실행이나 stop은 하지 않았다. 새 synthetic checkpoint만 사용했고, 현재 로컬 v100 pilot·main-study PAR2 분석에 이 경로가 연결돼 있다는 주장은 하지 않는다. 실제 raw 손실이나 과거 발생 빈도도 확인하지 않았다.

## 실제 생산자와 소비자

[run_frozen_skill_resume 51–85](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/run_frozen_skill_resume.py#L51-L85)는 development/holdout/regression/ablation/continuous를 처리하고 `exports[phase]`에 `new_completed`, `new_planned`, `previous_completed`를 기록한다. `complete=True` 자체는 `finally`에서 쓰이므로 실행의 종료이지 전부 성공이라는 뜻은 아니다. 이번 반례는 그 사실에 기대어 성공을 조작하지 않는다. **각 phase의 `new_completed=1`, `new_planned=1`, stop/error 없음이라는 명시적 완료 선언**과 회수한 수를 대조한다.

[collect_colab_cohort 38–46](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/collect_colab_cohort.py#L38-L46)는 remote exports와 현재 phase에서 회수 대상 목록을 만들지만, checkpoint directory 목록이 없으면 protocol 다운로드 전에 `continue`한다. 따라서 그 phase의 계획 파일도 로컬에 없다.

이후 [63–70](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/collect_colab_cohort.py#L63-L70)은 **로컬에 존재하는 protocol만** 합해 `planned_trials`를 만든다. remote의 `new_completed/new_planned`는 이 계산에 사용하지 않는다. `len(phases)==5`는 원격 이름의 수이고 계획 합계는 회수한 4개 파일의 합이므로, 둘의 서로 다른 분모가 만나 전체 완료로 오인된다. `collection_complete=True`는 이 수 비교의 성공 여부와 무관하게 설정된다.

다운로드된 ZIP 자체의 바이트·내부 파일 해시는 [verify_checkpoint 53–77](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/cloud_collection.py#L53-L77)가 검증한다. 새 문제는 그 검사를 통과한 4개 ZIP의 무결성이 아니라, **조회하지 못한 다섯 번째 집합을 완료 판정에서 제거하는 것**이다.

## 재현과 음성 대조

`evaluation-collection-repro.py`는 실제 `checkpoint_trial`로 각 phase의 작은 JSON/text checkpoint를 새 임시 폴더에 만든다. 다섯 시행은 모두 `success=False`인 완료 실패라 실패 자료가 보존되는지도 확인한다. 실제 `collector.main`, `verify_checkpoint`, `cleanup_ready`를 실행하고 원격 contents/credentials 경계만 fake로 대체한다. 실제 외부 API나 runtime controller 실행은 없다.

| 입력 조건 | 원격 완료 선언 | 로컬 계획 / 검증 회수 | collection complete | cohort complete | deadline 이전 cleanup 허용 |
|---|---:|---:|---|---|---|
| 모든 checkpoint 사용 가능 | 5 | 5 / 5 | true | true | true |
| **선언된 한 phase의 목록 FileNotFound** | 5 | **4 / 4** | **true** | **true** | **true** |
| 선언된 한 phase의 목록이 빈 배열 | 5 | 5 / 4 | **true** | false | **true** |
| 내려받은 archive 바이트 손상 | 5 | 미완료 / 0 | false | false | false |
| development만 완료 후 중단 선언, 그것만 회수 | 1 | 1 / 1 | true | false | true |

마지막 행은 범위 대조다. 아직 요청하지 않거나 원격이 완료를 선언하지 않은 phase까지 모두 조회하라는 요구가 아니다. 실제로 처리한 phase 하나가 전부 회수됐다면 collection complete는 가능하고, 전체 5-phase cohort는 incomplete로 남는다. 첫 네 행의 fixture가 쓰는 `holdout` 문자열은 실제 결과 분할 이름을 흉내 낸 식별자일 뿐이며, 저장소 heldout 측정자료를 읽지 않는다.

FileNotFound 조건에서는 해당 phase 목록 조회가 **1번**뿐이고 collector가 바로 exit 0 한다. 따라서 같은 클라이언트가 다음 조회에 회복될 수 있어도 이 실행에서는 재조회하지 않는다. archive 손상 대조는 `checkpoint_integrity_failed`와 exit 1로 거부돼 기존 개별 archive 검증이 작동함을 보여 준다.

## 실제 영향의 경계

[resume controller 97–118](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/resume_colab_comparison.py#L97-L118)는 collector의 `collection_complete`와 `remote.complete`를 읽어 [cleanup_ready](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/colab_job_lifecycle.py#L1-L6)에 전달한다. 이 predicate는 deadline이 아니어도 두 값이 true이면 cleanup을 허용한다. controller [125–137](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/resume_colab_comparison.py#L125-L137)은 소유 session/endpoint가 일치하면 `colab stop`을 호출한다.

재현이 직접 확인한 것은 **잘못된 상태 flag·exit code 및 stop 허용 predicate**다. 실제 stop이나 데이터 삭제를 실행하지 않았다. Colab stop 이후 자료 수명의 구체적 보장도 검증하지 않았으므로 “실제로 raw가 삭제된다” 또는 “과거 회수 자료가 유실됐다”고 쓰지 않는다. 다만 unretrieved 자료가 있음을 아는데도 controller가 `collected`로 끝내고 유한 회수 기회를 일찍 종료할 수 있는 연결은 소스에서 확인된다.

[LiveContentsClient 41–56](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/colab_live_contents.py#L41-L56)는 특정 오류에서 같은 runtime의 credential을 갱신하고 다시 호출한다. 이번 재현은 그 이후 collector까지 `FileNotFoundError`가 전달된 조건을 검증한다. 모든 HTTP 401/403/404가 항상 그 exception으로 변환된다고 주장하지 않는다. 실제 네트워크 계층에서의 빈도는 확인하지 않았다. 기존 [collector recovery test 64–91](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/tests/test_colab_recovery.py#L64-L91)는 목록 부재에도 collection complete를 허용하는 기대값이 있으나, 완료 시행 수를 명시한 phase의 자료가 덜 회수된 반례는 검사하지 않는다.

## 최소 수정과 수용 기준

- 계획과 기대 checkpoint 집합을 디렉터리 목록 성공 여부에서 추론하지 않는다. 회수 대상 phase의 protocol을 별도로 확보하고 remote 완료 선언·알려진 checkpoint ID와 실제 검증 완료 ID를 대조한다.
- 선언된 완료 자료가 부족하면 `collection_complete=False`와 구체적 missing phase/trial을 남긴다. 일시적 조회 실패는 현재 유한 deadline 안에서 재시도하고, deadline 종료 시 incomplete로 남긴다.
- `cohort_complete`는 각 phase의 고정 계획과 실행 상태를 대조한다. 로컬에 내려온 protocol 수만으로 계획 수를 축소하지 않는다.
- “원격 실행 종료”, “회수 완료”, “연구 cohort 완료”를 구분한다. 실행 실패가 있더라도 회수할 자료가 모두 확보되면 회수 완료는 가능하며, 반대로 cohort incomplete만 적었다고 회수 완료를 true로 만들어서는 안 된다.
- 정상 5/5, 중단 후 선언된 1/1 회수, archive 손상 거부를 유지한다. 누락 4/5는 회수 완료 및 deadline 이전 cleanup 허용이 false여야 한다. 결과/원본을 다시 실행하거나 삭제하는 수정을 요구하지 않는다.

## 재현과 무결성

```bash
python evaluation-collection-repro.py --repo /path/to/UGRP-at-b23fc087 \
  > evaluation-collection-local-result.json
```

Python 표준 라이브러리만 사용하며 스크립트의 source 6개 SHA-256 guard를 먼저 확인한다. 이 6개 해시를 pinned Git object와 독립 대조했다. 전체 저장소가 필요하고 자체적인 source 번들은 아니다. 출력은 stdout이며 보존 JSON을 덮어쓰지 않는다.

- `evaluation-collection-repro.py`: SHA-256 `6512557d3250ff8d1fa2c1f7bcdab9b3478004daeba713b83d11316920c9a16b`
- `evaluation-collection-result.json`: SHA-256 `60e9fa57cc354980a902d7632e507f88c75a4eadc826835f7782a4968afeb92a`

이는 기존 `pack_frames`의 부분 삭제 후 archive 축소와 별개의 오류다. 이번 경로는 archive를 다시 쓰는 것이 아니라 **수집할 집합의 누락을 완료로 선언**한다. 대규모 물리·학습 실행이나 실제 cloud 회수를 새로 수행할 필요 없이 위 작은 fixture로 수정 경계를 검사할 수 있다.
