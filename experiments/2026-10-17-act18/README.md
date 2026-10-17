# act18: 근거리 ACT TRAIN 적합도부터 검증

상태: **NOT_READY (2026-10-18 03:33 KST)**. R8·R100 모두 100k fp32 학습을 끝냈지만 TRAIN4 관문이 **각 0/4**로, VAL8·FINAL40은 제출하지 않았다. 물리 임무 성공은 0/4이며 기본 제어기가 아니다. 두 모델은 NOT_READY 라벨의 재현·비교용으로 공개 Release에 보존했고, 배포 검증(익명 재다운로드·전체 SHA·CPU 로딩)만 완료했다.

## 최종 결과 (2026-10-17 09:25Z 학습 시작 → 10/18 03:33 KST 종료)

학습은 gcp2 L4 `ugrp-act-l4-gcp2`(g2-standard-8, project `ugrp-sim-b-1014`, account `changmin5781@gmail.com`)에서 소스 `52e486316c25be122dc1e872b10ef8cd1e8b98e8`로 실행했다. 두 후보 모두 100,000/100,000 updates, seed20261017, batch8, AdamW1e-5, **fp32**(당시 소스에 autocast/precision 코드 없음), readback_verified=true다.

|후보|chunk|steps|wall|체크포인트 sha256(step100000)|TRAIN4|VAL8|FINAL40|
|---|---:|---:|---:|---|---|---|---|
|R8|8|100,000|30,812s|`e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a`|0/4|미제출|미제출|
|R100|100|100,000|30,779s|`44b11c3c147fb633fffa9e9cb6a0a48c5801f0b8fd2bdd9e33ea14a16804a544`|0/4|미제출|미제출|

TRAIN4(원 프로토콜 첫 4시드, 네 종류 각1개) 4세계는 모두 `cap_end`(90 SIM초 상한)로 끝났다. `requested 4 → grasp_done 0(4 전부 cap_end) → stable_lift 0 → stable_release 0 → task_success 0` funnel이며, R8은 88601·88603에서 물리 lift만 2/4, R100은 물리 lift도 0/4다. stage 자체 recount와 별도 실행한 독립 원본 재계수(같은 `act18_recount.py`, actor-actions/actor-inputs/owner evaluation-only/scene.xml에서 재계산)가 **둘 다 0/4로 일치**했다.

마지막 10 SIM초 10Hz 링을 1Hz로 샘플링한 4행 몽타주(각 후보 4시드): Mac 사본 `outputs/e2e18-admin/playback/act18-R8-TRAIN4/failure-montage-1hz.png` sha256 `a4466db727d50ef2f36a2fb4972c45d1a88093b574291d714f9c56fa80b05d9b`(VM `/home/ugrp/ugrp-sim/runs/act18/montages/R8-TRAIN4-1hz.png`), `outputs/e2e18-admin/playback/act18-R100-TRAIN4/failure-montage-1hz.png` sha256 `6a6013eceea0c16fe87fee615b1bc4840219a4fc15a51a88ed520c3c7e88213c`(VM `.../montages/R100-TRAIN4-1hz.png`). `outputs/`는 git 제외 경로라 실험 디렉터리에는 JSON·문서만 둔다(baseline-F 몽타주와 같은 규약). 몽타주에서 마지막 구간은 대부분 파란 바닥/상자 하단 띠이며, Lead 시각 분석(독립 재검증 아님)으로는 R8 4/4가 t≈9.7–12.4s에 base·arm이 전체 정지(마지막 100틱 관절 range ≤0.005rad, 속도 0, 손가락힘 0)하고 목표상자와 정확히 0.20m 지점에 머문다.

개루프 TRAIN 적합도(물리0, 1,430행)는 정지/진동 설명만으로 부족함을 보인다. R8 wheel 오차 median 0.00146·p90 0.00754, servo PWM p90 16.29, 교사 이동 2,482틱 중 projected-stop 123·raw 반대부호 44였다. R100은 wheel median 0.00225·p90 0.02017, servo p90 29.56, projected-stop 124·raw 반대부호 49다. 즉 교사 상태에서의 예측 오차는 작은 편인데(act17 10k 대비 크게 개선) 폐루프에서는 조기 정지한다. 이는 "개루프 fit 문제"와 "폐루프 누적/정지"를 분리해야 한다는 기존 act17 진단과 같은 방향이며, 이번에도 기본 제어기로 채택하지 않는다.

게이트 규칙은 코드로 강제됐다. `act18_evaluate.allowed_seeds`가 VAL8에 TRAIN4 raw-recount 4/4 영수증을, FINAL40에 VAL8 8/8·frozen selection을 요구하고 `act18_finish.prepare_final`도 같은 조건을 재확인한다. 이번에는 TRAIN4가 0/4였으므로 finish-r3 summary에 `VAL: NOT_SUBMITTED_TRAIN_FIT_FAILED`, `FINAL40_submitted=false`, `winner=null`이 기록됐다.

