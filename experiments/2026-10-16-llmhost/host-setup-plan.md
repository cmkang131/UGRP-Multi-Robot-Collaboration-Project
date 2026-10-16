# L4 호스트 준비안 — 미실행, 조정자 승인 뒤

2026-10-16 읽기 조회에서 Docker 미설치, NVIDIA container runtime 있음,
기존 유휴 timer active, root 135 GiB 중 109 GiB 사용·27 GiB 여유를 확인했다.
가중치 두 벌만 34.29 GiB이며 컨테이너도 추가 공간이 필요하다.
현재 공유 작업 때문에 정리·패키지 설치·디스크 변경·GPU 기동을 하지 않았다.
CPU gcp2 원본은 별도로 받는다. 빈 GPU만 생겨도 즉시 실행 가능한 상태는 아니다.

조정자가 비용/유휴/예산과 GPU 독점을 확인한 뒤 아래 **별도 데이터 디스크 + Docker**
준비안을 적용할 수 있다. 기존 root 파일이나 다른 작업 원본은 삭제하지 않는다.
추가150 GB는 두 artifact 36.82 GB + 컨테이너/임시 공간 + 문서의50 GiB 여유를
담는 계획 용량이다(사용자 확정 사양 아님). 디스크 과금은 VM 정지 후에도 남으므로
[공식 디스크 요율](https://cloud.google.com/compute/disks-image-pricing)로 별도 검토한다.
이 작업에서는 만들지 않았고 trial 비용 산식에도 포함하지 않았다.

리뷰용 명령(아직 실행하지 않음):

```sh
gcloud compute disks create ugrp-llmhost-data-gcp2 --size=150GB --type=pd-balanced --zone=asia-northeast3-a --account changmin5781@gmail.com --project ugrp-sim-b-1014
gcloud compute instances attach-disk ugrp-act-l4-gcp2 --disk=ugrp-llmhost-data-gcp2 --device-name=llmhost-data --zone=asia-northeast3-a --account changmin5781@gmail.com --project ugrp-sim-b-1014
```

새 디스크만 `/dev/disk/by-id/google-llmhost-data`로 식별한다. 조정자는 실제 disk ID와
기존 filesystem/마운트가 없는지 확인한 뒤 새 장치만 포맷하여
`/home/ugrp/ugrp-sim/llmhost`에 마운트·영구 mount 설정을 한다. 기존 디스크는 포맷하지 않는다.
Docker의 data-root도 이 디스크의 `docker/`로 두고 모델은 `models/`로 나눈다.
서버에는 model token·HF cache 인증 파일을 넣지 않는다.

[Docker Ubuntu 공식 설치](https://docs.docker.com/engine/install/ubuntu/)에 따라 서명된
apt 저장소의 Docker Engine을 설치한다. `nvidia-container-runtime`이 이미 있지만,
`nvidia-ctk` 유무와 toolkit 버전을 확인하고
[NVIDIA 공식 설정](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)을
따른다. driver/CUDA를 자동 교체하지 않는다. Docker daemon 재시작과 장치 검사는
다른 GPU 작업 종료·조정자 승인 뒤만 한다. ugrp가 Docker를 실행할 권한을 확인한다.

승인 후에도 먼저 CPU 작업만 수행한다:

1. Docker image를 digest로 pull하고 `docker image inspect`의 버전/크기를 기록한다.
   이때 컨테이너를 `--gpus`로 실행하지 않는다.
2. 자기 파일만 CPU gcp2→Mac→L4로 전송하고 전체 SHA를 검증한다.
3. 남은 디스크·기존8h STOP·idle timer·budget-stop·임대·다른 프로세스를 다시 확인한다.
4. `llmhost_trial`을 실행한다. GPU 점유는 조정자 승인에만 따른다.

현재 `llmhost_ctl.start`는 Docker 권한과 디스크 여유가 없으면 중단한다. 호스트 준비를
자동 우회·강행하거나 다른 참여자의 파일을 지워 통과하지 않는다.
