# simalt4 — MJWarp 파지 회복, 전체 동등성 미통과

**PARITY_FAIL / ready=false.** 기본 off인 `legacy-plane-v1`로 파지 유지 **30/30 표본**, 높이 차 **0.01584mm**, 무부하 끝점 **3/3 통과**까지 회복했다. 그러나 전체 파지·놓기·후퇴 trace 뒤 몸체 끝점 차이가 **11.508mm > 5mm**여서 확대하지 않았다. 물리값과 운영 backend는 바꾸지 않았다.

[요약](summary.json) · [거부 분포·관문](rejection_table.json) · [스텝 표 발췌](step-comparison-excerpts.csv) · [전체 25개 스텝 표 위치·SHA](evidence/remote/step-tables.json) · [영상 타임라인](playback-review.md) · [재현](reproduce.md).

## 결과

같은 L4의 C3.12/C3.13/C3.16과 고정 개발 MJWarp를 비교했다. 30은 같은 명령 trace의 3초를 10Hz로 평가한 표본 수이며 독립 30회 성공률이 아니다. 5mm/2°/2mm는 사용자의 원인 탐색 제안값이다. 완화하거나 기존 임무 성공 기준으로 승격하지 않았다.

| 조건 | 양쪽 접촉 / 30 | 최소 들림 | grip overflow | 판정 범위 |
|---|---:|---:|---:|---|
| C3.12 양성 기준 | 30 | 70.8346mm | 해당 없음 | 원래 trace 재현 |
| C3.13 버전 대조 | 0 | 사실상 0 | 해당 없음 | C3.12와 감사 배열 48개 동일 |
| C3.16 같은 버전 대조 | 0 | 사실상 0 | 해당 없음 | 버전 변경 자체도 실패 |
| R1 Warp, njmax128 | 미측정 | hold 미도달 | 204스텝 | 14.5 SIM초에 HOST_ERROR |
| R2 Warp, njmax256 | 0 | 0.00015mm | 0/173,600스텝 | 버퍼 확대만으로 파지 회복 안 됨 |
| R3 Warp, njmax256 + legacy Plane–Mesh | **30** | **70.8505mm** | **0/173,600스텝** | 파지 회복, 전체 끝점 불통과 |

R3 양쪽 패드 최소 법선력은 **5.2024N / 5.2021N**, C3.12는 5.2030N / 5.2026N이다. 높이 차 최대는 0.01584mm로 2mm 제안값을 통과한다.

| R3 대 C3.12 | 몸체 끝점 위치 차 | 몸체 각도 차 | 제안값 |
|---|---:|---:|---|
| 전진·정지 | 0.0063mm | 0.0015° | 통과 |
| 측면·정지 | 0.0143mm | 0.0147° | 통과 |
| 회전·정지 | 0.1259mm | 0.0931° | 통과 |
| 전체 grip trace | **11.5082mm** | 0.2420° | **불통과** |

grip의 상자 끝점은 3.2691mm / 0.3166°다. 남은 몸체 위치 차이는 하강 단계 **48,834스텝 / 12.2085 SIM초**에 처음 5mm를 넘고, hold 끝 6.737mm, 전체 끝 11.508mm다. 후퇴 이후만의 문제로 좁힐 수 없다. [단계별 오차](evidence/remote/residual-location.json).

3라운드 한도에서 종료했다. **두 로봇+빔과 N16/64/256 처리량은 미제출**이며, 수정 전 simalt3의 속도·비용 배율을 이번 후보에 재사용하지 않는다. 관측 RGB의 부분 투명도 문제도 이번에 해결한 것으로 보고하지 않는다.

## 확인한 원인과 남은 경계

