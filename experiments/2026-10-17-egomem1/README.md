# egomem1 — 자기 중심 지형지물 기억

사용자 2026-10-17 결정: 정적 지도·시작 구역 사전·전역 좌표 없이,
자기 자신은 항상(0,0)·정면이다. 목적지는 자기 RGB로 보고 찾는다.
이 README는 구현·오프라인 평가·실제 MJWarp 복귀를 각각 구분한다.
현재 결과는 실행 전이며 실제 성공은 아직 측정하지 않았다.
mapbuild12 미커밋 결과는 원래 브랜치 codex/mapbuild1의
`95769da0e12326e41b71d29843c4da75c5b10a00`으로 먼저 커밋·push했다.
새 브랜치는 origin/main `4bb02030b`에서 만들었다.
PR573 미병합 시 그 AGENTS와 기준표를 읽었으며
[정확한 기준표 사본](policy-pr573.json)은 검사에만 사용한다.

## 구현과 검증 경계

기본 off `egocentric_landmark_memory_v1`. 상태는 상대 점 목록과 전체
교차 공분산이며 world anchor·점유 격자·로봇 전역 자세를 저장하지 않는다.
이동량을 독립 변수로 추가→이전 좌표계에서 재관측 EKF 갱신→역변환
합성 후 이동 변수를 제거하는 Castellanos2007 §4 순서를 사용한다.
점 p의 합성은 `R(-dtheta)(p-dxy)`이며 F=R(-dtheta),
G=[-R(-dtheta), -J*p_new]로 공유 이동 오차를 보존한다.
재관측은 Joseph 공분산 갱신과 chi-square(2)99% 마할라노비스 관문이다.
같은 외형의 여러 기억이 관문 안에 있으면 모호로 거부한다.

검출은 기존 PR406 OpenCV floor_features/door_features·고정 K/D·자기
발행 서보 FK·자기 차체/동료 RGB 마스크를 재사용한다. 지도 palette 대신
전체 hue 공간을 기존 허용폭 간격으로 탐색한다. 부분 선분 중앙은 고정점으로
취급하지 않으며 관측된 선분 안의 교점만 구역 모서리 후보로 저장한다.
색은 외형일 뿐 구역 고유 ID가 아니다. 벽 모서리·빔 끝·화물·파트너의
안정된 점 검출/움직임 모델은 아직 연결하지 않았으며 지원을 주장하지 않는다.

상수: 거리σ.2m·방향σ3°·선각σ5°·최대6m·색 허용12는 기존 PR406
검출기 값을 그대로 쓴다. 새 장면의 공분산 보정 완료를 뜻하지 않는다.
sensor 간격1SIM초는 기존 mapbuild scan 주기다. 95%반경이 센서 전체
6m를 넘으면 국소 목표를 지정할 수 없어 삭제한다. 근거 없는 나이 상한은
없고 관측 간격 분포를 확인한 뒤에만 선택적 fade 시간을 설정한다.
32슬롯은 계산·LLM 목록 길이를 제한하는 후보 자원 예산(최대67차원)이며
물리 수용 기준이 아니다. 초과 시 가장 오래 안 본 슬롯을 교체하고 기록한다.

LLM 어댑터는 고정 규칙을 prefix에, 상대 기억·시각·불확실성·탐색 후보를
suffix에 둔다. 실제 LLM 호출/통합은 별도 검증이다.

## 오프라인 절차

gcp5 원본 `/home/ugrp/ugrp-sim/runs/mapbuild11-long-round1/unloaded-v2`
6.461m를 그대로 재생한다. 원래 기록은 정적 AMCL 제어로 만든 과거 코호트다.
새 기억에는 자기 RGB·명령·보정과 기존 LK 증분만 명시 allowlist로 전달한다.
정적 보정 자세·초기 사전·TOP·spawn은 제거한다. 예측을 SHA로 봉인한 뒤
별도 score만 평가 정답과 지형지물 라벨을 연다. 같은 외형의 정확한 장면
모서리 중 가장 가까운 것을 평가 라벨로 쓰므로 오검출·잘못된 대응은 한계다.
실제 복귀 재획득률은 이 재생으로 측정할 수 없으며 새 물리 기록에서 잰다.

수정 전 사유 분포는 [prior-rejection_table.json](prior-rejection_table.json).
새 detector의 관문표는 실행 뒤 별도 파일로 남긴다. Mac 물리/렌더/화면 앱,
CPU VM, 모델 키 전송, Drive는 사용하지 않는다.

## 참고 자료 — 원문 확인 범위

- [Castellanos·Neira·Tardós2004, Limits to the Consistency of EKF-based SLAM](https://webdiis.unizar.es/~jdtardos/papers/2004_IFAC_IAV_Castellanos_et_al.pdf): §4 식11–13의 자기 중심 역합성·이동 변수 추가·EKF 갱신을 확인했다.
- [Castellanos·Martínez-Cantín·Tardós·Neira2007, Robocentric Map Joining](https://webdiis.unizar.es/GRPTR/pubs/2006_Caste_JRAS_draft.pdf): §4 식11–16에서 이동 변수를 재관측으로 먼저 갱신한 뒤 합성하는 순서를 확인했다. 전체 map joining을 구현했다는 주장은 아니다.
- [Solà 외, Civera 연구실 공개 IJCV 원문 §7.1](https://webdiis.unizar.es/~jcivera/papers/sola_etal_ijcv11.pdf): 자기 중심 EKF에서 로봇이 매번 공분산0의 원점이 되는 설명·Civera2009 논문/학위논문 인용을 확인했다. Civera 학위논문 직접 URL은 찾지 못했으므로 전문 확인으로 표시하지 않는다.
- [Wang & Spelke2002, Human spatial representation: insights from animals](https://doi.org/10.1016/S1364-6613(02)01961-7): 서지 확인, 전문 접근 실패. 관련 직접 실험 [Wang & Spelke2000, Updating egocentric representations](https://www.sciencedirect.com/science/article/pii/S0010027700001050)의 초록에서 자기 중심 표적 갱신·방향 상실 결과를 확인했다. 이를 공학 성능 보장으로 쓰지 않는다.
- [Warren2019, Non-Euclidean navigation](https://doi.org/10.1242/jeb.187971): [저자 초록/서지](https://pubmed.ncbi.nlm.nih.gov/30728233/)와 [학회 저자 발표](https://www.biologists.com/meetings/jeb2018/programme/warren/)에서 전역 좌표에 통합하지 않는 국소 거리·경로 그래프 가설을 확인했다.
- [Beeching 외2020 EgoMap](https://arxiv.org/abs/2002.02286): 공개 전문에서 자기 이동의 affine 변환으로 자기 중심 기억을 갱신하는 구조를 확인했다. 해당 학습 격자/정답 ego-motion 입력을 가져오지 않는다.
- [Manigrasso 외, ESOM](https://arxiv.org/abs/2411.16934): 공개 초록의 관측 기반 object discovery→tracking→memory 흐름을 참고했다. 이 시스템의 학습 모델·3D 추적을 재현한 것은 아니다.

알고리즘 수식을 독립 Python으로 구현했다. 기존 검출기·카메라 FK는 저장소
코드를 재사용한다. `harness/servo_camera_fk.py`는 mapbuild1/95769da0e의
바이트를 그대로 가져왔으며 기본 off 및 과거 동작을 유지한다.
