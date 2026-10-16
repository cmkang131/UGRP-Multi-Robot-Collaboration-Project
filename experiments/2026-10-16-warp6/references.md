# warp6 CUDA 700 / SIGSEGV 참고 자료 (2026-10-16 열람)

최초 오류와 MPS의 후속 전파를 분리한다. 아래 사례를 이번 실행의 원인으로 확정하지 않는다. 설치본은 MuJoCo/MJWarp3.16.0, Warp1.15.0이며 문서 최신판과 다를 수 있다.

| 일차 출처 | 확인한 내용과 이번 검사 |
|---|---|
| [MJWarp batch·overflow·graph 문서](https://mujoco.readthedocs.io/en/stable/mjwarp/index.html) | nconmax는 세계당 기대 접촉 수이고 전체 용량은 nworld 곱, njmax는 세계별 제약 상한이다. XML size 값 대신 put_data 인자를 확인한다. overflow 비트 및 실제 nacon/nefc/awake 수를 기록한다. 초기 상태만으로 배정한 버퍼가 실행 중 충분한지는 별도 확인한다. graph는 여러 커널을 묶으므로 비동기 오류의 보고 지점과 최초 오류 커널은 다를 수 있다. |
| [MJWarp #1711](https://github.com/google-deepmind/mujoco_warp/issues/1711), [수정 제안 #1718](https://github.com/google-deepmind/mujoco_warp/pull/1718) | 다중 프로세스 부하의 CUDA illegal access 보고. nworld4096/500, MPS 없음, graph 없음의 사례이며 우리 N4/6/2와 다르다. 사용자 추정 data race를 확정 원인으로 취급하지 않는다. 유지자가 constraint/contact/sensor overflow의 경계 검사 제안을 연결했다. 설치 소스가 이 변경을 포함하는지 확인한다. |
| [MJWarp #458](https://github.com/google-deepmind/mujoco_warp/issues/458) | SAP_TILE의 _sap_range에서 sanitizer illegal read 보고, graph 없이도 발생. 큰 버퍼만으로 해결되지 않았고 NXN/SAP_SEGMENTED에서는 보고자가 재현하지 못했다. 우리 broadphase와 최초 커널을 대조한다. |
| [MJWarp #1104](https://github.com/google-deepmind/mujoco_warp/issues/1104) | 동적 primitive와 정적 mesh 충돌의 segfault 보고, nconmax/njmax 확대 뒤에도 지속. 버퍼·graph·MPS 중 하나로 미리 단정할 수 없다. |
| [NVIDIA Warp #441](https://github.com/NVIDIA/warp/issues/441) | VBD self-contact CUDA graph 실행의 error700 사례. 우리 MJWarp solver와 다르므로 graph 진단의 참고만 한다. |
| [Warp debug 안내](https://nvidia.github.io/warp/v1.17/user_guide/debugging.html) | mode=debug는 배열 경계 확인과 CUDA 줄 정보를 켠다. verify_cuda는 launch 뒤 동기화하지만 graph capture와 동시에 쓸 수 없다. 우선 R3 graph·배치 설정을 유지하고 Compute Sanitizer memcheck로 최초 커널을 찾는다. 필요하면 별도 비그래프 진단을 사용한다. |
| [NVIDIA MPS architecture](https://docs.nvidia.com/deploy/mps/latest/architecture.html) | fatal GPU fault는 영향을 받은 GPU의 다른 client에 전달될 수 있고, 발단 client를 식별하지 않은 채 보고될 수 있다. 동시 종료는 최초 세 프로세스가 모두 같은 코드 결함을 가졌다는 증거가 아니다. gcp3 GPU에 다른 CUDA client/MPS가 없음을 실행 직전에 확인한다. |

R3 거부 분포의 가장 큰 항목은 release8세계 native SIGSEGV, 그다음 빔4세계 CUDA700이다. 양쪽 모두 HOST_ERROR이며 물리 실패가 아니다. 최초 fault 커널을 확보하기 전 임의 용량 배율·수용 허용오차를 추가하지 않는다. 같은 결함이 3라운드 남으면 중단한다.

GitHub API 직접 확인: #1718은 OPEN, merged=false, merge_commit_sha=null이다. 제안 patch의 존재를 설치본에 이미 반영됐다는 뜻으로 쓰지 않는다.

- [NVIDIA Xid31 문서](https://docs.nvidia.com/deploy/xid-errors/archive/index.html), [현재 Xid 분석 지침](https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html): MMU의 잘못된 주소 접근이며 애플리케이션·드라이버·하드웨어 원인을 구분해야 한다. PID는 문제 흐름 식별에 도움이 되지만 실패 커널 이름은 아니다. sanitizer/cuda-gdb와 반복 양상을 권한다. 새로 회수한 `gcp2-r3-kernel-evidence.txt`는 Xid31 PID73446=빔과 같은 시각 release PID73447/73448의 libcuda SIGSEGV를 기록한다. 최초 버퍼·커널 원인 확정은 아니다.

- [MJWarp SAP API](https://mujoco.readthedocs.io/en/3.13.0/mjwarp/api.html): sweep-and-prune는 모든 geom쌍을 검사하는 NXN보다 큰 장면에 적합할 수 있다. 새로 엔진을 쓰는 대신 공통 backend의 기존 SAP_SEGMENTED 토글을 flow CLI에 기본off로 연결한다. 먼저 컴파일 뒤 폐기되는 한 물리step의 Warp1.15 ScopedTimer/TIMING_KERNEL 원본으로 비용순위를 기록한다. broadphase가 지배적이라는 가설을 확인하기 전 개선/원인으로 주장하지 않는다. 설치API와 코드SHA는 실제환경에서 확인했다. 접촉·형상·마찰·timestep·교사성공식을 변경하지 않는다.
