# beamact3 — ACT wheel 분류·compact history A/B (진행 중)

actdiag 권고를 같은 beampair8 dataset-v1과 beamact2 분할로 재학습한다. 원 데이터 archive SHA `739a9fae…e251`, split manifest SHA `a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd`이다. TRAIN166시드60023행 / validation19시드6908행 / 보류20시드8329000..8329019를 유지한다. 원본은 압축된 채 보존하고 metadata-only hardlink view로 읽는다. 데이터·정규화·시드·cold-start 분포·학생 실행기는 바꾸지 않는다.

A/B 모두 기본 off 후보: wheel별 `−0.35/0/+0.35` 3분류, shared ACT decoder의 연속 pulse/PWM, 기존 balanced completion BCE와 CVAE KL10. 동일 ImageNet 초기화·seed20261015·batch8·chunk8·10Hz·최종20000step 고정(300 smoke 포함). 검증/보류 성능으로 checkpoint를 선택하지 않는다. wheel CE는 유효 label의 표준 비가중 평균, 계수1이며 기존 done 계수1과 같은 단위 그룹 가중을 사용한다. upstream의 wheel L1 네 항만 정확히 제거한다. pulse/PWM은 같은 decoder 특징에 조건화되고, wheel0의 pulse0은 기존 명령 투영이 적용한다. 수제 근거리 경로·persistence 대체는 없다.

compact history는 최근5개 자기 발행 명령을 그대로 보존한다. 근거: actdiag의 unique TRAIN same-sign nonzero wheel run8293개 중앙5틱(0.5초), p25=1/p75=18. 원래16개 중 오래된11개의 normalized14차원을 TRAIN mean0으로 가린다. 전체 state252차원과 고정 번호표·시계·자기 RGB4장은 그대로다. A는 최근5개 명령 전체를 쓴다. B는 같은 상태에서 wheel/pulse40 scalar만 더 가리고 PWM/age는 보존한다. act16a training-plan의 해당 A/B는 whole-history dropout0이며 여기서도0이다. 따라서 A/B 차이는 recent wheel/pulse 마스크다. 기존 beamact2와의 차이는 head/history/20k의 묶음이며 단일 인과 효과로 주장하지 않는다.

학습은 gcp2 프로젝트 `ugrp-sim-b-1014`의 기존 `ugrp-act-l4-gcp2` L4를 warp3와 공유한다. 속도판정에 쓰지 않고 shared-load·GPU/프로세스·임대를 기록한다. 각 조건 유한 process <=7h, VM8h·idle20분·budget-stop 유지. 이미 시작된 VM 창이 모자라면 checkpoint+optimizer+sampler/torch/CUDA RNG로 같은 소스를 재개하고 HOST interruption을 별도 기록한다. 다른 작업을 정지하거나 VM 상한을 갱신하지 않는다. 비용 정지가 확인되면 새 실행·재시작을 금지하고 ops-alert에 BUDGET을 쓴다. gcp1 접근·Mac 물리/렌더/학습/GUI·모델 키 전달 없음.

평가 순서: final20000 저장/재로딩 → TRAIN/validation 전체·8틱 재추론·안정/전환·단계별 decoded MAE vs raw persistence → 번호표만 교환한 initial/first-approach 오프라인 출력 → gcp2 CPU 보류20 폐루프(16동시·전체40이하) → 원본재계수·퍼널·감사·실패영상/6장 이상 → 실패 모델도 새 Release 보존·재다운로드/전체hash/모델로딩. A/B 결과는 합산하지 않는다. 보류20은 beamact2에서 이미 본 비교 세트로 새 확증 자료가 아니다. 실패 직전10SIM초 자기 RGB10Hz ring은 기존 기록 옵션을 그대로 쓴다. 거부 원본은 [직전 분포/퍼널](prior-rejection-table.json)에 있다. 접근12·정렬7·파지1이므로 head/history의 전역 적합도와 접근/끝 선택을 먼저 검증한다.

Gemma 공급가50% 인상 경보는 시작 시 확인했다. 이 경로는 판단LLM 호출0이며 새 LLM 배치는 제출하지 않는다. 결과는 로컬 프로젝트·GitHub에만 기록한다.

기준 검증: Mac 비물리16pass/2skip (분류 loss/serializer 실제 연산은 GCP2에서 수행). 학습·폐루프·배포 완료 전에는 성공 수를 채우지 않는다.

참고: [PyTorch CrossEntropyLoss](https://docs.pytorch.org/docs/2.14/generated/torch.nn.CrossEntropyLoss.html)의 class-index 표적/유효행 평균; [고정 LeRobot ACT](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/modeling_act.py)는 웹 열람 실패, 대신 L4 설치 원문을 직접 확인해 한 번의 forward와 valid×14 분모·동일 decoder 출력 head를 유지했다. [ACT 원 논문](https://arxiv.org/abs/2304.13705)은 기존 구조의 출처이며 wheel CE의 성능을 보증하지 않는다. actdiag 원문을 [로컬 참조](actdiag-reference.md)로 보존했다.
