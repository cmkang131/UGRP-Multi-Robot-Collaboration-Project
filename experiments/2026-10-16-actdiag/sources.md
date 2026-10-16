# ACT 공개 구현 대조 (2026-10-16 원문 확인)

|항목|Zhao 2023 / 공식 ACT|LeRobot 공개 기본값|이번 빔 ACT / ACT15|
|---|---|---|---|
|청크|논문 Table III·공식 sim 예제 100|100|8|
|제어 주기·청크 시간|ALOHA 50Hz, 100이면 2초; 프로젝트 사이트 실물 영상 설명은 90|환경 주기에 따름|10Hz, 0.8초|
|재추론·앙상블|temporal ensembling 선택 가능, 공식 코드 계수 0.01|기본 n_action_steps=100, ensemble=None; 켜면 n_action_steps=1|n_action_steps=8, ensemble=None|
|KL / 잠재 변수|β=10, 배포 시 z=0|10, use_vae=True|10, 배포 시 z=0|
|구조|ResNet18, dim512, heads8, FF3200|같음; decoder 1층(원 코드 실효 동작 맞춤)|같음|
|배치·학습률|8 / 1e-5|1e-5 정책 기본값, 문서 batch8 예시|8 / 1e-5|
|자료 규모|작업당 50개 시연 사례; 보편적인 충분조건은 아님|문서 50개 사례|빔 성공185쌍, TRAIN166시드/60,023행; ACT15 TRAIN22,852행|
|학습 길이|공식 sim 예제 2,000 epochs; 실물은 더 길게 제안|문서 100k steps 예시|고정 마지막 10k steps|
|행동|연속 목표 관절 위치|사용자 정의 연속 action + L1|휠4·펄스폭4·PWM5 + 별도 balanced done BCE|
|상태|측정 관절 + 여러 카메라|선택적 observation.state|자기 발행 명령·시계·고정 지시만; 빔 wheel/pulse 이력128개 scalar는 TRAIN 평균으로 마스킹|
|이미지|실물 4개 시점|ResNet18 / ImageNet 초기화 기본값|자기 카메라 과거4장, 각240×320을 480×640 몽타주로 합침|
|정규화|행동/관절 mean/std, std 바닥 .01; 이미지 ImageNet 변환|STATE/ACTION/VISUAL mean/std 기본|TRAIN 고유 행 통계·std 바닥 .01; 이미지 ImageNet mean/std, 동일 온라인 변환|

`chunk=100`을 10Hz에 그대로 옮기면 10초가 된다. 공개 설정의 숫자와 물리적 시간 범위를 구분해야 한다. 공식 코드의 real-data -1 tick 보정도 시뮬레이션에 임의 적용하지 않는다. 이 데이터의 t→t+k 정렬은 원본과 별도 검사했다.

모델 config의 `pretrained_backbone_weights=None`만 보고 무작위 백본이라고 판단하면 안 된다. 실제 smoke 학습은 `make_policy(pretrained=True)`에서 ImageNet 가중치를 직접 넣고, main은 smoke의 전체 모델·optimizer·RNG를 복원한다. 설치된 pinned LeRobot은 `89236ea0f4f81a81ca566081e20dd1ff5f823cbe`이며 웹 main과 같은 버전이라고 가정하지 않았다.

출처:

- [Zhao 등 원 논문, IV절·Appendix D·Table III](https://arxiv.org/html/2304.13705v1)
- [공식 ACT README: 50시연·학습 예시·temporal_agg](https://github.com/tonyzhaozh/act)
- [공식 ACT 데이터 시간 정렬·정규화](https://github.com/tonyzhaozh/act/blob/main/utils.py)
- [공식 ACT 추론·temporal aggregation](https://github.com/tonyzhaozh/act/blob/main/imitate_episodes.py)
- [ALOHA 프로젝트: 50Hz·청크90 실물 사례와 카메라](https://tonyzhaozh.github.io/aloha/)
- [LeRobot ACT 설정 원문](https://github.com/huggingface/lerobot/blob/main/src/lerobot/policies/act/configuration_act.py)
- [LeRobot ACT 사용 문서](https://huggingface.co/docs/lerobot/act)
- [BeT: 이산 행동과 연속 보정으로 다봉 행동을 모델링하는 선행 방법](https://arxiv.org/abs/2206.11251). ACT를 BeT로 교체하자는 제안이 아니라, ACT 출력 표현을 검토할 참고 근거다.
- [Causal Confusion in Imitation Learning](https://arxiv.org/abs/1905.11979), [Fighting Copycat Agents](https://arxiv.org/abs/2010.14876). 높은 이전 행동 일치만으로 인과 혼동이 증명되지는 않는다.

고정 SHA의 GitHub raw URL은 웹 도구에서 열리지 않았다. 대신 실제 L4 설치 파일 경로·SHA·direct_url·forward 코드를 `runtime-audit.json`에 남겼다. 현재 설치의 패딩 L1 분모는 유효 horizon 수×14이며, 프로젝트 done L1 제거 분모와 일치한다. 과거 학습 당시 라이브러리 파일 전체의 별도 봉인 목록은 없어 완전한 당시 바이트 감사로 확대하지 않는다.
