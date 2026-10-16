# reloc20 — NOT_READY

locdiag.md/JSON을 먼저 읽고 `claude/reloc19` HEAD `b73e815f6` 위 `claude/reloc20`에서 구현·3라운드 실행을 마쳤다. [Draft PR #543](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/543). **최종 R3 place 0/4**(candidate 0/2, density 0/2), 목적지 획득 진입 0/4다. 세 라운드는 같은 시드의 DEV 반복이며 성공률 코호트로 합산하지 않는다. 전체 시도16회 중 운반10회(실제 제어 시작9회, 설정 오류1회), 짧은 자기지도6회다. 시작된 운반의 place는0/9, 종료는 cap_end9회·HOST_ERROR7회다.

[짧은 전체 결과 JSON](summary.json), [명령만/보정 xy 중앙·p95와 yaw p95 표](metrics.md), [전체 세부 보고서](full-report.json.zst), [실행별 범위·회전 펄스 분포](coverage.json). 원본 위치·결과/manifest SHA와 제어 소스 SHA를 실행마다 남겼다. raw는 gcp2 디스크에 보존했으며 Mac에는 요약·몽타주·실패 프레임·검토 영상만 회수했다. 전체 raw의 외부 백업을 뜻하지 않는다.

## 변경과 우선순위

locdiag의 yaw 전파 L1 증폭63–66%와 기하 위험 구간의 큰 국소 잔차를 보고 구동 평균·횡주행과 화물 포함 경로를 먼저 고쳤다. 독립적인 전체 오차 기여율로 해석하지 않았다. 수정 전 [사유 분포·관문 표](prior-rejection-table.json), [표준 방법과 모든 상수 근거](references.md)를 보존했다. Nav2 footprint/inflation·회전 후 전진·velocity smoothing, optical-flow 정지 검사를 조사했으며 확인하지 못한 논문 본문은 확인했다고 쓰지 않았다.

|토글|기본|후보 동작|
|---|---|---|
|`reloc20_loaded_footprint_v1`|off|기존 팔 envelope와 발행 PWM FK 화물 꼭짓점의 회전 불변 외접원. 정적 벽·명시한 초기 바닥 빔·자기 RGB 장애물에 strict A*. 시작/목표·모든 edge·내려놓기 전진/후퇴 검사|
|`reloc20_heading_forward_v1`|off|운반/목적지 획득의 횡 이동을 먼저 회전 후 전진으로 변경|
|`reloc20_contact_ode_v1`|off|PR510 후속 `7b223e30b` ODE를 별도 모듈로 보존. 기존 회전 보정 gain과 중복 적용하지 않음|
|`reloc20_visual_stall_v1`|off|자기 RGB LK+전역 변화량과 독립 명령 예측의 불일치. 자격이 있는 정지 영상에서만 적분 억제·손실 증분 외적만큼 공분산 증가·충돌 검사 후 후퇴/재계획|
|`reloc20_rotation_stall_v1`|off|R3: 같은 정지 검사를 순수회전에도 적용. 질감 부족은 unknown|
|`reloc20_obstacle_wall_mask_v1`|off|R2부터 기존 v5 벽/바닥 classifier를 장애물 검출에 재사용|
|`reloc20_obstacle_wall_component_v1`|off|R3: 벽 색 덩어리를 픽셀 제거 전에 검사해 잘린 벽 조각이 캔이 되지 않도록 거부|
|`reloc20_turn_density_v1`|off|R3 density만: 기존 요청 on-time을 누적해 기존 제어주기0.1초의 대칭 회전 pulse 발행. 정지/방향 변경 시 잔여 취소|
|`destination_direction_preserve_v1` / `destination_search_replan_v1`|off|reloc19의 비물리 후속. 후보에 함께 켰으므로 A/B/C 개별 인과 기여율을 측정한 실험은 아님|

clearance는 locdiag 최대 침투7.014mm+기존 최고 전진 한 tick8mm=15.014mm다. 위치 추정 오차까지 보장하는 경계가 아니다. 격자0.05m·노드40,000개로 제한하며 제어 계획에 wall deadline을 쓰지 않는다. 기존 시작/목표 여유를 푸는 fallback은 사용하지 않는다. `fixed-floor-map.json`은 두 시나리오의 선언된 **초기** 빔 keepout이고 움직인 빔 위치를 평가 정답으로 갱신하지 않는다. 화물 형상도 발행 명령 FK의 명목값이다.

하중 metric VO 자격0/531을 완화하지 않았다. 정지 판별은 metric VO가 아니다. 새 runtime 상수는 [원본 분포](flow-fit.json)·기존 제어주기·기존 보정/문헌 출처를 기록했다. 93266에 맞춘 방향별 yaw gain은 다른 DEV 시드93315에서 악화돼 **거부했고 실행에 넣지 않았다**([거부 결과](yaw-fit-rejected-summary.json)). 마찰·접촉·weld·카메라 배치를 바꾸지 않았다. wheel→body yaw gain 약0.984–0.986은 평가 전용 진단이며 접촉점 slip이나 실물 성능 증명이 아니다.

## 실행 결과

호스트는 gcp2 `ugrp-sim-b-1014` / `n4-highcpu-64`, CPU만 사용했다. 자체 최대6동시(상한8), 공용 상한40을 lease·실제 프로세스로 검사했다. 원본 머신/장면을 바꾸거나 gcp1을 사용하지 않았다. LLM·ACT 학습·Mac 물리/렌더/GUI 실행0.

|라운드|물리 제어 SHA|운반 place|짧은 자기지도|첫30 SIM초 wall/SIM 중앙|원본 해시 검증|
|---|---|---|---|---|---|
|R1|`aede24d64`|baseline0/2, candidate0/1+제어 전 설정 HOST_ERROR1|2회 재위치 추정 소진|4.306, 설정 실패의 표본 누락으로 gate FAIL|12,046파일 일치|
|R2|`1b3108601`|candidate0/2|2회 재위치 추정 소진|4.930 PASS|8,701파일 일치|
|R3|`cb8b37c29`|candidate0/2, density0/2|2회 재위치 추정 소진|4.356 PASS|12,400파일 일치|

R1의93315 선언 누락을 두 시나리오 hash-bound catalog로 고친 [해소 기록](round1/host-error-resolution.json)을 연결한 뒤 R2를 냈다. 원래 HOST_ERROR를 성공/정상 실행으로 고치지 않았다. 짧은6회는 원래 status가 HOST_ERROR이나 이유는 `selfmap4_relocalization_exhausted`로 VM 장애와 구분한다. 모든 시간 상한(phase_timeout 포함)은 cap_end로 구분하고 원래 사유를 유지한다. 세 라운드 짧은 결과는 동일했다:93584 command/registered xy p95=.092/.088m, yaw p95=2.573/2.686°;93583=.111/.127m,2.489/2.621°. 낮은 부분 오차가 재위치 추정 관문 성공을 뜻하지 않는다.

최종 R3 수치(전체 실행의 발행 시작 지도 좌표계, 보정=RGB/정지 검사 포함):

|조건/seed|명령 xy 중앙/p95(m)|보정 xy 중앙/p95(m)|명령/보정 yaw p95(°)|RGB 막힘 구간/누적 SIM초|평가 기하 위험 SIM초|첫 carry 대비 최대 변위(m)|
|---|---|---|---|---|---|---|
|candidate93266|.444/1.152|.277/.387|31.477/18.303|8/.8|1.3|3.131|
|candidate93315|.116/.203|.062/.139|24.222/16.786|10/1.0|0|2.273|
|density93266|.473/.614|.365/.491|22.639/11.988|0/0|0|1.035|
|density93315|.077/.235|.096/.254|15.167/15.208|0/0|0|1.992|

R1 off→R3 candidate의 보정 xy/yaw p95는93266 2.294m/89.726°→.387m/18.303°,93315 1.149m/90.268°→.139m/16.786°였다. **주행 거리·단계가 달라 완주 drift 개선으로 해석하지 않는다.** 시작 정답에 맞춘 명령 좌표계 오차와 carry/destination 단계별 분포도 summary.json에 분리했다. R2의93266 명령 yaw p95=168.986°와 기하 위험73.6SIM초도 metrics/세부 원장에 남겼다.

R3의 관측된 운반 횡 pulse는4회 모두0이었다. 목적지 획득은 진입0이므로 해당 새 분기의 물리 검증은 미완료다. density의 실제 순수회전 pulse는 각각106/102개, 전부100ms였으나93266 이동 범위가 짧아 채택하지 않았다. RGB 정지0도 실제 막힘0의 증명이 아니다. candidate의 unknown_texture frame은1103/1231개로 관측 불충분이 많이 남았다. 기준선의 정지 검사는 off/미측정이다.

평가 기하 위험은 초기 빔과 차체, 정적 벽과 화물의 SAT proxy이며 실제 접촉력과 다르다. candidate93266의1.3초는 wall_divider_1의 세 구간으로 최대 침투 약0.129mm였다. RGB만으로 막은 물체/최소 틈을 모르면 명시적으로 unknown/null과 사유 범주를 기록했다. 초기 분석 interval의0은 그룹화 sentinel이었으며 최종 summary에서는 미측정 null로 표기했다. 물리 원본을 수정하지 않았다.

## 거부·관문·전체 계획

각 대기열의 절대 `rejection_table`은 이전 탐색 표와 연결한다. [R1](round1/rejection-table.json), [R2](round2/rejection-table.json.zst), [R3](round3/rejection-table.json.zst)에 순서별 누적 통과·거부, 물체·최소 틈과 재현 명령을 보존했다. R3 운반별 funnel은 시작1→들기1→운반1→추정 도착0→place_view0→전진0→하강0→열기0→place0이다.

R3 direct-route overlap 재계획 원장(서로 다른 물리 충돌 사건 수가 아님):

|조건|물체|횟수|최소 틈(m)|
|---|---|---|---|
|candidate93266|wall_divider_1 / wall_divider_2 / own_rgb_cyan_track_1|205 /53 /21|−.280/−.280/−.350|
|density93266|wall_divider_2 / own_rgb_cyan_track_1|286 /76|−.280/−.350|
|candidate93315|wall_divider_1|256|−.280|
|density93315|wall_divider_1|362|−.280|

위 시도는 각각279/362/256/362개의 우회 경로로 재계획됐다. 지속 frame별 마지막 사유 집계는 같은 이벤트가 반복될 수 있어 위 이벤트 원장과 구분한다. 마지막 검사 edge 하나로 막은 물체를 확정하지 않도록 전체 거부 search edge 물체 분포도 기록한다.

[전체 계획 재검사](round3/full-plan-audit.json.zst)는 첫 held travel의 자기 추정 위치·명령 FK·자기 RGB 기억·정적 지도만으로 목적지5곳 모두의 경로 edge/내려놓기 전진/후퇴를 검사했다. 네 조건 모두5/5였다. R2는93266 5/5,93315 1/5였다([R2](round2/full-plan-audit.json.zst)). 이 재생은 전체 실행 성공·실제 충돌 회피·다중 화물/빔 짝 E2E 검증이 아니다. 앞선26.8SIM초 counterfactual과는 추정 상태/시점이 다르다. RGB 기억을 전부 지우는 진단은 실행에 채택하지 않았다.

## 검증·영상·남은 문제

[비물리 검사64 passed](verification.json). R1 default-off는 reloc19와 명령5,555개·영상4,444개 hash가 일치했다([동등성](round1/off-replay.json)). 모든16시도 입력 감사 계수 `invisible_measurements=0`, `held_world_reads=0`; 그중1회는 제어 전 설정 실패의 초기0이고 실제 제어 시작은15회다. 평가용 wheel/contact/정답은 제어 입력에 연결하지 않았다. 감사는 시뮬레이터 독립 검증/실물 성공을 뜻하지 않는다.

기존 CI 실패4개를 reloc19 `b73e815f6`에서도 재현했다([근거](ci-baseline-blockers.json)). frozen source 보존 검사3개와 disk report1개이며 관련 파일을 이 PR에서 바꾸지 않았다. 전체 CI 통과나 병합 준비로 보고하지 않는다.

[직접 영상 검토와 시간순 타임라인](playback-review.md), [영상·12개 실패 프레임과 SHA](artifact-receipts.json). R1 실패2개·R2 실패2개·R3 실패2개에서 전체2Hz와 끝10초10Hz를 직접 확인했다. 검토 영상은 모두4배속/8MB 이하이고 ffprobe로 확인했다. 프레임이 있는15회 각각 마지막10SIM초 기록 및 실패6장을 생성했다. 제어 전 설정 오류1회는0프레임이다. 성공0이므로 성공1개 영상 대조는 미충족이다. Mac 회수 원본 manifest87/62/99파일은 모두 hash 일치하며, 후속 파생 자료는 별도 delivery/artifact receipt에 연결했다.

남은 핵심은 운반 중 RGB 운동 관측이 자격을 잃는 구간과 회전/경로 진행 부족, 목적지 획득·배치 미도달이다. 새 후보는 모두 기본 off를 유지한다. 실물에 맞는 구동 검증, 실제 완주와 목적지 분기의 물리 검증이 더 필요하며 승인된3라운드를 넘겨 실행하지 않았다. 다른 lease·UGRP 실행 프로세스가 없음을 확인하고 자기 lease를 지운 뒤 gcp2를 정지했다. 최종 **TERMINATED**, 원본 디스크는 보존했다([호스트 기록](host-lifecycle.json)).