1. **Plane–Mesh 접촉 선택 변경의 기여를 확인했다.** C3.12와 C3.13은 감사한 모델 배열 48개가 같아도 같은 tape에서 파지 30/30 대 0/30이었다. 공식 3.13 변경 기록은 Plane–Mesh 재작성을 명시한다. Warp만 C3.12의 support vertex·graph 이웃 선택으로 바꾸자 무부하 응답과 파지가 회복됐다. 원래 `maxplanemesh=3`, `tolplanemesh=.3`을 그대로 옮겼으며 새로 맞춘 상수가 아니다. 첫 Plane–Mesh 접촉 수 4개, 전진/측면 최대 8/6개도 C3.12와 맞았다. 모든 버전 변경을 bisect한 유일 원인 증명은 아니다.
2. **새 dense replay에서 버퍼 부적합을 확인했다.** 첫 NEFC overflow는 57,797스텝 / 14.44925초, 당시 nefc131 대 상한128이었다. C3.16 전체 최대129, Warp prefix 최대134를 근거로 다음 2의 거듭제곱256을 썼다. nconmax32는 유지했다. R2/R3의 모든 grip 스텝에서 overflow0을 확인했다.
3. **원래 simalt3의 실패를 overflow 탓으로 단정하지 않는다.** 이번 C 재생은 simalt3의 10Hz 상태와 전부 비트 일치했다. Warp는 첫 표본부터 달랐고 grip 공통14.5초에서 몸체 위치 차 최대5.021mm였다. 로거 추가와 GPU 비결정성의 기여를 분리하지 않았다. 따라서 초기에 쓴 “이전 10Hz 검사에서 넘침을 놓쳤다”는 표현은 철회한다. [이전/새 재생 대조](evidence/remote/inherited-vs-dense-detailed.json).
4. **같은 XML의 관절 감쇠가 버전 사이에서 달랐다.** C3.16의 팔 4개 `actuator_biasprm[:,2]`가 C3.12와 다르며, 공식 3.15 `dampratio` 계산 변경과 부합한다. 이 값을 수정하거나 원래 값으로 덮어쓰지 않았다. geom size/quaternion/mesh vertex 차이의 body-frame Hausdorff 최대는 8.883e-10m로 기록했다. [모델 감사](evidence/remote/model-version-differences.json), [감쇠 값](evidence/remote/joint-damping-drift.json).

남은 11.508mm 오차가 감쇠 차이만으로 생겼다고 확정하지 않는다. solver 수렴·float32의 잔여 기여도 미분리다. 관절 이득을 맞추거나 물리값을 바꾸려면 **C와 Warp에 공통으로 고정한 별도 물리 프로필과 새 기준 검증**이 필요하며, 이번에는 만들지 않았다. 현재 판정은 “파지 회복, 엄격한 전체 동등성 실패”다.

## 구현·검증 범위

- `scripts/simalt_step_probe.py`: `--enabled` 필수, Linux gcp2 호스트 확인 후에만 simulator를 import한다. 모든 물리 스텝의 패드–상자 접촉 수, 접촉/제약 버퍼 사용, overflow, 최소 접촉 거리, 법선/접선 힘, 패드 관절, qpos/qvel을 기록한다. 접촉은 해당 step의 force 평가 시점, qpos는 적분 직후 값이며 두 엔진에 같은 방식을 썼다.
- `--dense-capacity-v1`, `--backend-mode legacy-plane-v1`는 **기본 off**다. 이전 옵션은 baseline이다. 마찰·solref/solimp·질량·dt·noslip10·관절 이득을 변경하지 않는다. mesh rbound와 norm(size)의 정확한 일치를 확인하지 못하면 호환 경로를 거부한다.
- 기록 전용 `--record-own-rgb`를 R2/R3에 켰다. C rasterizer가 별도 MjData에서 자기 카메라를 10Hz·최대100장 ring으로 기록하며 제어는 읽지 않는다. 각 grip 종료 ring은 100장/약1.89MB다. 실패 시점 검토에는 보존한 4kHz 상태의 C 사후 복원도 사용했다. Warp RGB 정보 동등성과 구분한다.
- `scripts/simalt_step_analysis.py`: 같은 MuJoCo3.16 C 대 Warp와 C3.12/3.13/3.16 버전 대조를 분리한다. **25개 표, 합계 1,387,600행**을 zstd 복원 전체 SHA 확인 후 보존했다. 원본은 VM에, 발췌만 Mac/Git에 둔다.
- 비물리 검사 **13개 고유 검사 통과**(5+8, 중복 재실행 제외), L4의 legacy kernel **컴파일 전용 검사 통과·physics step0**, 구문 검사·`git diff --check` 통과. PR은 Draft이며 전체 CI 통과는 확인하지 않았다.
- 진단 호출26개: 완료20, HOST_ERROR6, cap_end0. HOST_ERROR는 초기 로거 형식 오류4개(step0), legacy 최초 컴파일 오류1개(step0), 새 R1 NEFC overflow1개다. 추가 설치/검토 도구 오류는 이 파지 표본과 합산하지 않았다. [전체 호출](evidence/remote/jobs.json).

