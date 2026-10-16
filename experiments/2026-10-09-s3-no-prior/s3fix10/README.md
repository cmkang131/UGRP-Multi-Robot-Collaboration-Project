# s3fix10: Oracle 단계 probe (실행 전 등록)

2026-10-10 사용자 결정으로 Mac 물리·렌더·저장 재생은 중단한다. 이전 s3fix9 큐는 입력0/12·물리0 상태로 종료됐으며 대기 원본을 보존했다. Mac에서는 편집·커밋·관련 pytest만 한다. Oracle `oracle-a1`, ARM 8코어/24GB, 공용 MuJoCo3.12.0·OSMesa에서 커밋된 archive를 실행하고 원본을 회수한다. `~/stock-bot`·crontab은 접근·수정하지 않는다.

## 이번 묶음

v154를 보존하고 새 번들v155/workflow7.48.0으로 세 개를 병렬 실행한다. 각 ≤60 SIM초, wall상한30분, dev_light, heading기본on·공동파지 빔 운반만 heading예외, v3 호스트 마운트·weld off·자기RGB/명령/허용정적지도 조건은 그대로다.

1. pair-B: 실제 `align_start`, 카메라 자세 보존off. r1/r2 정렬→hover→하강→닫기.
2. pair-N: 같은 Oracle 장면·seed·실제 `align_start`, `preserve_issued_look_v1`만on. 같은 단계 판정.
3. cyan-carry: 기존 cyan 합성 접근 종료 위치에서 실제 RGB 정렬→hover→하강→닫기→기존 상승·운반 제어를60초까지 실행. 기존 probe의 닫기 후1초 종료만 이 새 번들에서 해제한다. 파지·상승·운반은 eval_only 접촉/높이/이동으로 각각 판정하며 발행 close를 성공으로 간주하지 않는다.

원본v152의560초 주변 정답은 **장면 재구성 owner에만** 쓴다. `scene-setup.json`은 원본 로그 SHA와 선택한 행을 보존한 작은 추출물이다. 컨트롤러는 새 전역 자기RGB 필터이며 초기 위치 정답·새 Gaussian prior를 받지 않는다. r3는 v152에서 정렬에 도달하지 못했으므로 기존v153과 같은 합성 stage entrance임을 표시한다. 정확한 checkpoint resume나 임무 성공을 주장하지 않는다.

세 실행은 같은 호스트에서만 비교한다. OSMesa/ARM/MuJoCo 버전 차이 때문에 Mac 영상·물리·궤적과 바이트 동일성을 요구하거나 승계하지 않는다. 보수 가드는 would_stop으로 기록하고 실제 낙하/기울기/집게 이탈/GO 실패/실행 오류만 정지한다. 원본 host의 실제 물리 정지는 HOST_ERROR와 구분해 기록한다. ENOSPC는 HOST_ERROR다. 임계값·seed·카메라 보정은 결과 뒤 변경하지 않는다.

새 입자 제안은 이 물리 묶음에서off다. s3fix9의 관측에 맞는 후보 선택 구현·선택 기준·참고 자료는 보존하되 100/500/새100 비교는 후순위다. 아직 새 비교 결과가 없으므로 채택하지 않는다. 먼저 raw를 보고 정렬·상승·운반 실패를 한 묶음으로 수정한다. 1시간 넘게 진전이 없으면 멈추고 남은 항목을 보고한다. Mac agent_lock 대기는 하지 않는다.

## 참고 자료와 기존 표준 경로

