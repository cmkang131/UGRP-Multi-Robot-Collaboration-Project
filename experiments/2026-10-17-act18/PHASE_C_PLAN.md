# Phase C co-training 계획 (실행 전 설계, Lead 보고용)

2026-10-18. **실행 없음.** B2 TRAIN4 4/4 통과 시 자동 진행 트랙. 근거: act-plus-plus `load_data`(다중 dataset_dir + sample_weights), Mobile ALOHA arXiv 2401.02117 co-training.

## 데이터 (gcp2 디스크 확인)

| 데이터 | 경로 | 규모 | 형식 |
|---|---|---|---|
| v7 근거리(현행) | `runs/act17-v7/dataset-r1` | 240 eps(TRAIN200/VAL40), 72,572행 | `ugrp.act17.jpeg_dataset.v1`, current_full_v1, state252, action14, chunk8 |
| act16w solo BOX | `runs/act16w-native-dataset-r1/records/dataset` | 40 eps(train32/val8), 14,886행(선택) | `ugrp.grasp_act.dataset.v1`, history montage4, state252, action14, chunk8 |
| 근거리 | v7와 동일 소스(별도 신규 녹화 없음) | — | — |

- 두 데이터 모두 state 252·action 14·행동 계약이 같아 공동 학습 가능. 차이는 이미지 모드(history4 vs current1)와 메타데이터(stage/teacher_phase 유무), done 라벨 출처(act16w done_counts grasp1/release1).
- act16w 데이터셋 정규화·manifest sha: `verified-dataset-receipt.json`(manifest_sha256 `3d0a1c49…`, train 32/validation 8, teacher 40/40, source `c27a9d53…`).

## 구현안 (Phase C 착수 시)

1. **adapter**: act16w v1 데이터셋 로더(신규, default off) — tensors.npz(state/action/pad/image_index), frames.json, samples.json을 읽어 **current_full_v1**(image_index 마지막 프레임)으로 통일. action은 h0(action[:,0,:])에서 `extend_targets`로 chunk20 재구성하고 h<8은 원본과 parity 검증.
2. **정규화**: 두 TRAIN split을 합친 mean/std(floor .01)로 단일 통계(act-plus-plus는 `stats_dir_l` 전체에서 통계). adapter에 통합 stats 기록.
3. **혼합 샘플링**: act-plus-plus BatchSampler와 같이 **데이터셋 단위 확률**로 선택 후 그 안에서 episode uniform. 가중치는 사전등록(예: v7 0.5 / act16w 0.5, 또는 에피소드 수 비례). batch8·lr1e-5·KL10·bf16·chunk20·base smooth5·done 양성배치·best-val(v7 VAL8 시드 제외) 유지.
4. **조건 토큰**: 현재 state에 skill/kind 토큰이 있으나 데이터셋 출처 토큰은 없음. co-training 조건 구분을 위해 dataset-origin one-hot을 state 뒤에 붙이는 새 후보(`act18-co`)로 사전등록(입력 계약 변경 → 화이트리스트·입력 감사 갱신, 정답/외부정보 아님).
5. **학습**: 100k bf16, gcp2 L4 1대. 예상 시간: chunk20·~0.13s/step → 3.6h + gates(TRAIN4 15분, VAL8 15분) ≈ 4.0–4.5h.
6. **판정**: TRAIN4 4/4 → VAL8. FINAL40은 VAL8 통과·Lead 보고 후. 기존 결과와 pooling 금지, 패키징/배포 금지(게이트 통과 전).

## 위험·사전등록

- 입력 계약 변경(origin 토큰)으로 기존 R8/R100/B*와 직접 비교 불가(새 후보).
- act16w 이미지 모드(history4)를 current1로 바꾸는 손실 → 가능하면 history4 adapter도 병행 후보로 비교(비용 증가).
- 데이터 혼합은 결과 pooling과 구분해 기록(act-plus-plus co-training 근거). epoch/step 정의는 update 기준.
- 새 녹화·카메라 변경·평가 계약 변경 금지.

## 착수 트리거

B2 TRAIN4 4/4(또는 Lead 재승인) → 위 1–5 구현(1.5h) → prereg 동결 → 학습 시작. B2 실패 시 Phase C는 보류하고 B3/행동형식(ACTION_FORMAT_DESIGN.md) 경로 우선.
