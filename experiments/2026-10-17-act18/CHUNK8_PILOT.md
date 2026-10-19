# ACT 4-world takeover pilot — chunk8 재실행안 (2026-10-19)

상태: **코드 준비 완료, 기본 OFF, GPU 미실행.** 이 문서는 파일럿 재실행
명령과 선택 근거만 고정한다. 물리 성공·성능 주장이 아니며 R8/R100의
TRAIN4 결과와 합산하지 않는다.

## 1. 차단 원인: 8 vs 100은 어디에 있나

- `harness/grasp_act_contract.py:25`의 `CHUNK=8`이 동결 계약이다.
- `harness/grasp_act_policy.py:33`의 `make_policy()`가
  `chunk_size=c.CHUNK, n_action_steps=c.CHUNK`로 모델을 만든다.
- `harness/grasp_act_policy.py:143-145`의 `ChunkExecutor`는
  `n_action_steps`를 `1..c.CHUNK`로 제한하고,
  `:175-176`에서 예측 shape이 `(c.CHUNK, ACTION_DIM)`이 아니면
  `ValueError('invalid action chunk')`를 낸다.
- 파일럿 `scripts/collect_act16w_dagger.py:80`이
  `ChunkExecutor(actor.predict)`를 기본값(`n_action_steps=8`)으로 만든다.
- R100은 `act18_policy.CANDIDATES['R100']=100`으로 만들어져
  `Actor.predict()`가 `(100, 14)`를 반환하고 adapter.json의 `chunk`도
  100이다. 그래서 첫 `executor.step()`에서 위 shape 검사에 걸린다.
- Act18 평가 경로는 이와 다르다. `scripts/act18_evaluate.py:134-135`가
  `contract.CHUNK=meta['chunk']`로 계약 상수를 평가용으로 바꾸고,
  `:166-169`에서 `n_action_steps=1, temporal_ensemble_coeff=.01`을 쓴다.
  즉 R100은 **100개 horizon 전체를 매 tick 재예측·ensemble**하는 조건으로
  평가됐다. 파일럿만 8로 고정돼 있었다.

재현 증거(추적 파일):
`experiments/2026-10-17-act18/protocol.json`의 R100 `chunk:100`,
`configs/model_artifacts.json`의 R100 adapter `chunk:100`,
`experiments/2026-10-17-act18/results/release-r1/public-verification.json`의
R8 `chunk:8` / R100 `chunk:100` 로딩 기록.

## 2. 선택지 비교

| | (a) chunk-aware executor (100→8) | (b) chunk=8 체크포인트 |
|---|---|---|
| 계약 변경 | shape 검사·queue·`n_action_steps` 상한 변경 필요 | 없음 |
| 정책 의미 | **바뀐다.** 100 horizon 중 0..7만 사용. 8틱마다 재예측하면 폐루프 주기가, 매 tick 재예측하면 ensemble horizon이 R100 평가 조건과 달라진다 | 기존 8틱 블록 그대로. R8은 계약 크기라 전송/실행 변경 없음 |
| 재검증 | TRAIN4 + executor/ensemble ablation, R8/R100과 pooling 금지 | artifact SHA·adapter chunk=8 로딩 검증. 파일럿 데이터는 별도 |
| 판정 | **구현하지 않음** | **채택** |

(a)는 "전송 수정"이 아니라 새 제어기다. R100의 100 horizon 중 92개를
버리고, `ChunkExecutor`의 `n_action_steps<=8` 상한 때문에 100틱
open-loop도 불가능하다. 따라서 이 PR은 긴 chunk를 자르는 코드를 넣지
않고, 계약 크기(8)가 아닌 체크포인트를 **거부**한다.

## 3. 후보 체크포인트