패키징은 두 후보 모두 수행했다(`finish-r3/packages/{R8,R100}/registry-entry.pending.json`, sha256 `17b1649c0e03152cf866ca22de3696e65a1d5d391cd9ea20ddb3ccfa23b8c261`/`b3f4aec754a2652f6a76d8a5c94239dd9c61ea7f5605a0497bb77d5756c5ea92`). 공개 Release: <https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261017-act18-v7-r1> (Pre-release, **TRAIN4 0/4 NOT_READY, 재현용·사용 금지**). 공개 검증은 `results/release-r1/public-verification.json`(sha256 `fc74c8967ea43f9341b13a8c6bff36e0ea934d6822b60d24020f94be35ed9f7a`)에 있다: 새 checkout `e91d41809`에서 익명 재다운로드로 ZIP SHA·크기 일치, 내부 24/24파일 SHA(207,592,611 / 207,969,467 bytes) 일치, bundled CPU 로더 `ready=true, chunk=8/100`. 이는 배포·로딩 검증이며 물리 성공이 아니다. registry는 `configs/model_artifacts.json`에 append했다(과거 자산 덮어쓰기 없음).

### 조건 이탈·미검증 범위
- **R100 gcp5 미이동(deviation):** bf16 프로브(2,000 step, 1.10배)는 수용했지만, R8이 gcp2에서 fp32로 학습 중이라 정밀도가 섞이고(합산 금지), `act18_train.py`가 옵티마이저/RNG 재개를 지원하지 않아 42,400/100,000(≈13,484s)을 폐기해야 하며, gcp5 예산 1,000KRW 정지 위험이 있어 gcp2 matched fp32 pair를 끝까지 유지했다. 근거는 `bf16-probe-decision.json`.
- 이 학습은 **fp32**다. bf16 기본 전환 커밋(c7900c0ac)은 이 학습 시작 뒤다. 100k bf16 학습은 아직 없다(runtime 증거는 2,000 step 프로브뿐). bf16 결과와 합산하지 않는다.
- 미검증: VAL8·FINAL40·일반화 성공률(미실행), 100k bf16, R100 gcp5 이전·재개, raw 시연 전체의 원격 백업(Release 범위 아님), 다른 호스트/정밀도/조건과의 합산.
- 실행 실패 원본 보존: `finish-r1`(학습 전 정지, `8d95cb6a…`), `finish-r2` HOST_ERROR(`bd58ebb5…`, training owner disappeared), `baseline-F-TRAIN4-r1` HOST_ERROR(원 recount가 eval-owner에 없는 input_audit 키를 요구한 결함, wall 1,646.5s; 수정 8d21fbe1a 뒤 raw recount 0/4, sha256 `95a95ac2…`)를 그대로 남겼다.
- 기계 판독용 전체 실행·경로·SHA는 `summary.json`에 있다.

`SURVEY.md`는 공개 구현 비교, `DIAGNOSIS.md`와 `rejection_table.json`은 변경 전 실패 분포다. `diagnosis-summary.json`은 gcp2 원본에서 만든 축약 요약이며 전체 히스토그램·프레임 예측은 VM에 있다. 회수 SHA-256은 각각 `b36b39aa2b952c4c7e3e0048e272b9d75295f44256ffa7da9d5893190f7ea217`, `370de0a0c3ec6a2f31b3f25d4921413dbc00fbe1b8ec91faa98d12a02ad55307`이다. 첫 진단 시도는 물리 전용 환경에 torch가 없어 실행 전 실패했고, 기존 ACT 환경으로 재시도했다(새 환경·새 물리0).

새 비교는 `protocol.json`에 고정한다. R8과 R100은 같은 v7 TRAIN200 시연, batch8, seed20261017, AdamW1e-5, 100k updates를 사용한다. 차이는 예측 chunk8/100이다. 기존 완료 BCE는 동일하게 유지하는 과제 어댑터이며 원 논문의 추가 상태·카메라를 가져오지 않는다. 원본 LeRobot을 직접 호출하고 별도 ACT 재구현은 하지 않는다. 체크포인트10k/50k는 TRAIN 진단에만 쓰고 최종100k를 비교한다. 추론은 두 후보 모두 공개 ACT temporal ensemble0.01·매틱 재예측이다. 이는 기존 act17의 실행8틱과 다른 조건임을 명시한다.

모델 완성 뒤 첫 TRAIN4(원 프로토콜 첫4개, 네 종류 각1개)의 개루프·폐루프를 먼저 확인한다. 4개는 종류별1개의 유한 적합도 점검이라는 설계 선택이며 모집단 성공률이 아니다. 이 네 시작의4/4가 확인된 후보만 같은 VAL8로 가고, VAL8의8/8이 원본으로 재계수된 후보만 FINAL40에 진입한다. TRAIN/VAL/FINAL을 합산하지 않는다. 현재 새 시연 녹화는 필요하지 않다: 기존 h0부터 긴 chunk를 재구성하고 기존8개 미래 표적과 전수 일치를 검사한다.

