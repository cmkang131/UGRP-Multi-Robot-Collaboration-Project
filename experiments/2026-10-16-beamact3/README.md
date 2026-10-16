# beamact3 — ACT wheel 분류·compact history A/B (진행 중)

actdiag 권고를 같은 beampair8 dataset-v1과 beamact2 분할로 재학습한다. 원 데이터 archive SHA `739a9fae…e251`, split manifest SHA `a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd`이다. TRAIN166시드60023행 / validation19시드6908행 / 보류20시드8329000..8329019를 유지한다. 원본은 압축된 채 보존하고 metadata-only hardlink view로 읽는다. 데이터·정규화·시드·cold-start 분포·학생 실행기는 바꾸지 않는다.

A/B 모두 기본 off 후보: wheel별 `−0.35/0/+0.35` 3분류, shared ACT decoder의 연속 pulse/PWM, 기존 balanced completion BCE와 CVAE KL10. 동일 ImageNet 초기화·seed20261015·batch8·chunk8·10Hz·최종20000step 고정(300 smoke 포함). 검증/보류 성능으로 checkpoint를 선택하지 않는다. wheel CE는 유효 label의 표준 비가중 평균, 계수1이며 기존 done 계수1과 같은 단위 그룹 가중을 사용한다. upstream의 wheel L1 네 항만 정확히 제거한다. pulse/PWM은 같은 decoder 특징에 조건화되고, wheel0의 pulse0은 기존 명령 투영이 적용한다. 수제 근거리 경로·persistence 대체는 없다.

compact history는 최근5개 자기 발행 명령을 그대로 보존한다. 근거: actdiag의 unique TRAIN same-sign nonzero wheel run8293개 중앙5틱(0.5초), p25=1/p75=18. 원래16개 중 오래된11개의 normalized14차원을 TRAIN mean0으로 가린다. 전체 state252차원과 고정 번호표·시계·자기 RGB4장은 그대로다. A는 최근5개 명령 전체를 쓴다. B는 같은 상태에서 wheel/pulse40 scalar만 더 가리고 PWM/age는 보존한다. act16a training-plan의 해당 A/B는 whole-history dropout0이며 여기서도0이다. 따라서 A/B 차이는 recent wheel/pulse 마스크다. 기존 beamact2와의 차이는 head/history/20k의 묶음이며 단일 인과 효과로 주장하지 않는다.

학습은 gcp2 프로젝트 `ugrp-sim-b-1014`의 기존 `ugrp-act-l4-gcp2` L4를 warp3와 공유한다. 속도판정에 쓰지 않고 shared-load·GPU/프로세스·임대를 기록한다. 각 조건 유한 process <=7h, VM8h·idle20분·budget-stop 유지. 이미 시작된 VM 창이 모자라면 checkpoint+optimizer+sampler/torch/CUDA RNG로 같은 소스를 재개하고 HOST interruption을 별도 기록한다. 다른 작업을 정지하거나 VM 상한을 갱신하지 않는다. 비용 정지가 확인되면 새 실행·재시작을 금지하고 ops-alert에 BUDGET을 쓴다. gcp1 접근·Mac 물리/렌더/학습/GUI·모델 키 전달 없음.

평가 순서: final20000 저장/재로딩 → TRAIN/validation 전체·8틱 재추론·안정/전환·단계별 decoded MAE vs raw persistence → 번호표만 교환한 initial/first-approach 오프라인 출력 → gcp2 CPU 보류20 폐루프(16동시·전체40이하) → 원본재계수·퍼널·감사·실패영상/6장 이상 → 실패 모델도 새 Release 보존·재다운로드/전체hash/모델로딩. A/B 결과는 합산하지 않는다. 보류20은 beamact2에서 이미 본 비교 세트로 새 확증 자료가 아니다. 실패 직전10SIM초 자기 RGB10Hz ring은 기존 기록 옵션을 그대로 쓴다. 거부 원본은 [직전 분포/퍼널](prior-rejection-table.json)에 있다. 접근12·정렬7·파지1이므로 head/history의 전역 적합도와 접근/끝 선택을 먼저 검증한다.

Gemma 공급가50% 인상 경보는 시작 시 확인했다. 이 경로는 판단LLM 호출0이며 새 LLM 배치는 제출하지 않는다. 결과는 로컬 프로젝트·GitHub에만 기록한다.

기준 검증: Mac 비물리16pass/2skip (분류 loss/serializer 실제 연산은 GCP2에서 수행). 학습·폐루프·배포 완료 전에는 성공 수를 채우지 않는다.

