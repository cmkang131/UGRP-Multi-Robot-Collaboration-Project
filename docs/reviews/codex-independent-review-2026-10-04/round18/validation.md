# 18차 독립 검증

## Replay source and comparator

별도 control 검토자가 writer/replay script `bbba3a3a…bf791`를 새 stdout으로 실행해 10개 case의 golden `ba0aa451…af818`과 바이트 일치를 확인했다. 6개 exact main Git source hash도 직접 대조했다. 원본 manifest comprehension·명령 writer·executor·replay main을 실행했지만 world/port/clock/snapshot은 대역이다. 현재 geometry hash가 recorded hash와 다른데 source predicate가 통과한다는 점과, 포함된 sim 변경·위치 1.1mm·미소비 명령이 거부된다는 대조를 확인했다.

Geometry 검토자가 누락 파일의 실제 model/target 의존성을 좁혔고, evaluation 검토자가 별도 XML/target fixture를 재실행해 원본 결과와 바이트 일치 및 11개 source hash를 확인했다. 1mm는 capsule 모델 endpoint의 변경이며 replay 위치 오차 측정이 아니다. 단일 template contact 2/1과 multi clone 2/3, source gate 누락과 전체 물리 replay 우회를 구별한다.

현재 stop/cargo 경계는 source와 합성 대조로 확인했다. 새로운 stop 누락이나 cargo identity 결함은 주장하지 않는다. 실제 raw episode·physics·render·모델은 실행하지 않았다.

## Reference identity

별도 geometry 검토자가 reference-assets fixture를 실행해 golden `4475e8cb…56b0e`와 바이트 일치, 3개 exact source hash를 확인했다. 정상 catalog/descriptor/consumer read와 다섯 변경·누락 유형의 차단이 범위다. 비자산 gate와 scene 이후를 대역/미실행으로 명시했다.

연구 메모는 coverage와 evaluation이 실제 producer/consumer 필드 및 비교 해석을 각각 source-only로 검토했다. 연구자가 fixture를 또 실행한 것으로 합산하지 않는다. 준비 자산, 실제 applied execution, 관측/행동 시퀀스, exposure 근거를 분리했고 새 finding을 추가하지 않았다.

## Delivery

GitHub는 탐색·판정 Markdown만, Mac은 상세 독립 QA·작은 재현·golden·manifest와 선택한 공개 exact source를 보존한다. 세 script는 표준 Python과 `--repo`로 지정한 pinned Git objects를 사용하고 저장소를 수정하지 않는다. 원본 증거를 보존하도록 임시 폴더에서 stdout을 새 파일로 저장한다. 상세 상대 링크가 canonical 게시명과 다를 수 있으므로 상위 navigation과 evidence의 reproduction-notes를 사용한다.
