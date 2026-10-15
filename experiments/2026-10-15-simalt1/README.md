# simalt1 — L4 EGL / MJWarp 한 구간 진단

2026-10-15, **미채택 / ready=false**. MuJoCo CPU 주 흐름과 최종 평가는 유지한다. 기본 OFF인 별도 진단이며 CPU 연구 결과와 합산하지 않는다. 단계 D 학습은 하지 않았다. Refs #523.

## 결과와 관문

| 단계 | 실제 수행 | 결과 | 다음 관문 |
|---|---|---|---|
| A N=1 | ACT11 seed8317100의 발행 명령 434개, 43.4 SIM초 재생. L4 NVIDIA EGL 대 gcp1 OSMesa/llvmpipe | 첫30 wall/SIM **4.358 대 2.664**, 전체 loop **184.155 대 113.226초**. 양쪽 재생 완료 | 새 교사 성공률·데이터 수집 속도 검증이 아님 |
| A N=4 | 같은 명령 trace를 4회 동시 재생, act15 추론 서버와 자원 공유 | 4/4 재생 완료, 첫30 중앙 **8.562**(8.437–8.594), 전체 배치 380.956초·37.800 trace/h | 기존 >6.0 관문으로 **N=8 미제출** |
| B | L4에서 저장한 동일 상태 30개를 두 렌더러로 비교 | K/D·카메라 SE3 정확히 일치, 방향·채널 원순서 30/30, 검정 경계 XOR 0. RGB MAE 중앙 0.546/255, 보이는 상자 mask IoU 중앙 0.9964·최소 0.9919 | **전체 통과 아님**. 상자 mask 비어 있음 19/30. 전체434 상태의 추가 평가에서 FOV 가장자리 후보3, 명확한 가림 후보0. 끝 색띠도 미검증 |
| C | noslip 구현 개발 SHA 고정, 기존 완성 장면을 변경 없이 변환하는 선행 관문 | `put_model`에서 noslip=10 유지. `put_data` float64→float32 변환에서 `overflow encountered in cast` | **중단**. 수용된 step 0, 단일 로봇+상자 명령 동등성·3초 슬립·N1/16/64 처리량 미측정 |

A는 성공한 기존 교사의 **발행 명령만 재생한 부하 진단**이다. 실시간 교사의 인식·탐색·판단 비용은 포함하지 않았고 새 물리 성공을 채점하지 않았다. N=4는 독립 seed 4개의 성공률이 아니다. gcp1 동시16 기준의 완결 시도/$는 새로 측정하지 않아 제안된 2배 채택 관문은 판정할 수 없다.

C 선행 관문은 기존 3대 몸체·장면을 그대로 둔 호환성 점검이다. 요청한 1대+작은 상자 축소 장면의 물리 동등성 단계까지 가지 않았다. 최초 probe는 RuntimeWarning을 예외로 승격하지 않아 step 컴파일에 진입했다. 경고를 확인한 뒤 소유 PID6830을 종료했고, 어떤 step도 완료로 수용하지 않았다. 이어 경고를 즉시 예외로 처리하는 가드를 넣은 **입력 변환 점검만** 4.24초 수행해 같은 오류를 확인했다. 옵션·마찰·접촉·dt를 바꾸는 우회는 하지 않았다. 최초 probe의 부분 GPU 실행 여부와 overflow가 발생한 정확한 배열 필드는 미확인이다.

## 시간 분해와 동일성

| 전체 누적 native timer(초) | gcp1 N1 | L4 N1 | L4 N4 worker0 첫30 |
|---|---:|---:|---:|
| physics `mj_step` | 87.061 | 171.391 | 242.512 |
| scene update | 0.027 | 0.041 | 0.036 |
| GL draw | 9.801 | 0.655 | 1.059 |
| readback | 11.954 | 0.194 | 0.186 |
| remap | 0.085 | 0.630 | 1.149 |
| Pillow JPEG | 미계측 | 미계측 | 0.603 |
| 별도 reset wall | 3.726 | 7.180 | 각 result.json |