## 고정 입력·소스

- 교사/장면 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`; scene.xml SHA `ad46cd87ef4188daa9a4dbebd79c470fac6f1b3fcb5e5a1fe0d9dfa3c2261849`, fixture.npz SHA `d3548742053aa18ee526297baa2611bb37b32f923b504097dc5a0c17f4184577`.
- native C 로거 `e2c2a4c4f6df401da003e79563eb6c3ef06d11d9`, dense Warp 로거 `4585ac9178d44784f00cce8c6ffb13270e92a56c`, R2/R3 실행 코드 `5ce41464efe3d3687aeecf8ebd7a76dcbeb9dfce`. 각 result에 실제 script/fixture/XML SHA와 argv가 있다. 실행 중 해당 소스 사본을 변경하지 않았다.
- simalt3 설치 재사용: 기록된 MJWarp dev `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148`, MuJoCo3.16.0, Warp1.15.0. io.py SHA는 고정 upstream과 일치했다. 설치의 direct_url commit metadata는 없어서 이번에 패키지 전체 소스 SHA를 새로 확인했다고 주장하지 않는다.
- 발행 명령 tape만 재생했다. 정답·접촉은 평가/검토 전용, 모델 호출·학습·실물 검증0, weld OFF다. 계획/탐색 자체가 없고 실행량은 정수 physics tick/SIM 시간으로 제한했다. wall 상한은 사용자 자원3시간 전용이다.

## 보존·회수·종료

시작 신호를5분 간격으로 확인해25분 뒤 `simalt3:` 줄을 읽고 선행 기록부터 검토했다. 계정 `changmin5781@gmail.com`, 프로젝트 `ugrp-sim-b-1014`, 기존 `ugrp-act-l4-gcp2` 한 대만 사용했다. 첫 프로젝트 API/SSH, 새 VM 생성, Mac 물리·렌더·화면 앱 실행0이다.

원본 `/home/ugrp/ugrp-sim/runs/simalt4/`의 **1,690/1,690 SHA256 PASS**를 모든 writer 종료 뒤 확인했다. [최종 검증](evidence/remote/raw-verification-final.json), [최종 목록](evidence/remote/SHA256SUMS-final). collector가 자기 완료 로그를 쓴 뒤 생기는 차이를 제외한 최종 감사이며, 앞선 provisional 목록은 기록으로 남겼다. raw는 정지한 L4 영속 디스크에 있고 전체 외부 백업이 아니다. 모델 감사는 항목을 확장한 파생 기록이며 초기 44개 검사 결과는 스텝 metadata와 함께 보존한다.

Mac lite308,700bytes SHA, 요약27파일, 검토30파일, 대형 JSON3개의 전체 복원 SHA를 확인했다. [회수 검증](local-transfer-verification.json). 영상은 파일당8MB 이하이며 검토는 [전체2Hz·직전10초10Hz 프레임 띠](playback-review.md)로 직접 했고 MP4 형식/길이는 원격 ffprobe로만 확인했다. 결과는 로컬 프로젝트와 Git에 보존한다.

L4 **TERMINATED** 확인. 실제 시작~정지 **3,092.024초 = 0.85890h**, 사용자/이전 simalt3의 $1.096/h 가정으로 **VM 정가 추정 $0.94135**다. 실제 청구·크레딧 잔액·디스크·네트워크·세금은 미확인이다. 8h STOP·idle20분·Mac의 유한3h 감시는 유지했고 작업 후 감시도 종료했다. 이번 gcp2 사용 중 budget-stop 발동은 없었다. [호스트 증거](evidence/final-host-status.json).

## 참고 자료

- [공식 MJWarp 문서](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html): nconmax/world, naconmax/전체, njmax/world의 구분과 overflow의 undefined behavior. XML size 값 대신 put_data 인자로 용량을 지정한다.
- [고정 README 기능 차이](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/README.md#MuJoCo-API-Compatibility): IMPLICITFAST midpoint/PGS/plugin actuator·sensor 미지원, flex 실험적, noslip은 discrete integrator에서 미지원. 현재 implicitfast·noslip10 경로와 구분한다.
- [공식 XML 옵션](https://mujoco.readthedocs.io/en/latest/XMLreference.html?highlight=touch), [고정 io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py#L433): 기본 Euler/Newton/pyramidal. 실제 장면은 implicitfast/Newton/elliptic, dt.00025, 80/50 반복, tolerance1e-8, noslip10/tolerance1e-6이다. upstream float32용1e-6 clamp를 원래1e-8로 복원했다. margin/gap은0, geom condim3(465개)/4(4개), 패드–상자는3이다. 전역 float64 실행 토글은 고정 API에서 확인하지 못해 미측정이다.
- [충돌 분기](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/collision_driver.py#L47): plane/mesh primitive, box/mesh·mesh/mesh·box/box convex CCD. primitive box SAT 대안은 조사했으나 이번 선택 후보에는 쓰지 않았다.
- [C3.13 Plane–Mesh 변경 기록](https://mujoco.readthedocs.io/en/stable/changelog.html#version-3-13-0-september-8-2026), [C3.12 원본·상수](https://github.com/google-deepmind/mujoco/blob/3.12.0/src/engine/engine_collision_convex.c#L966), [C3.16 원본](https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_collision_convex.c#L1091).
- [C3.15 dampratio 변경 b3dd9e617](https://github.com/google-deepmind/mujoco/commit/b3dd9e617): 다관절 체인의 반사 관성 계산 변경과 낮아질 수 있는 감쇠.
- [이슈1546](https://github.com/google-deepmind/mujoco_warp/issues/1546): float32 world 좌표 GJK/EPA 접촉 누락과 pair-local 해결. [고정 convex 소스](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/collision_convex.py#L842)에 이미 들어 있어 새로 적용하지 않았다.
- [이슈1635](https://github.com/google-deepmind/mujoco_warp/issues/1635): Warp 자체 deterministic 모드에서 convex 접촉이 사라지는 사례. maintainer의 미지원 답변을 확인했고 해당 모드는 켜지 않았다.
- [이슈87 noslip](https://github.com/google-deepmind/mujoco_warp/issues/87), [이슈1517 작은 마찰 NaN](https://github.com/google-deepmind/mujoco_warp/issues/1517), [이슈926 할당/메모리](https://github.com/google-deepmind/mujoco_warp/issues/926). 이번과 같은 파지 미끄러짐을 nconmax/njmax 증설만으로 해결한 사례는 확인하지 못했다.
- [공식 Discussions](https://github.com/google-deepmind/mujoco_warp/discussions)와 grasp/friction/contact 검색에서 같은 장면의 검증된 해결법은 찾지 못했다. 미확인을 “사례 없음”으로 일반화하지 않는다. 다운로드 URL·SHA는 [sources.json](references/sources.json), 진행 메모는 [work-log.md](work-log.md)에 남겼다.
