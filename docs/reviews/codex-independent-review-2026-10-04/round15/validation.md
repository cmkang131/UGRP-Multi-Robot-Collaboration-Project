# 15차 독립 검증과 재현 범위

## Attachment

통합 검토자가 author fixture를 별도 JSON으로 실행해 최신66ff receipt 결과 `d6ed53a8…c7dbab`와 geometry 결과 `e18bf0dd…88c440`의 모든 byte 일치를 확인했다. 실제 사용8+20 source hash를 exact Git object와 대조했다. Close receipt 생성→lower READY/GO→HIGH callback→실제 guard flag 전달, open/no-checkpoint/new-grasp 대조가 통과했다. Production file과 원본 결과는 변경하지 않았다.

## Geometry

실제 static map/catalogue/v3 FK/PairGeometry/start-relief를 사용한 authored stationary beam reserve는+21mm다. +.10/.15s 명령의 최종 beam reserve는−7mm이며 False flag만 허용한다. 합법 reverse−.05와 stationary는 두 flag 모두 허용하고 양쪽 motion pad는4mm다. Body-only 약566mm 여유와31개 whole-beam sphere를 구분한다. Source의 uncertainty용 loaded profile은 유지된다.

첫 fixture의 geometry는 전달값 기록 double이고 두 번째가 실제 geometry 차이를 확인한다. 실제 prefix 물리 성공이나 route가 그 pose/command를 발행한다는 증거가 아니며 reserve 위반을 실제 접촉으로 읽지 않는다. 상세 독립 메모와 소비자 원고는 Mac evidence의 `attachment-independent-validation.md`, `loaded-beam-geometry-consumer.md`다.

## Currentness

독립 source reviewer가 actual factory의 C3 MRO와 receipt 쓰기 위치를 확인했다.66ff의 receipt 관련 HIGH 메서드와 base 구성이 같고, geometry/contracts12파일의 de03→66ff bytes 동일성도 통합 검토자가 직접 다시 확인했다. 새 terminal final-veto는 살아 있는 checkpoint의 attachment flag를 복원하지 않는다. 직접 PARKED stage 진입의 receipt 부재는 활성 caller 결함으로 추가 집계하지 않았다. Source-only 메모·manifest를 Mac evidence에 보존한다.

## Fixed

다른 독립 검토자가 final-veto old/new **12개 scenario**를 실행해 golden `b417a1ab…36847` 전체 일치,18개 source hash와 실제 runner dispatch를 확인했다. 두 caller(control/arm)의 기존 같은-tick 반례가 차단되며 no-abort는 보존된다. 실제 motor/joint 움직임, 모든 shutdown 조합, 새 admission/relook 기능은 검증 범위가 아니다. [수정 확인](fixed.md).

## Research and diagnosis

성공 계약은 source·기존 test assertion·BEHAVIOR 원문 선택 구간을 독립 대조했다. 절차 완료(C), 허용 관측 확인(K), 별도 task predicate(Y)를 구분하고 GT feedback 금지와 문헌의 reward/관측 조건 차이를 보존한다. 제안한 동일-input/다른-eval-label 비간섭 대조는 아직 실행하지 않았다.

Historical de03 row sensitivity는 원 golden `9b438924…6844af`와 독립 재실행, h/4 차분, exact-zero 열, √2 복제 대조를 확인했다. Optional M1은 golden `dd04b4d2…977e`와 독립 실행 및 source10개 대조를 확인했다. 이는 [진단 경계](diagnostics.md)이고 새 구현 결함이 아니다.

GitHub에는 Markdown만, Mac에는 `round15/evidence/`의 script/result/manifest/상세 QA를 둔다. Exact Git objects가 있는 clone, Python3 및 geometry/row용 NumPy가 필요하다. Receipt와 final-veto/M1은 표준 라이브러리를 사용한다. Geometry/row helper는 기존 `round12/evidence/`에 고정되어 있으므로 새 임시 폴더로 **round12와round15의 상대 구조를 함께** 복사해 실행하고 stdout을 새 파일에 저장한다. 원본 evidence를 덮어쓰지 않는다. 상세 reproduction note에 fixture별 dependency를 적었다.