native timer에는 setup 호출도 누적된다. 첫30/전체 loop wall에는 reset wall을 포함하지 않는다. 그러므로 이 표를 서로 더해 loop 시간과 같다고 해석하지 않는다. GL draw는 비동기 GPU 요청 시간이고 readback에는 대기가 들어갈 수 있다. 기존 JPEG가 Pillow 경로임을 확인한 뒤 N4에서 직접 계측했다. N1 미계측 값을 0으로 채우지 않았다.

GPU GL draw/readback은 빨랐지만 이 호스트·부하에서는 물리 계산이 전체 시간의 대부분을 차지했다. L4 C와 gcp1 C의 **434×2025 integration-state 배열 전체가 정확히 일치**했다. 이는 동일 발행 명령 재생의 상태 동등성이며 새 영상으로 결정하는 교사·ACT의 성공 동등성이 아니다.

## 고정 조건과 입력 경계

- base `580f37ebc3129984c0dc07d1f73ccfe92e273202`, 별도 진단 코드의 실행 SHA는 [summary.json](summary.json)의 `sha`에 기록했다. source teacher `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`, ACT11 adapter 원본 `1fce11554754d4609470e4fe4b172f9a583bc026`.
- A/B: `mujoco==3.12.0`, 640×480, 10 Hz, 기존 K/D와 `cv2.remap(INTER_LINEAR, BORDER_CONSTANT)`, `floor_light_v1`, 기존 solo 장면의 끝 색 OFF. 외관·FOV·질감을 새로 바꾸지 않았다.
- dt=0.00025, solver iterations=80, ls_iterations=50, noslip_iterations=10, implicitfast·elliptic·Newton, weld OFF, 기존 마찰 유지. XML의 호스트별 절대 asset 경로 때문에 XML bytes 해시는 다를 수 있다. 동일 source archive와 각 XML 해시를 함께 보존했다.
- C: 개발 `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148`, package 표기 3.16.0을 release tag와 구분한다. 별도 `/tmp/simalt1/warp-env`에 MuJoCo3.16.0·Warp1.15.0 설치. C 평가용 `/tmp/simalt1/c-env`의 MuJoCo3.12는 유지했다. 기존 act15 환경은 수정하지 않았다.
- ACT 계약은 읽기만 했다. 자기 RGB4장·발행 이력16개·10 Hz·chunk8·14차원, 각 원본640×480. 해당 두 파일의 SHA-256은 summary의 `configuration`에 있다. act-train worktree 수정 0.
- [trace.jsonl](trace.jsonl)은 `t/phase/command`만 남겼다. `visible_target` 등 원본 교사 정답은 제거했다. phase는 기록 분류에만 쓴다. 정책·학습 모델은 호출하지 않았다. 설정/정답 좌표는 장면 setup·비교·평가 기록에만 있다.
- 검색은 수행하지 않았다. 재생은 명령 수·SIM 시각으로 끝나며 wall 상한은 자원 예산 전용이다. 새 실행기는 별도 기록용 **10 Hz·100장(10 SIM초)** 고리 버퍼를 저장한다. 학습 카메라와 제어 경로는 바꾸지 않았다.

## 거부 분포와 원본

[rejection_table.json](rejection_table.json)에 단계별 누적 통과·거부 수, 범주·막은 대상·최소 틈의 적용 여부와 원본 경로를 남겼다. 기하 통로 거부가 아니므로 minimum_gap은 null과 사유를 함께 적었다. [protocol.json](protocol.json)의 `rejection_table`은 실재하는 절대 경로를 가리킨다. 다음 대기열 승인은 false다.

