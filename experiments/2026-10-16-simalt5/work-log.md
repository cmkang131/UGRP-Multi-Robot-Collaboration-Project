# simalt5 작업 기록

- 2026-10-15 16:45:52.759 UTC: gcp2 L4 시작. 계정 changmin5781@gmail.com / 프로젝트 ugrp-sim-b-1014 / g2-standard-8 / asia-northeast3-a. 사용자 상한 10,800초, 종료 시각 상한 19:45:52.759 UTC. CPU gcp2에는 beampair5/scenetex3 임대가 있어 정지하지 않는다. 양쪽 호스트에 simalt5 임대를 만들었다.
- simalt4 README·summary·스텝 표·ops-alert 505행을 먼저 검토했다. 원래 11.508172 mm, 48,834스텝/12.2085 SIM초에 5 mm를 처음 넘었다. 파지 30은 같은 3초 trace의 시간 표본이며 독립 시행 수가 아니다.
- 공식 MuJoCo3.15 b3dd9e617의 dampratio 관성 계산 변경을 확인했다. `actuator_biasprm[:,2]` 4개만 같은 XML의 C3.12 컴파일 값으로 복원하는 compiled-312-v1을 기본 off로 추가했다. XML·actuator 이름/순서·나머지 감사 물리 배열이 다르면 거부한다. 반대 방향(C3.12에 C3.16 감쇠)도 별도 ablation으로 기록했다. 새 물리값을 튜닝하지 않았다.
- 실행 소스 e89ff15343225a08e826788b5345666f792bc42c, 원래 simalt3 fixture/XML 재사용. C3.12/C3.16 native 교환 2개, Warp 보정 4개를 R1에 등록했다. C3.12에 C3.16 감쇠만 넣으면 원래 C3.12와 끝점 차이 11.305279 mm, 기존 Warp와는 0.574656 mm다. 이 값은 하나의 개입 결과이며 scalar norm을 가산 분해하지 않는다.
- R2 native controls(51048030): C3.16에서 공개 collision function table과 해당 버전 헤더를 써서 C3.12 Plane–Mesh support/neighbor 선택을 포팅했다. 물리 배열은 유지했다. 컴파일 전용 0-step PASS. 감쇠까지 복원해도 끝점 12.874258 mm / 2.225243°가 남았고, contact/constraint count가 16스텝부터 달랐다. 따라서 이 native adapter가 엔진 전체를 C3.12와 같게 만들었다고 주장하지 않는다. 두 감쇠 조건 모두 파지 30/30, 높이 차는 각각 0.003391/0.049287 mm다.
- 추가 import 감사(ada5d5c3): copied damping이 `put_model` 뒤에도 C3.12 값의 float32 변환과 정확히 같음을 확인했다. physics step0. 기존 pinned MJWarp 설치를 재사용하며 패키지 전체 source 재감사를 주장하지 않는다.
- 소스 사본은 같은 L4의 git-shared.git을 직접 참조했다. 최초 filtered shared clone 때문에 sparse checkout에 blob이 없었고, 그 뒤 네트워크 reference clone 한 번은 unresolved delta로 실패했다. shared에서 해당 branch를 materialize하고 `git clone --reference ... --shared ...`로 직접 참조해 해결했다. 사본을 참조하는 사슬이나 원본 삭제는 하지 않았다. 첫 materialize의 Git 자동 packing 메시지를 본 뒤 gc.auto=0/maintenance.auto=false로 설정했다. 수동 gc/prune은 실행하지 않았다.
- native physics 2개가 끝난 뒤 분석이 아직 진행 중인 Warp를 읽어 incomplete-input으로 거부된 1건이 있다. 물리 실패와 별개다. 원본은 유지하고 Warp 완료 뒤 새 분석 경로에서 다시 비교한다.
- 화면 앱은 열지 않았다. gcp2에서 원래 실패와 C3.12 양성의 4배속 MP4·전체 2 Hz·실패 발생 직전 10초의 10 Hz 띠를 다시 만들었다. Mac에는 요약/몽타주/MP4만 회수했고 초기 16/16 SHA를 대조했다. 전체 원본은 L4에 남긴다.

이 파일의 진행 중 숫자는 최종 summary의 완료 판정을 대신하지 않는다.
