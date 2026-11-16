# v6h 초안 후속 갱신·검증 기록 (2026-09-30, Codex)

작업 기준은 `codex/v6h-prereg-update`, base `claude/b-v6h-gain`(PR #285), 시작 HEAD **`af2afb5b657a81fa88459778afb2cdac35a9aab5`**다. PR #290의 분류기와 완료된 axial lag probe 보고서가 이 base에 있다. 변경은 `experiments/2026-09-30-pair-v6h-carry/`에 한정했다. 하네스·기존 물리 raw·기존 배치·봉인 파일·기본 체크아웃은 수정하지 않았다.

## 변경과 근거

- `PREREG_DRAFT.md` / `REGISTRATION_PLAN.md`: b-v6h1의 다섯 변경군에 `carry_axial_lag=True` 및 gain 보정 필수 조건을 반영했다. gain README의 **29/29 배치·58/58 케이스**, OFF **3/7·11/12·7/10**, 접촉·하드 위반 0은 기존 probe 보고서를 인용한 값이다. 이번 작업의 물리 결과가 아니며 독립 검토는 미완료다. 29/29의 Wilson 하한 **0.883026406**은 수식으로 다시 계산했다.
- 수치 설계: `cohort_sizing.py`가 PR #286의 모형을 그대로 사용한다. 68건/34배치의 끝점만 저장 기록에서 다시 읽어 기존 적합 계수·잔차 sd와 **1e-10 이내**로 일치했다. 플랜트 재적합은 없었다. 모형별 3,000회 계산은 한 스레드에서 CPU **0.95초**, 재현 검사는 **0.89초**였다(공유 Mac의 성능 비교가 아니라 이 작업의 계산량 기록).
- 현재 60곳의 조건부 기대 통과 수: ON **59.741**, 옆 오차 ×1.5 **55.487**, ×2 **47.205**. 정확 이항 p=0.88 민감도에서 P(≥48)=**0.976072**, P(≥55)=**0.258970**. 기본은 ≥48/60 관측 기준을 유지했다. 모집단 주장·검정력 90%·참 p=0.88·양측 정확 95% 하한>0.80을 원하면 최소 **N=225, ≥192/225**이며 정확 검정력 **0.905981**이다. p=0.85라면 N=619. 세부 값·분포 전제·해시는 [`sizing_20260930/COHORT_SIZING.md`](sizing_20260930/COHORT_SIZING.md), `cohort_sizing.json`, `training_inputs.json`에 있다.
- 분류기의 11개 해석을 초안 §5.1에 같은 순서로 권장안으로 옮겼다. **일반 setdown 관문(6), teacher 준비/실행 기록 경계(7)**는 OPEN QUESTION FOR COORDINATOR다. 분류기 코드를 바꾸거나 정의를 봉인하지 않았다.
- 현재 60개 배치가 새 ON probe 29개 구성과 근접 중복 **0건**임을 확인했다. 배치 파일 SHA-256은 **`bb8044058377d86efc658ce3a7458c8afc141680acfd98542260e0efda018454`**로 그대로다. `placement_freshness.json`에 시작 구성과 원본 해시를 기록했다.
- `acceptance_replay_DRAFT.json`에 lag ON **5케이스, 시드 911**의 실제 case id·소스 SHA·명령 원본 전체 해시를 기록했다. OFF sB/cA를 ON의 바이트 동일 기준으로 쓰지 않으며, 새 등록 소스의 **commands.json 바이트 및 sha256 일치**를 필수로 했다. 골든 기록은 재생 통과가 아니다.
- p2f **0/208**의 정지 감지 한계를 유지하고 D1 밝기 기반 검출기(PR #291)가 별도 탐색 제안이며 b-v6h1에 포함되지 않는다고 적었다. 성공을 safe stall handling으로 보고할 수 없다.

## 수행한 검사

기존 환경 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 재사용했다(Python 3.12.13, NumPy 2.5.2). 모든 검사에 `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`을 적용했고 pytest는 `PYTHONPATH=.` 및 `-p no:cacheprovider`를 사용했다. 물리 잠금은 다른 작업이 보유하고 있어 아래 저장 기록·수식/정적 검사만 직접 실행했다. worker·물리 step·모델 호출은 없다.

```sh
python -m pytest -q -p no:cacheprovider tests/test_v6h_classify_placements.py
# 35 passed in 0.42s
python -m pytest -q -p no:cacheprovider tests/test_b_v6h_gain.py \
  -k 'confirmatory_placement_draft or registered_sources_are_untouched'
# 2 passed, 18 deselected in 0.45s
python experiments/2026-09-30-pair-v6h-carry/analysis/cohort_sizing.py --check
# CHECK PASS: saved output identical; CPU 0.89s
python experiments/2026-09-30-pair-v6h-carry/make_confirmatory_placements.py --check
# exit 0
git diff --check
# exit 0
```

수치 검사에서 이항 recurrence와 직접 조합 합을 n=60, 두 문턱(48/55) 및 54의 반례에서 대조해 차이 **<1e-12**를 확인했다. N 전수 검색은 모든 더 작은 N의 최대 검정력도 기록한다. 짝지은 횡 오차 배율의 통과 수가 단조 감소함을 확인했다. 추가 문서/입력 대조는 §5.1의 연속된 번호 1–11, OPEN 6/7, 다섯 플래그, 문서의 기대 통과 수·두 꼬리 확률과 JSON 일치, HEAD 대비 배치 바이트 보존, 29개 case 해시 및 5개 commands 해시를 확인했다.

## 미검증과 남은 결정

새 물리·시뮬레이션·모델 호출·봉인·등록·인수 재생·병합은 수행하지 않았다. 독립 검토, 정의 6/7, 모집단 주장 추가/표본 수와 전제, 기존 σ 범위/과보수 진단 등의 봉인 전 검토가 남는다. 전체 CI는 로컬에서 실행하지 않았으며 원격 결과는 PR에서 별도 확인해야 한다.

이번 산출물은 기존 결과를 이용한 초안 수치 설계이며 새 실험 결과가 아니다. 기존 raw·TensorBoard 스냅샷은 보존했고 새 변환·서버·브라우저 개방은 하지 않았다. 기존 물리 결과의 보기는 기본 `outputs/tensorboard-view.json`의 `b_v6h_axial_lag_20260930` 키(77 runs, 확인 범위는 gain README의 기존 기록)다. 이번 작업에서 화면을 다시 검증하지 않았다. raw는 로컬 보관이며 원격 백업이 아니다.

## 참고 자료

- [gain README 물리 확인](../../2026-09-30-b-v6h-gain/README.md), `results/axial_lag_physical_check.{txt,json}`, `results/{tS,tR,tX1,tX1b,tX0,sB,rB}.{txt,json}`.
- [PR #286 예측 모형](../../2026-09-30-l1-axial-offset/analysis/predict_pass.py), `plant_model.py`, `results/predict_pass.json`, `results/raw_manifest.json`.
- [분류 정의 11개](CLASSIFY_NOTES.md), [분류기](classify_placements.py), [이전 분류 검증](VALIDATION.md).
- [PR #285 조정자 결정과 병행 구현 범위](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/285), [PR #291 별도 정지 검출 연구](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/291). 조정자의 포함 결정은 작업 지시와 #285 등록 구현 코멘트에서 확인했으며, #291 설명은 `gh pr view 291`로 읽었다.