- A 초기 gcp1 EGL 선택은 pre-import HOST_ERROR 1건. 이 호스트의 기존 OSMesa로 수정한 실행은 별도 경로에 보존했다.
- B 수정 전 분포는 [coverage-first.json](coverage-first.json), 전체 상태의 평가 전용 ray/투영 감사 요약은 [snapshot-selection.json](snapshot-selection.json). 필요한 희귀 사례 수가 없어 30개 표본으로 다시 포장하지 않았다.
- L4 원본: `ugrp-act-l4-pilot1:/home/changmin/ugrp-sim/runs/simalt1`. 원본 611파일에 `sha256sum -c SHA256SUMS` **611/611 PASS**. 파일별 해시와 설치 환경은 [l4-results.json](l4-results.json)에 포함했다. 전체 원본은 VM 디스크에 있고 Mac에는 요약·몽타주만 회수했다.
- gcp1 비교·감사·영상 원본 경로는 summary `raw_paths`, 각 실행의 `raw_paths`와 `sha256`에 있다. [gcp1-reference.json](gcp1-reference.json), [render-comparison.json](render-comparison.json), [state-comparison.json](state-comparison.json)을 보존했다.

## 영상 검토

gcp1에서 저장 상태를 복원해 개요+r1+r2(유휴)를 나란히 렌더했다. 0–43.4 SIM초 전체를 2 Hz·87프레임의 두 프레임 띠로 직접 읽었다. 4배속 MP4는 ffprobe로 10.875초·59,761 bytes 확인했다. Mac 화면 앱은 열지 않았다. 로컬 회수 위치는 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/playback/simalt1/`이다.

시각 순서: 0–0.5초 팔 접기, 0.6–7.8초 접근(자기 화면에서 상자가 잠시 나갔다 다시 들어옴), 7.9–10.3초 정렬(상자가 아래쪽에서 커짐), 10.4초 이후 팔 동작 동안 자기 화면은 주로 바닥이고 대상이 보이지 않음, 33.3초부터 후진, 35.4–41.2초 주위 벽·문 방향을 둘러봄, 41.3초부터 완료 상태다. 이것을 집게 접촉/들기 성공의 시각 판정으로 확대하지 않았다.

단계명만 고른 B 표본보다 전체 2 Hz 검토에서 접근 중 짧은 화면 이탈과 이후 긴 비가시 구간이 분명했다. 2 Hz만으로 빠른 진동 부재를 판정할 수 없다. 실행된 임무 실패는 없고 C는 입력 변환에서 중단되어 실패 직전 10초 영상 대상이 없다. 진행한 A의 마지막10초 10 Hz 원본은 각 run의 `failure-rgb-buffer/`에 별도로 남겼다. 자세한 타임라인은 [playback-review.json](playback-review.json).

## 예산·자원 종료

설치 시작 13:13:35Z부터 소유 계산 종료 13:30:10Z까지 L4 공유 VM 창은 **995초(0.2764h)**다. 공식 서울 g2-standard-4 정가 **$0.907714004/h**로 이 창 전체는 **약 $0.251**다. act15와 공유한 VM 시간의 정가 추정이며 실제 청구·크레딧 잔액·이 작업의 증분 비용이 아니다. 디스크·네트워크·세금은 제외했다. 4h 전체 상한의 VM 정가는 약 $3.631이다.

A+B 2h·C 2h 및 누적4h 이내다. 설치 시작 후 첫30 SIM초 유효 측정은 약6분 이내에 확보했다. budget-stop의 13:15:39Z 로그는 costAmount=0 KRW·budgetAmount=1000 KRW였고 정지 발동은 관측되지 않았다. 잔여 크레딧은 미확인이다. 8h STOP·유휴20분·budget-stop을 변경하지 않았고 새 VM은 만들지 않았다.

13:30:10Z 소유 계산 종료 시 GPU 0%, 계산 앱은 기존 **act15 PID1670만** 남았다(658 MiB). 이 작업의 프로세스·자식은 종료했다. 공유 VM을 정지하지 않았다. GL 라이브러리만 기존 compute driver와 같은 580.178.04 버전으로 추가했고 compute driver·act15 서버는 보존했다. 디스크 여유는 종료 무렵 약6.6 GB였다. 모델 키·에이전트/Kaggle 자격 증명은 VM으로 보내지 않았다.

그 뒤 13:32:30Z·13:33:22Z에 사용자 계정의 `instances.stop` API 감사 로그가 있었고, 최종 조회는 **TERMINATED**였다. 이 작업에서는 VM stop 명령을 실행하지 않았다. 최종 SSH 재확인은 정지 상태로 실패했으며 재시작하지 않았다. 앞의 act15 생존 확인은 13:30 시점의 근거다. 원본 해시 검증과 결과 회수는 정지 전에 끝났다. [최종 호스트 상태](final-host-status.json).

## 검증과 재현 명령

Mac에서는 순수 안전성 검사만 실행했다: `python -m pytest -q tests/test_simalt_pilot.py` **5 passed**. 6개 진단 스크립트 구문 검사·`git diff --check` 통과. 실제 물리·렌더·영상 생성과 분석은 L4/gcp1에서만 했다.

다음은 실행 경로 재현 설명이다. 현 판정은 확대 불가이며 N8·C 배치를 재제출하지 않았다. 먼저 고정 teacher source를 `git archive 6f057f7e sim harness scripts configs maps`로 별도 SOURCE에 풀고, 이 폴더의 plan/trace를 사용한다.

```sh
# L4: 명시적 기본-off 렌더 진단
C_ENV/bin/python scripts/simalt_pilot.py replay --source SOURCE --plan plan.json \
  --trace trace.jsonl --out NEW_RAW --sha SOURCE_SHA \
  --render-backend egl_l4_v1 --egl-l4-v1 --snapshots
