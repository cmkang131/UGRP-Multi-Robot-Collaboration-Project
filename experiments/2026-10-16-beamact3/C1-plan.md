# beamact3c C1·C2 사전 실행 계획

사용자 2026-10-16 `ㄱㄱ`와 `빨리빨리 해줘`, coordinator19:00/19:35 인계가 근거다. base335fc8e35의 A/B와 별도 집계한다. C1=gcp5(ugrp-sim-e-1016, changmin5781@gmail.com), C2=gcp6(ugrp-sim-f-1016, kcm5781kcm5781@gmail.com), 각각 g2-standard-8/L4. 두 VM 실행 상한 없음, 유휴20분·budget-stop 유지. 첫 프로젝트 접근0, 모델/에이전트 자격 증명 전달0, LLM0.

C1은 정규화된 자기 명령 전체16×14를0으로 가려 RGB·고정 표·기존 스킬 시계만 받는다. 입력 차원·모델 크기는 A/B와 동일하고 명령 값은 학습/추론 모두 영향을 줄 수 없다. C2는 A의 최근5개 명령을 유지하고 학습 때 표본 전체 이력을 확률p로0으로 가린다. p=TRAIN 고유 h0의 안정 바퀴 프레임수/N. 전환은 h0 바퀴4개와 직전 자기 발행 바퀴4개의 정확한 데이터 알파벳 불일치이며 A/B offline 전환 정의와 같다. 안정·전환 두 클래스에 기대 표본 질량1/2씩 주는 가중 복원추출로 전환 프레임당 가중 Ns/Nt를 적용한다(기존 전체 BC/완료/KL 목적함수의 프레임 가중과 기댓값 동등). 이 수치들은 TRAIN만으로 산출해 원장·adapter·resume에 저장한다. 보류/validation 선택0. 근거 주석은 harness/C1-beamact3c.py:train_priors.

동일 데이터 manifest SHA a0f5d8a1c6c9b6c4988122ae40bf412c4c705f3c34740d8d7a91c93fef58d6cd, seed20261015·batch8·chunk8·총20000step·3분류wheel·balanced BCE·AdamW·ResNet18 사전학습·ACT 구조를 유지한다. 각 C 조건300step smoke→저장/재로딩→optimizer/RNG 정확 재개로 총20000step. 판단 상수·제어 경로·물리·60SIM초 평가 cap 불변. 체크포인트5000step마다, 최종20000만 선택한다. 새 wall cap0.

학습 완료 후 동일 gcp2 CPU C MuJoCo 보류20 평가, 총 동시≤40/임대 준수. 먼저 전환 정확도·cold-start 첫wheel변화, 폐루프 접근→정렬→READY→파지→3초들기 누적 퍼널과 거부 표를 보존한다. cap_end/HOST_ERROR 분리, 자기 입력/명령·원본 SHA 재계수. 실패1–2개와 성공이 있으면1개를 gcp2에서 자기카메라 나란히 개요 영상≤8MB·전체2Hz·직전10SIM초10Hz로 만들고 파일로 확인한다. 성공0이면 성공영상 없음으로 기록. 원인 확인 시 해당 결함 실행을 즉시 정지한다. Mac 화면 앱/로컬 물리/모델0. 모델은 별도 GitHub Release 재다운로드·전체SHA·새 reference clone CPU 로딩 확인 뒤 배포 완료로 기록한다.

사전 거부 분포는 C1-prior-rejection-table.json(A 접근16 정렬0, B 접근13 정렬1 READY1 파지0); copycat은 실험 가설이며 확정 원인이 아니다. A/B 기록 파일은 수정하지 않고 새 파일은 C1-/C2-만 쓴다. PR은 codex/beamact3 위에 쌓으며 병합은 별도 승인 대상이다.
