# warp9 참고 자료 — 2026-10-16 열람

두 번 막힌 처리량 문제는 새 실험 전에 공식 자료부터 조사했다. 원문 URL·조회한 main SHA·파일 SHA-256은 [sources.json](references/sources.json)에 있다. 웹 문서 403/구 경로 404도 남겼고 공식 저장소의 같은 문서 원문으로 보완했다. 설치본은 gcp3 MuJoCo Warp **3.16.0 / Warp 1.15.0**이다. 최신 main API를 설치본 지원으로 간주하지 않는다.

| 자료 | 실제 읽은 범위와 적용 |
|---|---|
| [MJWarp 공식 문서](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html), [원문](references/mujoco-doc__mjwarp__index.rst.txt) | CUDA graph, 버퍼 크기, sleeping/island·compact solver, overflow, batch rendering. nconmax/njmax는 계산·메모리 크기다. 실제 최대값과 overflow를 먼저 재고 조절해야 한다. NoSlip·dt·solver 설정은 이 작업에서 변경하지 않는다. sleeping 정책·nvmax는 R3 후보를 유지하고 넘침을 오류로 처리한다. |
| [공식 testspeed](https://github.com/google-deepmind/mujoco_warp/blob/c384ac51df67eb92ab7657cc472ff7494dc036bf/mujoco_warp/testspeed.py), [_src/cli.py](references/mjwarp-mujoco_warp___src__cli.py.txt) | 함수별 graph capture, JIT 시간 분리, nworld×nstep의 처리량, contact/constraint 분포와 overflow. 렌더 모드는 refit+render와 physics를 구분한다. 첫 0.3 SIM초만으로 운반 성공이나 첫30 속도를 주장하지 않는다. |
| [공식 benchmark suite](https://github.com/google-deepmind/mujoco_warp/blob/c384ac51df67eb92ab7657cc472ff7494dc036bf/benchmarks/README.md) | 모델별 nworld·nconmax·njmax를 별도 설정한다. 예시 8192세계를 우리 장면의 효율 근거로 쓰지 않고 요청한 1·4·16·64세계를 직접 잰다. |
| [NVIDIA Warp profiling](https://github.com/NVIDIA/warp/blob/c518321b157e5a4648fc3bbd08612476dd1d6ed1/docs/user_guide/execution_and_performance/profiling.rst) | CPU 예약 시간과 CUDA 완료 시간이 다르다. 계측용 CUDA event 구간·completion wait·복사 바이트/호출을 따로 기록한다. event 구간은 커널 busy 합계가 아니다. 계측의 추가 동기화가 overlap을 바꾸므로 실운전 속도는 별도 무계측 실행으로 확인한다. |
| [NVIDIA Warp concurrency](references/warp-docs__user_guide__execution_and_performance__concurrency.rst.txt) | GPU launch는 비동기, pageable host copy는 동기이며 pinned memory가 비동기 전송의 조건이다. 매 세계 전체 배열 readback·카메라별 wait·재할당을 우선 계수한다. 전송을 줄일 때 같은 GPU 상태의 export/RGB 동등성을 별도로 확인한다. |
| [MuJoCo Playground 공개 렌더 benchmark](references/playground-mujoco_playground__experimental__madrona_benchmarking__benchmark.py.txt), [훈련 실행기](references/playground-learning__train_jax_ppo.py.txt), [wrapper](references/playground-mujoco_playground___src__wrapper.py.txt) | render_batch_size=num_envs, batched inference와 env.step을 JIT scan에 넣고 결과 의존 token을 남긴다. compile을 분리하고 완료를 기다린 뒤 FPS를 계산한다. 우리 Python 제어는 이와 달리 호스트 왕복이 있으므로 render만의 GPU FPS와 E2E 처리량을 분리한다. Madrona로 교체하거나 해상도·FOV·기록 주기를 줄이지 않는다. |

## 측정 설계

- 고정 R3 장면 하나의 명시적 복제를 1·4·16·64세계로 측정한다. 독립 성공 시행 수로 세지 않는다. 원래 R3 두 모델 그룹·N16 임무는 별도 검증한다.
- `command_python`, `physics_graph`(event/host submit/wait), 렌더 refit·extract·복사·CPU 변환, 평가 export의 D2H 횟수·바이트를 구분한다. setup/JIT/초기 parity 렌더는 본 측정에서 제외한다. 계층 total과 하위 phase를 중복 합산하지 않는다.
- setup warmup이 물리 상태를 바꾸지 않도록 기존 초기 상태 복원을 유지한다. 재현은 커밋 SHA·queue·임대·host·GPU process 증거와 연결한다. GPU 임대가 없거나 다른 GPU PID가 있으면 시작하지 않는다.
- 병목 표를 만든 뒤 가장 큰 원인부터 기본 off 후보로 수정한다. 렌더/평가 배열 캐시, graph 크기, 버퍼 변경을 아직 성능 개선으로 주장하지 않는다. n4 제어 + L4 물리 소유자 분리도 별도 대상이다.