Mac에서는 소스 편집·짧은 비물리 시험·요약/기존 프레임 띠 파일 열람만 한다. 실행과 실패 분석은 gcp2 L4 영속 디스크, 모든 gcloud는 계정/프로젝트 명시, gcp1·CPU VM 시작0이다. 모델 키·정답 학생 입력·정적 지도·weld·noslip은0이다. 예산2,000KRW 정지와 유휴20분을 유지한다. 새 이미지/텐서 복제0, 예상 신규 디스크는 소스 사본≤2GB+2후보×3체크포인트×0.21GB+평가/대표 영상≤2GB이며 기존 여유26.76GiB에서 바닥8GiB를 남긴다. 중간/최종 모델과 실패 원본을 보존하고, 결과에 쓰는 모델은 Release 업로드·익명 재다운로드·전체 SHA·로딩까지 검증한다.

훈련 진입점은 `scripts/act18_queue.py --enabled`, 개별 훈련은 `scripts/act18_train.py --enabled`다. 모든 새 대기열은 현재 main에서 가져온 `check_current_stack.py`와 `configs/current_stack.json`으로 점검하고 절대 `rejection_table` 경로를 연결한다. 실행 소스는 커밋 후 고정한다. 임대 `leases/act18*.json`과 자기 프로세스를 정리하고, 타 작업이 없을 때만 L4 정지·TERMINATED를 확인한다.

## bf16 짝 비교 (10/17, gcp5 단독)

AGENTS 10/17 bf16 규칙에 따라 gcp5 L4 한 대에서 R100 조리법(chunk100·batch8·seed20261017)을 2,000단계씩 fp32→bf16 순차로 돌렸다. bf16은 forward/loss만 `torch.autocast('cuda', dtype=torch.bfloat16)`이고 가중치·옵티마이저·grad clip은 fp32다. 단계 중앙값 0.1675→0.1523초(1.10배), 최고 GPU 메모리 2,230→2,186MB, last200 손실 평균 1.654→1.596, VAL8 손실 0.7358→0.6448(2,834행), NaN/inf 0/2000·0/2000이었다. 단일 시드·2,000단계 방향 점검이며 품질 결과가 아니다.

판정: 수용. 다만 R100을 gcp5로 옮기지 않는다. R8이 gcp2에서 fp32로 이미 학습 중이라 bf16 R100과 짝지으면 chunk 차이 외에 정밀도가 섞이고(AGENTS: bf16·fp32 결과 합산 금지), act18_train.py는 옵티마이저/RNG 재개를 지원하지 않아 42,400/100,000에서 옮기면 13,484초를 버리고 0부터 다시 해야 하며, 그래도 gcp2 잔여(약 5.1시간)보다 0.9시간 이르는 데 그친다. bf16은 다음 새 학습부터 쓴다. 원본·해시·근거는 `bf16-probe.json`, `bf16-probe-decision.json`, `bf16-probe-progress-*.jsonl`에 있다.

### 프로브 재계수 검증 범위 (10/17, haiku-verifier 독립)

원격 원본 JSONL은 50스텝마다 1점만 남겨 팔당 41점(2,000스텝의 2.05%)이다. 그 표본으로 다시 계산한 단계 중앙값은 fp32 0.1682초, bf16 0.1524초(1.104배)로 보고값(0.1675/0.1523, 1.0997배)과 방향·크기가 일치했고, 메모리 2,230→2,186MB(십진), VAL8 손실 0.7358→0.6448(2,834행 보고값), 비유한 손실 0건도 확인됐다. 다만 보고된 중앙값은 첫 200스텝을 제외한 1,800점에서 계산한 값이고, "0/2000 NaN"과 2,834행은 원격 실행 보고값이라 로컬 JSONL 41점만으로는 재현되지 않는다. 로컬 파일 해시는 decision에 기록한 원격 해시와 일치한다(b4801ee9…, 11f8e04e…, 8dda6137…). 이 검증은 표본 2.05%에 대한 방향·크기 확인이며 100k 학습 품질이나 전체 스텝 집계의 독립 재계산이 아니다.

새 ACT 학습 기본은 bf16이다(사용자 10/17 결정, 위 프로브 확인). `act18_queue.py`/`act18_train.py`가 `--precision bf16_autocast_v1`을 기본으로 쓰고 queue.json·훈련 config에 `training_precision` 영수증을 남긴다. fp32는 재생·정밀도 짝 비교에만 명시적으로 쓰며 bf16 결과와 합산하지 않는다. 이 기본값 변경 뒤의 새 학습은 아직 실행 전이라 런타임 증거는 프로브(2,000스텝)뿐이다.
