# ACT13 main 학습 실행 기록

class **dev**, research_result=false, student_success=false. 학습·저장·재로딩 검증이며 학생 독립 실행·물리 성공은 측정하지 않았다.

- 실행 소스: `961aa7517b29f187f6869e2624ed848ee2c32cfd`; PR #504. 실행 VM 소스는 clean detached이며 기록용 Mac 브랜치는 별도로 유지했다.
- Dataset manifest SHA-256: `9ed3f155c87c8b53631ae89480bb0a6d868cc2a4c12341ff1e0579541deff925`. train45/validation5, 선택행18086(train16275/validation1811), 정규화는 train45 전용.
- 승인 대기열: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-act13-train-961aa751.json`; 보존 사본 SHA-256 `f16e6081e33c96776c1dbbf6e711e4804641d8da3703ad43bef8d489ab4a5ea4`. coordinator_approval와 두 main-approval 템플릿을 그대로 사용했다.
- 기존 GCP `ugrp-act-l4-pilot1`, `g2-standard-4`/NVIDIA L4, `asia-northeast3-a`, 프로젝트 `ugrp-act-train-1014`만 사용했다. 신규 VM·다른 호스트·모델 키·Kaggle 자격 증명 반입 없음.
- 시작 전 TERMINATED·8h STOP·idle1200·budget-stop ACTIVE/설정 시험 이후 미발동을 확인했다. VM에서 clean detached961aa751·GPU 프로세스0·idle active/enabled·데이터202개 전체 파일 해시·여유22774943744 bytes를 확인했다.
- p0→p02 순차 실행. seed20261015, balanced_bce_v1/weight1, history dropout0/0.2, 각 군의 정확한 smoke step300에서 optimizer/RNG까지 재개했다. 총 목표10000(신규9700)·checkpoint5000/10000·가드·external_timeout_argv를 유지했다.

| 군 | 종료/스텝 | 첫→마지막 기록 손실 | 첫10→마지막10 평균 | 학습 wall초 | NaN/비유한 | 최종 재로딩 |
|---|---|---|---|---|---|---|
| p0 | EXIT0 / 10000 | 3.129037 → 0.132395 | 3.182868 → 0.297731 | 1823.958 | 0 | torch.equal 일치 |
| p02 | EXIT0 / 10000 | 3.172845 → 0.132137 | 3.220209 → 0.369120 | 1821.623 | 0 | torch.equal 일치 |

손실은 해당 군 main301–10000의 학습 로그이며 validation 성능이나 학생 과제 성공률이 아니다. 훈련기는 모든 업데이트에서 loss 유한성 및 gradient의 비유한 값을 검사하며, 기록된 수치도 별도로 재검사했다. 각 군의 최종 GraspActor를 디스크에서 다시 로딩하고 동일한 학습 입력에서 메모리 내 최종 정책과 `torch.equal`로 출력이 정확히 일치함을 확인했다. summary의 전체 artifacts 해시도 VM에서 다시 읽어 검증했다.

손실 곡선 PNG를 직접 확인했다. 유한한 배치 손실 스파이크(p0 최대 10.876695(step8210), p02 최대 8.317372(step2750))가 있으므로 단조 감소로 해석하지 않는다. 후행 평균은 초반보다 감소했고, 스파이크 원인 진단과 학생 성능 평가는 이번 범위에 포함하지 않았다.

실제 VM 기동~정지 시간에 승인된 공식 계산단가 **$0.907714/h**를 곱한 compute 비용 추정은 **$0.999340**다. 디스크·네트워크·세금·크레딧은 제외하며 실청구·남은 크레딧 잔액은 확인하지 않았다. 학습 시간 합산은 3645.581초다.

| VM 창 | 시작 | 정지 | 실제 기동초 | compute 추정USD |
|---|---|---|---|---|
| 1 | 2026-10-15T02:35:49.271-07:00 | 2026-10-15T03:41:52.662-07:00 | 3963.391 | 0.999340 |

최종 체크포인트 원본은 아래 VM 영속 디스크 경로에 남겼다. Mac으로 가중치를 내려받지 않았고 GitHub Release 업로드도 하지 않았다.

- p0: `/mnt/act-source/act13train-961aa751/p0/main/step-010000`; summary SHA-256 `50367eaaaf1039785fe97431aada9add2f933345207ad37dec223286bb1b0202`.
  - `step-010000/actor/SHA256.json`: 265 bytes, SHA-256 `1a79b25b5e84401150074af9d3b7fa7f79a975e72557470f2f54c37c500c0f56`.
  - `step-010000/actor/adapter.json`: 15287 bytes, SHA-256 `f5832e9fe6bbfcff0671456ae33457071222c214edefc61e4e58a3c485be3491`.
  - `step-010000/actor/config.json`: 1278 bytes, SHA-256 `b63bc05fb84e5c0f53329336a7a147f18ca73f297ed25279b42b968e279f571f`.
  - `step-010000/actor/model.safetensors`: 207363320 bytes, SHA-256 `b617415079a95a4bb4426fefe0d445cb288ea49eef0928278cb268212de02676`.
  - `step-010000/optimizer.pt`: 414621387 bytes, SHA-256 `f64b64fe9f7e8528241623d737fb765db24b0bbb78c17c94b97fd84153aca49c`.
  - `step-010000/resume.json`: 722 bytes, SHA-256 `a0da81b9c5858dcd1bae7d0d2e59c1f28002b9a9ee2925f3a09dddb478eb4022`.
- p02: `/mnt/act-source/act13train-961aa751/p02/main/step-010000`; summary SHA-256 `97d329c255acf91065bc32ebfb54743070fc37e372aa44b301b1783fb14416e4`.
  - `step-010000/actor/SHA256.json`: 265 bytes, SHA-256 `b2b4589abdfafaba3f75b98ab8742a182f5d8a0202e549e421f8a1d107bea81d`.
  - `step-010000/actor/adapter.json`: 15287 bytes, SHA-256 `f094630df3d53f61aa67e10885281a3443c6ca0b4cd08b7e818fcec8cc10fd41`.
  - `step-010000/actor/config.json`: 1278 bytes, SHA-256 `b63bc05fb84e5c0f53329336a7a147f18ca73f297ed25279b42b968e279f571f`.
  - `step-010000/actor/model.safetensors`: 207363320 bytes, SHA-256 `b55a72bc8cbd01fec553313375b59686bc8297ea62944283fccedd38cff58613`.
  - `step-010000/optimizer.pt`: 414621387 bytes, SHA-256 `3dcdc097525331d4c877554390f7f342142463bee25c1d3517a905243ee0e139`.
  - `step-010000/resume.json`: 722 bytes, SHA-256 `9a834e0fb5de56591c8dad15f3181badec7ce134c581888390f2116bfec0711f`.

Mac 회수 위치: `/Users/changmin/projects/ugrp/outputs/act13train-961aa751`. `loss-curves.png`/`.svg`, 군별 `*-loss.csv`, 원본 summary/progress/승인/실행/검증 JSON, `checkpoint-hashes.json`, 전후 VM·예산 증거를 보존했다. 회수 tar SHA-256 및 summary/progress/RUN_META 해시를 Mac에서도 검증했다.

최종 VM 상태: **TERMINATED**. 운영 기록은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/ops-log.md`; 실패·중단·비용 이상은 `ops-alert.md`에도 기록한다. 최신 예산 관측: `{"timestamp": "2026-10-15T10:27:05.868650Z", "payload": {"budgetAmount": 1000, "costAmount": 0, "currency": "KRW"}, "checked_at": "2026-10-15T10:42:17.024375+00:00"}`. 비용 집계 지연은 남는다.

완료 상태: `complete`. 실패/미완료 기록: `[]`. 학생 시험·성공 판정·게이트 승격·배포는 미실행이며 조정자 결정 전이다.

저장소 소스 코드는 수정하지 않았다. 이 문서와 요약 JSON만 결과 기록으로 추가했다.