| 후보 | chunk | provenance | 판정 |
|---|---:|---|---|
| **act18 R8** | **8** | 100k fp32, v7 TRAIN200, batch8, seed20261017, source `52e486316`, checkpoint sha `e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a`; Release `models-20261017-act18-v7-r1`; TRAIN4 0/4 NOT_READY | **채택** |
| act18 R100 | 100 | 같은 레시피의 matched chunk100, sha `44b11c3c...`; TRAIN4 0/4 NOT_READY | 계약과 불일치, 거부 |
| act16w native 10k | 8 | `experiments/2026-10-16-act16w/resume4/*`, 10,000 step, `act16w` adapter/입력 변환 | 보조 후보. act18 파일럿 lane의 actor/데이터와 달라 이번 비교에 쓰지 않음 |

R8은 R100과 데이터·레시피·100k schedule이 같고 예측 horizon만 8인
가장 가까운 짝이다. 공개 Release에서 익명 재다운로드·전체 SHA·CPU
로딩(`chunk=8`)이 검증됐다. R8 역시 NOT_READY이므로 **제어기 채택이
아니라 파일럿용 student**로만 쓴다.

## 4. 구현

- `scripts/act18_chunk8.py`: 기본 OFF gate.
  - `require_contract_chunk(chunk, enabled=False)`: OFF는 strict no-op.
    ON은 `int` 8만 허용하고 100을 명시적으로 거부.
  - `contract_chunk_rows(...)`: ON에서 정확히 `(8,14)`만 허용. 100행을
    8행으로 자르지 않는다.
  - `contract_chunk_predict(...)`: OFF는 원래 callable을 그대로 반환.
    ON은 8행 호출을 검증하는 wrapper를 반환(8행 호출은 row 동일).
- `scripts/collect_act16w_dagger.py`: `--contract-chunk8` 추가.
  `--takeover-pilot` 전용이며, R8 adapter(`chunk=8`)가 아니면 GPU owner
  시작 전에 실패한다. OFF면 기존 경로와 동일하다.
- `tests/test_act18_chunk8.py`: 6 tests.
  - OFF no-op(identity) / R100 100행은 slice되지 않고 거부 /
    boundary 7·8·9·100 / nonfinite / 8행 wrapper 동일 /
    executor가 8틱마다 1회만 predict / R100은 기존 `invalid action chunk`.

검증: `/home/ubuntu/ugrp-venv/bin/python -m pytest
tests/test_act18_chunk8.py tests/test_act18_policy.py -q` → **9 passed.**

## 5. 4-world 파일럿 재실행 명령

4세계의 토폴로지가 `nbody 162/159/159/162`로 달라 단일 4-world
`combine_models`는 `converted model scalar/topology/options differ`로
실패한다. 그래서 **토폴로지 동질 2세계 × 2그룹**으로 나눈다.

- group-000: seeds `88600 88603` (nbody 162), `case-000` compiled reference.
- group-001: seeds `88601 88602` (nbody 159), `case-001` compiled reference.
  `act16w_native_contact.initialize`가 index 0에 `--compiled-reference`를
  강제하므로 그룹 첫 세계의 case를 써야 한다. 그룹 내 다른 세계는
  `--references`의 exact-XML mapping에서 각자 reference를 찾는다.

공통 변수(새 체크아웃에서):

```bash
cd /home/ugrp/ugrp-sim/src/act-chunk-<COMMIT>   # 이 PR의 clean checkout
export UGRP_ACT16W_NATIVE_GATE=/home/ugrp/ugrp-sim/runs/act16w-native-gate-r2/independent-gate-recount.json
REF=/home/ugrp/ugrp-sim/runs/act17-v7/record-references-r1-owner-regen
T=/home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e
Q=/home/ugrp/ugrp-sim/src/f0db6b1abb842ea65b71c433738210254f300a7c
ACTPY=/home/ugrp/ugrp-rl1b-act-env/bin/python
WARPPY=/home/ugrp/ugrp-sim/runs/simalt3/warp-env/bin/python
ACT=/home/ugrp/ugrp-sim/runs/act18/release-verification-r1/models/act18-v7-r8-step100000-20261017/act
ACTOR_SOURCE=/home/ugrp/ugrp-sim/src/3f99d58c5ada0862e669ef4065c0ba957f1b4547
QUAL=/home/ugrp/ugrp-sim/runs/warp3/teacher-gate-qualification-r1.json
PROTOCOL=$PWD/experiments/2026-10-17-act18/protocol.json
DAGGER_STARTS=$PWD/experiments/2026-10-17-act18/results/open-R100-10k-summary.json
PLANS=/home/ugrp/ugrp-sim/runs/act-takeover-pilot5-embedded-plans.json
```