- [관측 제안 사전 등록·Mixture MCL/SRL 원문](../s3fix9/README.md#참고-자료)
- 기존 공통 `Scene`·v3 카메라 바인딩·실제 motor port 경로를 유지한다. 입력/기록 경로만 서버에 맞춰 분리한다.
- [MuJoCo Python headless rendering](https://mujoco.readthedocs.io/en/stable/python.html#rendering): 플랫폼별 OpenGL context 경로를 명시하고 실제 환경을 기록한다. Oracle 실행은 사용자 지정 OSMesa다.

실행 전 관련3파일의26개 통과, Oracle 환경 fixture의 우선순위 모의를 고친1개 재실행 통과: 총27개 확인. 실제 모터 stub 경로·Mac 실행 거절·archive SHA·닫기 후 상승/운반 상태 진행을 검증했다. 물리·렌더·저장 재생0.

상승 전 source 점검에서 S3 host는 낙하/기울기를 감시하지만 S2의0.3초 양손가락 접촉 이탈 가드가 없음을 확인했다. 새 r3 probe에만 기존 S2 `StopGuard`를 그대로 연결한다(높이0.06m·이탈0.3초·바닥0.005m·기울기10도, 수정 없음). GT는 별도 host의 abort만 결정하며 위치/행동 보정에 반환하지 않는다. pair와 기존v153/v154 기본 경로는 유지한다.

실행 전 host 갱신: 08:01UTC 자동 축소·재부팅으로 실제2코어/12GB가 됐다.8코어 복원 안내를 요청했지만, 이를 위해 다른 서비스를 재부팅하거나 자원을 다시 확장하지 않는다. 현재2코어에서 같은 세 probe를 병렬 실행하고 각30분wall상한을 유지한다. 실제 CPU/메모리를 environment에 기록하며8코어 성능·Mac 속도와 비교하지 않는다. c5d0bb17 plan은 실행시작false/EXIT0으로 회수했으며 물리0이다.

## 서버 중단과 재시도

첫 묶음(`s3fix10-{pair-n,cyan,pair-b}-c0bf138f`)은08:20:05UTC까지 PID10245/11788/11825·nice0·2CPU/12GB에서 실행 중이었다. 이후 SSH 연결이 끊겼으며08:26UTC 재접속에서 uptime3분·기존PID없음·EXIT/result없음으로 재부팅 중단을 확인했다. 재부팅 주체/이유는 미확인이다. 이 작업은 서버 resize/reboot 또는 다른 프로세스 종료를 수행하지 않았다. 세 원본을 기본 체크아웃 `outputs/oracle-runs/`로 회수하고 Oracle에서 `interruption-record.json`에 파일 SHA·남아 있는 프레임 기록을 별도로 봉인했다. 로봇 실패·성공이나 완료 시간으로 해석하지 않는다.

08:26UTC 현재 자원은6 logical CPU/24GB였으며 다른 물리 실행이 없음을 확인했다. 같은 커밋 `c0bf138f24d8afa2bdd540375fc008ad6a65c2e4`·v155·장면·seed·옵션으로 `s3fix10-r2-{pair-n,cyan,pair-b}-c0bf138f`를 병렬 재시작했다. 이 새6CPU 묶음끼리만 비교한다. 첫2CPU 중단 묶음은 비교 분모에서 분리하며 원본을 덮어쓰지 않는다. 실행 전 PR416에도 이 구분과 실행 중 재부팅 회피 요청을 남겼다.

## 회수된 pair 결과

| 조건·로봇 | 검출/관측 | 끝점 가시 | 정렬 문턱 충족 | 회전 방향 반전 | hover/하강/닫기 | wall/SIM |
|---|---:|---:|---:|---:|---|---|
| B r1 |141/141|129/141|0|115|0/0/0|753.543/60=12.559|
| B r2 |141/141|138/141|0|125|0/0/0|동일 실행|
| 자세 보존 N r1 |144/144|144/144|0|136|0/0/0|761.243/60=12.687|
| 자세 보존 N r2 |144/144|144/144|0|143|0/0/0|동일 실행|

B/N 모두 `DEV_STAGE_FINISHED`·EXIT0·HOST_ERROR0이며60초 상한까지 정렬 상태다. N은 실제 발행한 `inspect`(3/4/5/6=508/2432/1320/1500)를 두 로봇에서 그대로 유지했다. 프레임별 표는 각 회수 폴더 `evaluation/frames/r{1,2}-frames.jsonl`이며 픽셀 오차·발행 명령·eval_only 실제 이동을 함께 보존한다. 회수한 raw 각각3,635개 파일의 봉인 SHA가 일치한다. 카메라 진입 수정의 적용·가시성 개선과 정렬 성공은 별개이며, 아직 pair 집기를 해결하지 못했다.

남은 원인은 **집게 목표의 상대 자세 오차를 차체 원점의 주행 경로점처럼 heading에 전달하는 것**이다. 합법 fine lateral 프로파일은0개다(±0.35 옆 명령은0.06초여서 REAL 최소0.10초에서 제외되고,0.65 옆 명령은 최종정렬 강도 한도 밖). 따라서 마지막 수cm에서도 `rotate_path`로 돌아가 `atan2(ey,ex)`를 쫓는다. N r1의3.0초 관측 `[23.229,2.403]mm`에서+0.35/0.10초 회전 후3.4초 관측은 `[20.080,-23.382]mm`; 다음 회전을 반대로 발행한다. 마지막 실제 회전 크기도 r1/r2 약0.0998/0.1028rad이며, 같은 회전으로 전방의 집게 기준점이 옆으로 움직이는 효과를 목표 오차 변환에 포함해야 한다. 단순 검출 실패나 σ 정지로 분류하지 않는다.

### 재조사와 다음 수정의 경계

- [Chaumette·Hutchinson 2006, Visual Servo Control Part I](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf): PBVS는 관측한 목표의 상대 자세를 카메라/차체 운동과 일관되게 변환한다. 여기서는 `R(-dθ)(grip-dxy)-grasp_target` 전체 변환이 필요하다. 이미 구현된 `visual_pose_mpc_v1`은 이 항을 포함하지만, 이전 카메라 진입 후보와 이번 N 실행에서는 꺼져 있었다. 이번 결과만으로 다시 채택하지 않는다.
- [Nav2 RPP 설정](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/configuring_regulated_pp/): 경로 진행 방향과 목표 자세를 구분하며, stateful goal 처리는 XY 도달 후 방향 보정 단계가 다시 XY 추종으로 되돌아가지 않게 한다. 우리 pair의 마지막 RGB 정렬을 경로점 추종으로 대체한 부분은 이 목적과 다르다.
- 다음 pair 검증은 자세 보존을 고정하고 기존 full-pose PBVS 옵션만 바꾼 ≤60초 probe로 한정한다. 법적 최소 명령·기존 보정 프로파일·3mm/0.035rad 판정은 바꾸지 않는다. 더 짧은 미보정 명령 또는 GT 보정으로 통과시키지 않는다.

r3는08:43:01UTC 원격 `result.json`/EXIT0에서60 SIM초·894.933wall초·최종`carry`를 확인했다. 후속 평가 중 A1이 다시 재부팅됐고08:47UTC 2CPU로 접속이 회복됐다. 원래 `evaluation/`의 미완료 산출물은 보존하고 `evaluation-v2/`에서 평가를 끝냈다. **이미 끝난6CPU 물리 실행**을2CPU에서 사후 판정했으며 새 물리 실행이 아니다.

| r3 단계 | raw SIM 시각 | probe 시작 후 |
|---|---:|---:|
| hover |12.35|10.00|
| 하강 |13.65|11.30|
| 닫기 |15.30|12.95|
| lift 상태 |15.75|13.40|
| 양손가락 접촉 유지 + 높이>0.06m |16.55|14.20|
| carry 상태 |37.55|35.20|

실제 양손가락 접촉과 상승917표본, 최고COM높이0.162949m, 접촉 유지한 상승 구간의 최대 수평 변위0.249884m를 확인했다. B 배송/놓기/귀환은 미도달이며 전체 임무 성공이 아니다. 실제 정지0, HOST_ERROR0, 짧은 명령0, 혼합 축0; would_stop은 `REAL_PREGRASP_UNCONFIRMED`1·`ARM_COLLISION_GUARD`14·`POSE_UNCERTAIN`27·`PATH_COLLISION_GUARD`1이었다. wall/SIM=14.916은 이6CPU 동시 묶음의 측정이며 Mac 성능과 비교하지 않는다.

다음 물리 재시도 전에 N의 저장 RGB 오차288개에 기존 PBVS 선택기(HORIZON6·같은 보정 명령)를 재생한다. 원래3mm/0.035rad 이내의 예측 종료 상태 수와 명령 변화만 세며, 재생 결과를 물리 수렴으로 부르지 않는다. 예측 경로도 판정 문턱에 도달하지 못하면 동일 물리 실패를 반복하지 않고 합법 미세 명령의 보정이 필요한 것으로 보고한다. 결과를 보고 horizon/문턱/seed를 늘리지 않는다.

기록 정리 전 정렬 진입 관련3개 시험을35.24초에 다시 통과했다. 이번 소스의 고유 회귀 사례 수는28개이며 재실행3개를 새 사례로 더하지 않는다.

## 저장 제안 재생·최종 전달

동결한 후처리 `d5c103cf`의 `replay_alignment_geometry.py`를 Oracle에서 실행했다. 제어/보정 원본은 물리 실행과 같은 `c0bf138f`다. r1/r2 각144개 중 명령 변화113/101개, 원래 문턱 이내의6단계 **모델 예측**은1/0개였다([해시·집계](geometry-replay.json)). 전체1/288을 물리 성공률로 해석하지 않으며, 기존 MPC만 켜는 처방은 채택하지 않는다. r1/r2 정렬은 미해결이다. 같은 실패의 물리 반복은 추가하지 않고, 다음에는 최종10cm용 **합법0.10초 이상 미세 명령의 보정 범위·도달 가능성**부터 확인해야 한다. 관측에 맞는100입자 후보의 기존12재생은 여전히0/12·미채택off다.

- [세 완료 실행의 단계·프레임 집계·원본 SHA](completed-runs.json), [세 재부팅 중단 원본](interrupted-runs.json), [실제 재시도 PID 영수증](retry-process-receipt.txt). 완료 raw10,906개 파일의 회수 해시가 모두 일치했다. 모든 제어/물리 프로세스와 이번 후처리는 종료됐으며 다른 작업은 종료하지 않았다.
- `outputs/tensorboard/1010-s3fix10-oracle`: 완료3개와 인프라중단3개를 분리한 새 스냅샷. 총72 scalar를 event에서 다시 읽었으며, 중단 시행은 물리 성공/실패 값을 만들지 않았다. [핀·실행·영상·UI 검증](tensorboard-verification.json).
- [TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1010-s3fix10-oracle%2F#timeseries), [r3 대표4배속 영상](http://127.0.0.1:6007/video/2433400557dbee674291). 세 MP4 모두15초·20fps·1920×480, HTTP Range206 확인. Chrome `강`에서 실제6개 실행·핀8개·수치1/0/0 및0.2499m와 r3 영상 재생을 확인했다. HParams는case/policy/seed/source_sha 네 열을 적용했지만 공용 전체4,445그룹이며 실제 비교 화면은 Time Series의6개 필터다.
- Oracle 자원은 실행 전8→2, 중간6, 후처리 전2CPU로 바뀌었다. 세 유효 물리는6CPU/24GB에서만 수행됐다. 이 작업이 자원 변경이나 재부팅을 요청/실행한 적은 없으며, 두 번의 SSH 중단·첫 원본 손실 가능성과 후처리 재시도를 별도 보존했다. Mac 물리/렌더/저장 제어 재생0, Mac 잠금 대기0, CI 대기0, 병합0이다.
