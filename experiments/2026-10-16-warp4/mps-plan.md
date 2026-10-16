# 공유 L4의 private MPS 진단

공식 [MPS 개요](https://docs.nvidia.com/deploy/mps/latest/index.html), [Quick Start](https://docs.nvidia.com/deploy/mps/latest/quick-start.html), [architecture](https://docs.nvidia.com/deploy/mps/latest/architecture.html)를 2026-10-16 열람했다. 여러 프로세스가 각자 CUDA context를 쓰면 GPU 작업이 time slice되고, MPS는 여러 client의 동시 GPU 작업을 지원한다. 작은 world 배치에서 공유 비용을 줄일 수 있다는 **후보 가설**이며, 관측한 지연의 인과 원인으로 확정하지 않는다.

현재 non-MPS prefix의 N4는 nv222/active110/nvmax128, .5SIM초의 physics100.6657초였다. 이것은 초기화89.5초와 별개이고 shared-load이며 정상상태나 SIM초/$ 판정이 아니다. 추가 .4초 quiet setup 뒤에도 active110/nvmax128이었다. 물리·noslip10·iterations80·질량·마찰·카메라·교사를 바꾸지 않는다.

`mps_shared_v1`은 기본 OFF인 별도 runtime cohort다. `CUDA_MPS_PIPE_DIRECTORY=/home/ugrp/ugrp-sim/runs/warp4/mps/pipe`와 별도 log만 warp4의 새 client에 설정한다. GPU compute mode는 Default 그대로이고 다른 작업의 환경·PID·context를 수정하지 않는다. private control daemon/server PID와 client PID를 기록하고, 종료 후 자기 client가 모두 끝났을 때 자기 pipe의 daemon만 종료한다. 기존 non-MPS 원본은 보존하고 새 cohort와 합산하지 않는다. 실제 client 연결·성공·처리량 검증은 실행 결과에 따로 기록한다.