group-000:

```bash
"$ACTPY" -u scripts/collect_act16w_dagger.py --enabled \
  --takeover --takeover-pilot --contract-chunk8 \
  --takeover-hold-s 2 --takeover-after-s 6 --max-ticks 900 \
  --plan-seeds 88600 88603 \
  --physics-python "$WARPPY" \
  --qualified-source "$Q" --teacher-source "$T" --qualification "$QUAL" \
  --references "$REF/per-world-references.json" \
  --compiled-reference "$REF/case-000/compiled-312.json" \
  --compiled-geometry "$REF/case-000/compiled-geometry312.npz" \
  --plans "$PLANS" --actor-source "$ACTOR_SOURCE" --checkpoint "$ACT" \
  --dagger-starts "$DAGGER_STARTS" --native-protocol "$PROTOCOL" \
  --out /home/ugrp/ugrp-sim/runs/act-takeover-pilot6/group-000
```

group-001:

```bash
"$ACTPY" -u scripts/collect_act16w_dagger.py --enabled \
  --takeover --takeover-pilot --contract-chunk8 \
  --takeover-hold-s 2 --takeover-after-s 6 --max-ticks 900 \
  --plan-seeds 88601 88602 \
  --physics-python "$WARPPY" \
  --qualified-source "$Q" --teacher-source "$T" --qualification "$QUAL" \
  --references "$REF/per-world-references.json" \
  --compiled-reference "$REF/case-001/compiled-312.json" \
  --compiled-geometry "$REF/case-001/compiled-geometry312.npz" \
  --plans "$PLANS" --actor-source "$ACTOR_SOURCE" --checkpoint "$ACT" \
  --dagger-starts "$DAGGER_STARTS" --native-protocol "$PROTOCOL" \
  --out /home/ugrp/ugrp-sim/runs/act-takeover-pilot6/group-001
```

두 그룹은 **순차 실행**한다(같은 L4에서 병렬 실행은 wall/GPU
비결정성을 섞는다). 성공 판정은 `summary.json`의 `HOST_ERROR` 부재와
`takeover_worlds`/`takeover_ticks`이며, 물리 성공이 아니다.

## 6. 재검증 체크리스트

- [ ] `sha256(model.safetensors) == e1ec6592...`이고 adapter `chunk == 8`.
- [ ] `--contract-chunk8`이 켜졌고 `checkpoint_chunk:8`이 summary에 기록됨.
- [ ] group-000/001 각 2세계; 4-world 단일 combine을 쓰지 않음.
- [ ] group-001이 `case-001` compiled reference로 owner 초기화 통과.
- [ ] 첫 30 SIM초의 inputs/commands를 육안 검토(기존 규칙).
- [ ] R8/R100 TRAIN4와 pooling 금지; `NOT_READY` 라벨 유지.
- [ ] R8 open-loop 8틱 실행은 act18 R8 평가(매 tick ensemble .01)와
      다른 조건임을 보고서에 명시.

## 7. 리스크

1. R8은 TRAIN4 0/4 NOT_READY다. 파일럿 데이터 품질이 낮을 수 있다.
2. group-001의 `case-001` reference는 아직 GPU에서 검증되지 않았다.
   geometry/scalar mismatch가 나면 case-001·case-002를 1세계씩
   분리 실행하고 그 사실을 기록한다.
3. 이 PR은 Oracle에서 CPU 테스트만 통과했다. GPU owner·MJWarp 경로는
   재실행 전까지 **미검증**이다.
4. `--dagger-starts`는 admission artifact가 아니라 승인된 대체
   `open-R100-10k-summary.json`이다. Lead 승인 조건을 유지한다.