참고: [PyTorch CrossEntropyLoss](https://docs.pytorch.org/docs/2.14/generated/torch.nn.CrossEntropyLoss.html)의 class-index 표적/유효행 평균; [고정 LeRobot ACT](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/modeling_act.py)는 웹 열람 실패, 대신 L4 설치 원문을 직접 확인해 한 번의 forward와 valid×14 분모·동일 decoder 출력 head를 유지했다. [ACT 원 논문](https://arxiv.org/abs/2304.13705)은 기존 구조의 출처이며 wheel CE의 성능을 보증하지 않는다. actdiag 원문을 [로컬 참조](actdiag-reference.md)로 보존했다.

소스와 자원: 학습 core는 `4747c4144a972e348a9ae4c7bbcc769ad116106d`에 고정했다. 후속 평가/기록 SHA는 별도로 남긴다. 원본 및 A/B checkpoint를 보존하면서8GiB 여유 바닥을 지키기 위해 L4 디스크를100→140GB로 온라인 확장하고 파일시스템 여유52,517,224,448B를 확인했다. warp3 프로세스·VM 스케줄·budget-stop 변경0. [실행/저장 예산](resource-plan.json).

A 최종20000 학습 완료: main wall10120.58초(shared-load, smoke309.48초 별도). final model SHA `e5c48771f03660b20cff525515cddb6cf82566c2797b2d89a8b57a9c17e27650`; actor 전체3파일과 optimizer 저장/재로딩 일치. 검증 wheel MAE 전체0.022876 vs persistence0.023129(1.1% 감소), 재추론0.020701 vs0.022809, 안정0.011423 vs0, 전환0.126417 vs0.232231(45.6% 감소). pulse/PWM은 persistence보다 크므로 wheel 개선을 전체 명령 개선으로 넓히지 않는다. 검증 initial38개 번호표 교환에서 wheel class 변화0, first-approach29개 중1개 변화다. cold-start40개 probe와20시드 학생 평가는 아래와 같이 완료했다. B smoke도 같은 gcp2에서 완료했다. 공유 디스크 여유11.17GiB와 B 잔여 checkpoint 약3.1GB 때문에140→180GB를 온라인 확장했다(여유50G 확인); 원본 삭제·다른 임대/프로세스 중단·VM 상한 변경0.

A 학생 원본20시드 재계수는 **0/20 NOT_READY**, cap_end20회·HOST_ERROR0회다. 누적 접근16→정렬0→READY0→파지0→3초들기0이며, 실패 단계는 정렬16·접근4다. 전체24000 자기 입력/명령 행 감사와 프로토콜 재생,35620개 raw파일·96000 RGB참조 SHA를 확인했다. [재계수/퍼널](A-student-summary.json) · [거부 표](A-rejection-table.json) · [영상 직접 검토](A-playback-review.md). cold-start40의 번호표만 교환할 때 첫wheel변화3/40·8틱chunk변화6/40·발행명령 방향반전1/40이다. 다만8329001은 이번A에서 배정된 파랑/청록 끝에 각각 접근했으므로 번호표 무시만으로 실패를 설명하지 않는다.

A [비교 모델 Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-beamact3-a-v1) 완료: 공개 ZIP191893393B 재다운로드·10파일 SHA·새 reference clone `5ad43e1e0`의 CPU worker `ready:true` 확인. [배포 영수증](A-release-verification.json). 새로운 물리 성공 검증은 아니다. B는 smoke300 후 기존 VM 창의 step1498에서 cap_end 체크포인트/optimizer/RNG 재로딩을 확인했고,8시간 정상 종료 뒤 같은 학습을 계속한다.

번호표 검증 통계 정정: validation 첫 접근29개에서 원래 float 방향 반전1건은 순수 회전의 약1e-9 평면 이동 투영 오차였다. 관측된wheel3값과4-wheel 축합의 정수 단위0.35/4로 다시 세면 **반전0/29·이동 시작/정지 변화1/29**다. initial38개는변화0이다. [정확한 축합 재계수](A-validation-role-direction.json)와 원 float 결과를 함께 보존한다. pulse 길이까지 곱한 별도 cold-start40 명령-dose 반전1/40과는 다른 지표이며 합산하지 않는다. 체크포인트·wheel MAE·학생0/20 결과에는 영향을 주지 않는 후처리 정정이다.

09:05UTC 일시 네트워크/API 오류로 Mac 중계만 종료됐다. 같은 부팅의 L4 학습 PID1544는 계속 실행되어18830step을 확인했다. 중계의 read-only 재시도와 완료 결과/살아 있는 작업 재연결을 보완했고 A 모델3파일·원본20개·소스/모델 SHA를 재확인하여0/20을 재사용했다. 새 A 시뮬·새 B 학습·추가 VM 재시작0, 원래18시간 중계 기한 유지. [복구 검증](relay-recovery.json).