# gcp1: 같은 C 엔진 + 기존 렌더러
MUJOCO_GL=osmesa LP_NUM_THREADS=1 C_ENV/bin/python scripts/simalt_pilot.py replay \
  --source SOURCE --plan plan.json --trace trace.jsonl --out NEW_REF --sha SOURCE_SHA --snapshots
# gcp1: 같은 저장 상태의 렌더 분포 비교 / 평가 전용 희귀 사례 감사
python scripts/simalt_compare_render.py REF_SNAPSHOTS L4_SNAPSHOTS comparison.json
MUJOCO_GL=osmesa python scripts/simalt_select_snapshots.py --source SOURCE \
  --plan plan.json --states FROZEN_L4_STATES --out selection.json
```

C의 실행 명령과 오류는 `l4-results.json`의 C0/C1 원본 경로에 있다. 경고 즉시 예외 가드 이후에도 동일 배열 변환이 거부되므로 물리/배치 측정 명령은 기록하지 않았다. 새 학습·데이터 관문이나 기존 gcp1 결과를 이 진단으로 승인하지 않는다.

## 참고 자료

- [사용자 결정 · #523 댓글6192850947](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/523#issuecomment-6192850947)
- 로컬 조사: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/research/simalt.md` §1·2·1.3·6, [GCP 실행 규칙](../../docs/gcp_simulation.md)
- [고정 개발 MJWarp io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py), [noslip solver](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/solver.py), [pyproject](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/pyproject.toml). 고정 HTTPS 원문과 설치 io.py SHA256 `d496e51ac392731fd1b20d0cc53c573b38dcf38924dbcd04a2d5f85ffeb84310` 대조.
- [MuJoCo 시각화](https://mujoco.readthedocs.io/en/latest/programming/visualization.html), [GCP accelerator VM 공식 가격](https://cloud.google.com/products/compute/pricing/accelerator-optimized). 2026-10-15 HTTPS 원문 서울 행 $0.907714004/h 확인. gcp1의 과거 제3자 가격으로 비용 채택 관문을 대신하지 않았다.
