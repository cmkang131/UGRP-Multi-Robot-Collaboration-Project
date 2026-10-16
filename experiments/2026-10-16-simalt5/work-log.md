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

## 최종 정정·종료

- R1 역방향 보정은10.5581655mm였다. “대부분 감쇠”라는 초기 가설은 철회했다. R3의 기하65필드(12개 값 변경)까지 복원해도 Warp12.0992490mm, 높이차0.0187556mm, 무부하3/3, 접촉30/30이다. 3라운드 한도로 확대하지 않았다.
- native 포팅의 matvec/translation 덧셈 순서 차이를 C3.12 자기 대조가 검출했다(13.317663mm). 이를 MuJoCo 원래 함수 호출 순서로 수정한09d585b7의 두 C 대조는 C3.12 원본과173600×135열 모두 비트 일치했다. 따라서13.318mm를 버전 엔진 탓으로 본 중간 해석은 오류이며 제외한다. 추가 Warp 후보를 내지 않았고 이2회는 R3 대조기 수정 검사다. 총 새 물리 호출16회 완료·HOST_ERROR0·cap_end0, 이전 native 대조4회는 인과 추론에서 제외했다.
- 보정 뒤 C 버전 잔차0과 같은 버전 Warp 잔차12.099mm를 분리했다. Warp의 float32·충돌·솔버 산술 내부 분해는 남는다. 원래11.508mm의 벡터 분해에서 감쇠4.343/기하4.533/잔차12.099mm norm은 합산 가능한 독립 기여가 아니다.
- 전체 공통 numeric 모델 배열479개와 모든 옵션을 조사했다. 차이가 남은ctrlspec와dof_length는 현재 경로에서 미사용이며 fixed gain0·sleep enableflags0·flex0을 기록했다. 직접 C3.12 Warp import는mjINT_DISCRETE 부재로0-step 거부됐다.
- 첫 bit-parity 검사 JSON이 run root의 상위 폴더에 기록돼 수집기2회가 필수 파일 부재로 거부됐다. 원본 JSON을 보존하고 올바른 run 경로에도 회수해 재수집했다. 두 오류 로그를 보존했고 완료/해시 검증으로 소급하지 않았다.
- 모든 writer가 끝난 뒤 원본2552/2552 SHA PASS(1846450181bytes),25개 스텝 표3394400행을 기록했다. Mac lite111파일2733658bytes·검토32파일5366327bytes를 전체 SHA 대조했다. 검토는 MP4를 앱에서 열지 않고 ffprobe와 프레임 띠로 했다.
- L4 TERMINATED: 3417.701초/0.94936139h, 기존1.096USD/h 가정으로1.04050008USD 추정(실청구·디스크·네트워크·세금 제외). 사용 상한10800초 이내. 자기 임대를 지웠고 마지막 L4 audit에서 다른 임대/프로세스0이었다. Mac 자원 감시도 종료했다.
- CPU gcp2의 기존 beampair/scenetex 임대는 작업 중 종료돼 없어졌다. CPU를 다시 감사해 외부 임대·실행 프로세스0일 때 자기 임대를 해제하고 정지했다. 이후 외부 scenetex5가 VM을 다시 시작했음을 확인했으며 추가 정지하지 않았다. 현재 CPU RUNNING은 simalt5의 미정리 실행이 아니다.
- 최종 로컬 비물리 고유8검사 PASS·구문/diff 검사 PASS. PR Draft·전체 CI 결과 없음. 기본 backend·물리 프로필 변경 없음, 모델/학습/실물 검증0, 과거 연구 코호트와 합산 없음.
