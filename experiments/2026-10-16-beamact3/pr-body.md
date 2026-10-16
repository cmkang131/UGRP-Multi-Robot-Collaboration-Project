beamact2는 명령 유지 구간에서 전체 휠 오차의76.3%가 생겼고, 허용된 wheel/pulse 이력을 모두 가린 상태에서 학생0/20이었다. 기본 off ACT 후보에 wheel3분류와 최근5개 자기 명령 이력을 넣고, A(이력 유지)/B(wheel·pulse 마스크)를 같은 데이터·분할·시드로 총20k씩 학습한다.

- 학습 core `4747c4144` 고정, beampair8 TRAIN166/validation19·기존 보류20 유지. A/B·기존 모델 결과는 합산하지 않는다.
- A smoke300: 저장/재로딩 `torch.equal` 통과, shared-L4309.48초. A main 진행 중; B·오프라인 MAE·학생20·Release는 미완료다.
- Mac 비물리16pass/2skip, GCP2 L4/CPU 각각17pass/1skip. CI 별도 진행 중.
- GPU는 warp3와 공유하며 임대·부하·8h/idle/budget-stop을 유지한다. 디스크100→140GB 확장, 여유52.5GB 확인. CPU 학생은16동시·전체40이하이며 reloc20을 유지한다.

[실험/범위](experiments/2026-10-16-beamact3/README.md) · [smoke 근거](experiments/2026-10-16-beamact3/A-smoke-summary.json) · [자원 예산](experiments/2026-10-16-beamact3/resource-plan.json). 아직 학생 개선·기본 채택을 주장하지 않는다.

참고: [PyTorch CE](https://docs.pytorch.org/docs/2.14/generated/torch.nn.CrossEntropyLoss.html), [고정 ACT](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/modeling_act.py). upstream 웹 조회 실패 시 L4 설치 원문을 직접 확인했으며 ACT encoder/decoder/CVAE/valid×14 분모를 보존했다.
