# warp8 작업 공간 수정 근거 (2026-10-16)

- [MJWarp compact solver / nvmax](https://mujoco.readthedocs.io/en/stable/mjwarp/index.html#compact-solver): nvmax는 세계당 최대 활성 DOF 작업 공간이다. 미지정 기본값은 전체 nv다. 초기 활성 수보다 나중 각성이 많아질 수 있으므로 초기 count를 전체 상한으로 쓰지 않는다. 문서의 solver/sleep tolerance를 줄이는 제안은 이번 작업에 적용하지 않는다.
- [MJWarp overflow detection](https://mujoco.readthedocs.io/en/stable/mjwarp/index.html#overflow-detection): 고정 할당을 넘기면 동작이 미정의이므로 overflow를 숨기거나 계속 실행하지 않는다. 설치본 types.py는 NVMAX=1<<7(128), island.py1132–1140은 실제 요구 DOF가 nvmax를 넘으면 이 비트를 쓴다.
- 설치본 io.py1383의 `_nvmax_pad`는 augmented column과 기존 dense tile 크기에 맞춘다. io.py1791–1797은 compact tolerance를 nv/nvmax_pad로 정규화해 full-model 기준과 맞춘다. 원본 SHA는 [nvmax-evidence.json](nvmax-evidence.json)에 있다. 최신 웹 문서를 설치본과 동일한 버전으로 간주하지 않는다.

R1은 model nv222 / 초기110 / 할당128(nvmax_pad144)이었고, 마지막 step226에서 활성156과 world008의 bit128을 기록했다. seed8318706이다. 새 기본off `full_active_dof_workspace_v1`는 임의 배율 없이 모델의 정확한 전체 nv222를 할당한다. 이는 모든 DOF가 깨어도 담을 수 있는 구조적 상한이다. 각성·sleep policy·NoSlip10·dt·접촉·마찰·m.opt의 tolerance/iterations는 바꾸지 않는다. upstream compact 정규화는 그대로라 새 pad와 파생 ctol/cls_tol은 기록한다. padding 차이로 계산 바이트가 같다고 주장하지 않으며 R1과 새 관문은 합산하지 않는다.

수정 전에 R1 거부표를 저장하고 성공1개와 HOST_ERROR1개의 전체2Hz·마지막10SIM초10Hz를 직접 봤다. 초기에 만든 파생 full2Hz 개요에는 startup0.5SIM 시각 기준 오류가 있어 native NPZ로 수정했다. 수정본은 evaluator/NPZ 중복175행 중174, 실패221행이 비트 단위 일치한다. 독립 physical hold 재계수는 원본175행으로3초이며 영상 수정과 무관하다. 실패는 world008의 r1이 다른 로봇 쪽으로 접근한 뒤 GPU 배치가 중단되는 순서다. 어느 접촉이 각성을 일으켰는지는 아직 확정하지 않는다.
