# ACT13TRAIN — 회복50 조립·전체 입력 감사·기존 L4 두 군 smoke300

2026-10-15. **두 군 모두 첫 라운드 300/300·EXIT0, 손실 감소·유한 loss/gradient·저장 모델 재로딩 출력 완전 일치. class dev이며 학생 임무 성공이 아니다. 본 학습은 실행하지 않았다.**
실행 소스 `961aa7517b29f187f6869e2624ed848ee2c32cfd`(PR #504), 교사 `1fce11554754d4609470e4fe4b172f9a583bc026`, `recovery_active_search_v1` + rotation-on `act8_yaw_gain_v1`.
수치·원본·파일 해시는 [act13train-summary.json](act13train-summary.json), 고정 조립 설정은 [act13train-protocol.json](act13train-protocol.json).

## 데이터와 입력 경계

- 원본 ACT12 기록50(신규48+파일럿2), 승인된 train86820–86864(45) / validation86865–86869(5)를 그대로 사용했다. 원본50·ACT6 composed95와 섞지 않았다. 원본은 `gcp1:/home/ugrp/ugrp-sim/runs/act12-record-*-1fce1155`에 보존했다.
- 기존 로더와 같은 `ugrp.grasp_act.dataset.v1`(에피소드별 tensors.npz/images.npy/metadata)로 조립했다. 원장 **22,938행 전체**의 strict nested whitelist·실제 발행 명령 ledger 이력·자기 명령 clock을 재검증했다. 근거리 `local_skill_sample`과 회복 perturbation 제외 규칙을 적용한 학습 표적은 **18,086행(train16,275 / validation1,811)**이다. 원본 행수와 학습 선택 행수는 다르다.
- 전체 변환 텐서의 state/action/padding/RGB 인덱스를 원본에서 다시 계산해 완전 일치를 확인했다. 정규화는 train45의 고유 선택 timestep만으로 다시 계산해 저장 통계와 정확히 일치했다. validation은 통계 계산·체크포인트 선택에 쓰지 않았다.
- 학생 입력은 자기 RGB 이력, 자기 발행 명령16×14, skill/kind/role/destination 번호표, 자기 명령 clock2뿐이다. 정답·접촉·측정 관절·교사/평가 입력0. 50개 저장 result의 입력 감사는 invisible_measurements=0 / held_world_reads=0이며 hash-bound ledger 회복 성공50을 다시 집계했다. 이는 저장 자료 감사이며 새 물리 실행이 아니다.
- dataset manifest는 모든 생성 파일 **202개**의 SHA-256을 담고, 자체 SHA-256은 **`9ed3f155c87c8b53631ae89480bb0a6d868cc2a4c12341ff1e0579541deff925`**이다. 정규화 SHA-256 `e03b53f779a55c9ffc5b6d82f92ea365d38c55a6160adc9a8ab28937333137b2`. 전송 checkout SHA(파일럿 da4727b6 / 나머지0a891f53)와 실제 교사1fce1155는 각각 고정해 검증했으며 원본 SOURCE_SHA를 고치지 않았다.

조립본: `gcp1:/home/ugrp/act13train-961aa751/dataset`, 학습본: `ugrp-act-l4-pilot1:/mnt/act-source/act13train-961aa751/dataset`.
기존 버킷 `gs://ugrp-act-train-1014-runs/act13train-961aa751/dataset.tar.zst`의 압축본225,457,505byte SHA-256 `12bd25224c3854408377718c3e930ebd55ea538d30202ca9f7e9a333ae635926`를 사용했다. GCS 재다운로드와 L4 압축본 SHA-256이 같고, L4에서 전체202파일을 다시 확인했다. 첫 `gcloud storage cp` 재다운로드는 CRC 오류였으며 `storage cat` 스트림 전체 SHA-256 비교로 다시 검증했다. 새 VM·새 버킷·다른 프로젝트·자격 증명 전송은 없다. 원본 전체의 독립 백업은 아직 없으며 데이터셋 GCS 사본이 raw 전체 백업을 뜻하지 않는다.

## 실제 L4 스모크

기존 `ugrp-act-l4-pilot1`, 서울 `asia-northeast3-a`, g2-standard-4 / NVIDIA L4, batch8, seed20261015, balanced_bce_v1(weight1), dropout p0/p0.2. 두 군은 순차 실행했다. 재시도·학습 HOST_ERROR0. max-wall840초와 외부 timeout900초, checkpoint-every5000(최종300 저장), JSON 기록만 사용했다.

| 군 | step · EXIT | 첫→마지막 loss | 첫/끝 로그10개 평균 | 평균/중앙/p95 초/step | GPU 할당/예약 GiB | trainer wall초 |
|---|---|---|---|---|---|---|
| p0 | 300/300 · 0 | 94.35465 → 3.15304 | 16.61193 → 3.51226 | 0.19827/0.19238/0.19429 | 1.443/1.916 | 83.264 |
| p02 | 300/300 · 0 | 90.66122 → 3.21628 | 16.53922 → 3.61961 | 0.19665/0.19332/0.19530 | 1.443/1.916 | 78.574 |

두 군 모두 nonfinite0, readback `torch.equal` 통과. GPU 시간은 CUDA 동기화한 배치 로드/H2D/forward/backward/optimizer 포함, 저장·로그 제외다. smoke는 수렴·일반화·학생 임무 성공 근거가 아니다. optimizer 상태는 저장·해시 확인했지만 실제 재개 optimizer step은 이번 범위가 아니다.

- p0 summary SHA-256 `a08674f1d1d6c54d8ddc7573fa63954b20f150d95685881112fe5ecd59ecdba1`
- p0.2 summary SHA-256 `9706e053c89925ecacc8e402cb5e49bbbce9f8803b94482de1878f79e67edfd6`
- 원격 원본 `ugrp-act-l4-pilot1:/mnt/act-source/act13train-961aa751/{p0,p02}`, 각 최종 체크포인트622,002,255byte. 원격 파일27개 전체 해시와 회수 파일23개를 검증했다. lite266,240byte SHA-256 `2555b265f72f775e7047ff3ed6938d251a620e5f8c09b613641796e5b3c172ef`. 가벼운 회수본 `/Users/changmin/projects/ugrp-wt/act-train/outputs/act13train-ops/retrieved`. 원격 가중치·optimizer와 기존 모델은 보존했다.

시작 전 VM TERMINATED·8h STOP·startup idle1200초, 부팅 뒤 timer active/enabled·GPU 프로세스0을 확인했다. 종료 직전 source clean·GPU 프로세스0·idle active, 최종 **TERMINATED**(2026-10-15T02:27:07.532-07:00)를 확인했다. budget-stop은 시작 전/후 ACTIVE·설정 시험 이후 미발동이며 최신 저장 메시지는 2026-10-15T08:48:24.228312Z 순비용0KRW다. 비용 집계 지연·크레딧 잔액/실청구 미확인은 남는다. 자신의 L4만 정지했고 gcp1의 다른 작업은 변경하지 않았다.

## 디스크 해결과 시간·비용

`--checkpoint-every 5000`을 기본 off(0) 옵션으로 추가했다. **끄면 기존 smoke100/main500**, 켜면 smoke 최종300과 main5000/10000을 저장한다. 최종/중단 저장, optimizer·RNG·provenance는 유지하고 파일을 삭제하지 않는다.

- 새 데이터4.077GiB와 압축본0.210GiB, 소스 checkout을 놓은 뒤 L4 여유 **22.383GiB**.
- 두 군 체크포인트 총6개는 실측 기준 **3.476GiB**. 예약을32→**5GiB**로 계산해 재설정하고 바닥8GiB를 유지한다. 예약+바닥을 빼도 **9.383GiB** 여유다. 원본·기존 모델 삭제0.
- smoke 뒤 여유 **21.224GiB**, 남은 main 체크포인트4개 약2.317GiB를 써도 예상 **18.907GiB**. 각 main 시작 전 다른 승인 쓰기를 포함해 재측정하고 >=13GiB(예약5+바닥8)를 요구한다.

공식 단가로 사용자가 지정한 **$0.907714/h**를 적용했다(디스크·네트워크·세금·크레딧 제외, 실청구 아님). 각 군 총10k(이미 끝난 smoke300 포함)는 p0 **33.87분/$0.512**, p0.2 **33.46분/$0.506**, 합계 **67.33분/$1.019**다. 남은 main9700×2만은 **64.64분/$0.978** 추정이다. CUDA step max(평균,p95), 초기화2회·저장3회·재로딩/추론2회를 적용했다. 초기 outlier 때문에 평균이 p95보다 커서 큰 값을 썼다. optimizer 재개 추가 시간·VM 부팅/전송·장시간 속도 변화는 미측정이다. 이번 VM 시작~정지544.019초의 compute 추정은 **$0.1372**다.

## 미승인 본 학습 대기열과 보존 계획

새 파일 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-act13-train-961aa751.json`(SHA-256 `5bc3930a2f6d8308eb5c987ad3594a0802b7f62ea8246f4e33ff6d3351dc859f`)에 정확한 source/data/smoke SHA를 채웠다. 기존 ready 초안은 변경하지 않았다. 모든 bool 플래그는 false다. p0/p0.2 main10k는 각각 step300에서 재개하며 process21600초·외부21900초·예약23400초의 별도 <=8h VM 창이다. 매 군 새 사전 점검 후 실행·회수·정지/TERMINATED를 요구한다. 두 창 예약 상한46,800초 compute **$11.800282**.

[main-approval p0](act13train-main-approval-p0.json) / [p0.2](act13train-main-approval-p02.json)는 approved=false다. 조정자의 독립 재집계 결과·smoke 검토와 SHA 고정 main 승인 뒤에만 사용한다. `grasp_act_training_guard`를 우회하지 않는다.

완료 후 군마다 고정 최종 step10000 체크포인트·모든 파일 크기/해시·config/adapter/추론 자산·optimizer/RNG·데이터/교사/소스/검증 범위 출처를 회수한다. 새 ID와 새 GitHub Release asset을 만들고 `configs/model_artifacts.json`에 URL/크기/SHA-256/source/scope를 추가하는 PR을 낸다. 과거 asset을 덮어쓰거나 가중치를 Git 이력에 넣지 않는다. 업로드 뒤 새 경로에 재다운로드해 archive·내부 전체 해시와 실제 GCP 모델 로딩을 확인해야 배포 완료다. 현재 선택·배포한 본 학습 모델은 없다.

## 재현 명령

GCP L4의 새 budget/lifecycle/disk 점검과 시작 승인을 선행한다. [smoke 재현 스크립트](act13train-smoke.sh)는 고정 소스 checkout으로 이동하고 새 출력 디렉터리를 요구한다. Mac에서는 실행하지 않는다. 이 스크립트는 결과 기록 커밋의 도구이며 실행했던 소스 SHA는 위961aa751로 유지한다.

```sh
bash experiments/2026-10-15-act-train/act13train-smoke.sh p0 /mnt/act-source/act13-repeat-p0
bash experiments/2026-10-15-act-train/act13train-smoke.sh p02 /mnt/act-source/act13-repeat-p02
```

조립·전체 감사(cwd `/home/ugrp/act13train-source-961aa751`, gcp1 기존 Python):

```sh
/home/ugrp/ugrp-sim/src/0a891f53dc8c770f6a1c1b7bbc2b47302dfcb041/.venv-sim/bin/python -m scripts.prepare_grasp_act_data --runs-root /home/ugrp/ugrp-sim/runs --protocol experiments/2026-10-15-act-train/act13train-protocol.json --output /home/ugrp/act13-repeat/dataset
/home/ugrp/ugrp-sim/src/0a891f53dc8c770f6a1c1b7bbc2b47302dfcb041/.venv-sim/bin/python -m scripts.audit_grasp_act_dataset --dataset /home/ugrp/act13-repeat/dataset --raw-check --output /home/ugrp/act13-repeat/data-audit.json
```

main의 정확한 argv는 미승인 queue.jobs 두 개에 있다. 현재 실행하면 approved=false 때문에 거부돼야 한다.

검증: 관련 pytest 두 파일 **34 passed**(동시1개), `git diff --check`, 재현 shell `bash -n` 통과. Mac 학습·추론·물리·렌더0. 소스는 먼저 커밋·지정 upstream에 push했다(origin fork push는 missing necessary objects로 거절돼 PR #504의 지정 저장소 URL을 사용했다). 본 학습·독립 재집계 승인·optimizer 재개 실행·학생 새 조건 성공·Release 배포는 남아 있다.

## 참고

[PyTorch 공식 저장/로딩 지침](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html): 모델과 optimizer state_dict를 보존하고 eval에서 저장 전후 출력을 비교한다. 이번 변경은 선택적인 저장 간격만 줄이고 최종 저장과 optimizer/RNG를 유지했다. 기존 [ACTGPU1](actgpu1.md), `harness/grasp_act_data.py`, `scripts/grasp_act_training_guard.py`, [모델 배포 규칙](../../docs/model_artifacts.md)을 재사용했다.
