# ACT18 v7 fp32 100k R8/R100 — TRAIN4 0/4 NOT_READY (재현·비교용, 사용 금지)

이 Release는 실험 보존용입니다. **두 모델 모두 TRAIN4 4/4 관문을 통과하지 못했고 실제 물리 임무 성공은 각 0/4입니다. 기본 제어기로 쓰지 마세요.**

## 학습
- 호스트: gcp2 L4 `ugrp-act-l4-gcp2` (project `ugrp-sim-b-1014`, g2-standard-8)
- 물리·장면: `warp_native_contact_v1`(GPU/CPU noslip 0), weld OFF, v7 시나리오·v6 화물, `grasp_act_teal_blue_v1`
- 데이터: `act17-v7/dataset-r1`, manifest sha256 `44c1c46073aa08ea028324ffe924b67d862a2f01b56f4db11afad17000a9b198`
- 학습: 100,000 updates, batch 8, seed 20261017, AdamW lr1e-5, **fp32**(혼합정밀도 없음), 기존 과제 완료 BCE adapter
- R8 chunk8 checkpoint sha256 `e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a`
- R100 chunk100 checkpoint sha256 `44b11c3c147fb633fffa9e9cb6a0a48c5801f0b8fd2bdd9e33ea14a16804a544`
- 학습 소스 `52e486316c25be122dc1e872b10ef8cd1e8b98e8`, 패키징 소스 `ab89b3c549791be19c93110b917a7fe1370ec15e`, 프로토콜 sha256 `1db4e22345fdf29cdd80d07bbf61f23aa6101a6859e125f974f550577be1fb4e`

## 게이트 결과 (요약 아님, 원본 재계수)
|모델|TRAIN4|grasp_done|안정 lift|안정 release|VAL8|FINAL40|
|---|---:|---:|---:|---:|---|---|
|R8|0/4|0/4|2/4 물리 lift(비안정)|0/4|미실행|미실행|
|R100|0/4|0/4|0/4|0/4|미실행|미실행|

- TRAIN4 4/4 실패 → VAL8 미제출, VAL8 8/8 미달 → FINAL40 미제출. 4세계 모두 cap_end(90 SIM초 상한) 종료.
- 원본 재계수: `act18_recount.py`를 stage 원본(actor-actions/actor-inputs/owner evaluation-only/scene.xml)에 별도 실행, stage 자체 recount와 0/4 일치.

## 구성물
각 ZIP 24파일: `model.safetensors`·`config.json`·`adapter.json`·`SHA256.json`, `comparison-protocol.json`·`training-summary.json`·`dataset-manifest.json(.zst)`, `inference/`(bundled ACT runtime·정책·입력계약·로더), `environment.json`·`provenance.json`·`README.md`.
포함하지 않음: 옵티마이저 상태, raw 시연 전체, 학습 로그 원본.

## 검증
- 공개 재다운로드·전체 파일 SHA-256·CPU 로딩: 아래 `public-verification.json`(익명 다운로드, 고정 ACT 환경 CPU load_model.py).
- 이 검증은 배포·로딩 확인이며 물리 성공이나 일반화 결과가 아닙니다.

## 미검증 범위
- 실제 임무 성공 0/4(TRAIN4), VAL8·FINAL40 미실행
- 100k bf16 학습 없음(bf16은 2,000 step 짝 프로브만)
- 다른 호스트·정밀도·조건 결과와 합산 금지
