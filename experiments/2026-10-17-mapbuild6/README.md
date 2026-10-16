# mapbuild6 — 실제 운반 경로 녹화 전 관문 실패 / NOT_READY

**ownership-ack. 요구한 실제 운반 경로를 확보하지 못해 LK/RBPF 채택을 판정할 수 없다.** 같은 `codex/mapbuild1`, [PR #556](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/556) DRAFT다. gcp5만 사용했고3회 상한으로 실행을 종료했다. 성공한 지도→ACT 인계·문 통과·구역 도착·복귀·내려놓기/둘러보기는 각각0개다. 수 m 경로·LLM E2E·학생 성공은 미측정이며, 이 기록을 mapbuild5c와 합산하지 않는다.

요구 정확도와 결정 규칙은 녹화 전에 고정했다([요구표](requirements.json), [추출 코드](../../scripts/mapbuild6_requirements.py)). native87420–87459 원본은 gcp5에 없었고 다른 VM에 접근하지 않았다. 사용자가 허용한 기존 교사 원장 대체로 Mac에 보존된 성공40건79800–79839(소스6f057f7e)를 gcp5로 보내 분석했다. 이 과거 CPU 분포는 요구 조건 근거일 뿐 native/학생 성공 자료가 아니다.

|요구 항목|예비 정확도·근거|출처|
|---|---|---|
|근거리 인계 XY|시작 거리 P5/P50/P95=.647563/.848315/1.080183m, 작은 양쪽 여유 **200.751mm**|`/home/ugrp/ugrp-sim/runs/mapbuild6/teacher-ledgers/*/plan.json` 및 대응 성공 result, 각SHA는 요구표|
|인계 방향|`abs(yaw error)+atan2(XY error,.848315-XY error) <= 21.423317°`(성공 시작의 대상 시선 오차P95)|동일40건. 원시 시작 XY 구름의 P95 반경815mm를 위치 허용오차로 쓰지 않음|
|자리 중심·자리 구분|자리 중심60mm, 최근접 자리 구분200mm(자리 간격400mm/2)|`maps/zones/zone_wide_door_geometry_v3.json`: `zone_slots`|
|화물이 구역 안|작은 구역 반폭300mm−상자 최대 반폭20mm=280mm|동일 지도 `regions`, `sim/zone_arena.py:BOX_HALF`|
|문·통로|차체 baseline에서 `XY+a*abs(sin(yaw))+b*abs(cos(yaw)) <= width/2`, a=.120m,b=.105m. 폭.5m·yaw0의 여유145mm|지도 `passages`, `harness/zone_team_footprint.py`의 원래 측정 차체 외곽. 팔/적재 화물 전체 외곽은 별도 검증 필요|

인계 표는 중앙 거리에서의 경험적 **예비 예산**이며 학생 성공 허용범위·결합95% 보장을 뜻하지 않는다. 요구표의 시작 XY 중앙값은 분포 설명값이며 실제 인계 목표로 적용하지 않았다. 실제 지도→ACT 인계가 없어 이 표의 인수도 미완료다. 과거 `handoff_pose_error` P95=115.472mm/3.967°는 내려놓은 뒤 위치 추정에 주입한 별도 오차라 인계 시작 분포와 섞지 않았다.

사전 결정 규칙은 모든 필수 지점에서 둘 다 통과하면 LK 기본/RBPF off, LK만 실패하고 RBPF만 통과하면 RBPF, 둘 다 실패하면 원인표와 다음 묶음 제안만이다. 필수 경로 자체가 빠지면 **미측정/채택 보류**다. 이번 결과는 마지막 경우다. 두 방법의 요구 정확도 통과/실패를 가상의 도착 시각에서 만들지 않았다. 상수 재맞춤·척도 fitting은0이다.

시도는 `s1_normal_mixed_v7`의 cyan_2→A였다. 과거 성공 교사의 자기 발행 휠/PWM prefix를 native에서 재생한 뒤 지도 주행에 연결하려 했으나, 실제 파지부터 실패했다. v7 화물·지형은 표준 장면이지만 로봇 시작은 과거 원장의 진단 spawns를 썼다. arena_default v7 실행의 결과로 승계하지 않는다. 이 녹화 어댑터 선택은 실제 닫힌 루프 native 운반 실행을 확보하지 못했다. 과거 교사의 성공을 재생 성공으로 승계하지 않는다.

|시도|소스·결과|실제 자료|
|---|---|---|
|R1|60db80c1a… / HOST_ERROR. 기존 v7 질감 확장 인자 누락|물리0. 누락 키는 이미 고정된 gatesv5_release_extension에 있었음|
|R2|f4923f21a… / HOST_ERROR. FK `loaded_or_unknown_load_not_qualified` 예외|14.0SIM초·141자기 프레임|
|R3|**c7477b1f64910f498b52e1697488c28b2c4569e1** / SUPERVISOR_STOP|24.6SIM초·247자기 프레임·차체 이동0.839299m. 지도 주행 발행0|

모두 `warp_native_contact_v1`, noslip0이다. R2→R3는 FK 거부를 unknown으로 기록하는 호출부 수정이며 거부를 풀지 않았다. R3의 lift~hold104프레임에서 담당 상자 바닥 최대 높이−0.108mm, 기존 교사의 필요 들림12mm를 넘긴 프레임 **0/104**다. 같은 종류 cyan_1을 포함한 다른 색 상자도0/104였다([평가](results/diagnosis-r3.json), [전체 상자 확인](results/all-colour-lift-check.json)). 손가락 경계 구의 분리 하한0으로 접촉·마찰·IK 원인을 분리할 수 없으며 특정 접촉 원인으로 단정하지 않는다. 파지 실패가 확인돼 자기 실행만 멈췄다([감독 기록](operations/supervisor-stop-r3.json)).

아래 수치는 **운반 전 접근/파지 재생 prefix 참고값**이다. 실제 필수 지점의 판정값이 아니다. 동일 저장 자기 JPEG/발행 명령, 차체 중심SE(2), 시작 정렬 한 번, 척도1이며 봉인 뒤 평가했다.

|R3·247프레임|LK+명령 fallback|LK+벽 RBPF|
|---|---:|---:|
|XY ATE RMSE /P95 mm|91.867 /114.958|98.054 /122.392|
|최대 XY mm /SIM초|119.328 /7.0|127.313 /7.0|
|종료 XY mm|68.578|72.328|
|yaw RMSE /종료 °|3.617 /3.775|.932 /.435|
|종료 XY/실제 이동 길이 %|8.171|8.618|

[전체 요약](results/r3-summary.json), [R2 별도 참고](results/r2-summary.json). 명령 fallback은 기존 명목 휠 식이며 이 native duty 전 범위를 새로 보정한 모델이 아니다. 온라인·오프라인 LK는 R2 141/141, R3 247/247 bit-exact였다. R2/R3는 reset·발행 prefix가 같아도 차체 궤적은 최대3.450mm/0.939° 달랐다. 호출부 소스도 달라 순수 비결정성 실험은 아니며 합산하지 않는다. 카메라 중심 오차는 이번에 산출하지 않았고 판정에 쓰지 않았다.

[순차 funnel/거부표](rejection_table.json)는 R3 **247→카메라 자격138→명령 자세 불변102→벽 스캔65→정착62→SIM 스케줄7→bootstrap/정합 수용5**다. 정합6회 중 수용4/고잔차 거부2다. 거부2도 기존 정책에 따라 odometry 위치에 지도를 삽입했으므로 지도 삽입7을 정합 성공7로 부르지 않는다.30입자·후보 검사174,704·색 경계 검사291,248이며 wall 상한은 없다. [실제 큐 원표](results/replay-r3-funnel.json), [다음 큐 ready=false](next-queue.json)에 존재하는 절대경로 `rejection_table`을 넣었다.

미측정 사유는 loaded/unknown FK94, servo변화51, rigid consensus26이고 LK측정75다(bootstrap1 별도). 벽 투영 자체가 자격을 얻지 못한 loaded 프레임은109/247이다. 0.1초 증분 잔차 합은 LK측정 구간0.216m가 가장 크고, 다른 세 범주0.077/0.054/0.051m다. 빈도와 최종 누적 오차 원인은 다르므로 “특징점 부족” 또는 “명령 예측만 문제”라고 결론내리지 않는다. 실제 운반·회전/복귀 오차 원인표는 경로가 없어 만들 수 없었다.

입력 감사에는 중요한 제한이 있다. R3 코드의 미실행 지도 분기는 초기 좌표를 설정용 `spawns`에서 가져오도록 되어 있었다. **정적 입력 경계 미통과**이며 실제 발행 명령247개는 모두 과거 prefix와 일치해 그 지도 분기 실행은0이었다([감사](operations/input-boundary-audit.json)). 사후9c4f171c5에서 이 좌표 경로를 제거하고 허용된 자기 RGB 등록이 없으면 `MAP_REGISTRATION_REQUIRED`로 막았다. 이 수정 뒤 새 물리 실행은0이다. raw의 자기 보고0 카운터를 정적 경계/교사 InputAudit 인수로 확대하지 않는다.

절차상 R3 호출부 수정 커밋은 전체 사전 프레임 분포표 저장보다 먼저였다. 로그에서 예외 원인은 확인했지만 “분포표 먼저” 순서는 충족하지 못했다. 이 한계와 실제 경로 부재 때문에 결과·현재 workflow 모두 미인수다. 현재0.1.1 workflow는 전제 진단이며 실제 운반 녹화의 완료 버전이 아니다. 관리 카탈로그를 추가했지만 이번 실제 호출은 직접CLI였고 관리 실행으로 소급하지 않는다.

[영상 직접 검토](playback-review.md)는 R3 개요+r1+r2 전체2Hz/끝10초10Hz다. 같은 native 성공 영상은 없어 성공 대조 요구는 미충족이다. gcp5 ffmpeg/ffprobe만 사용했고 Mac에는 요약·53검토 미디어(해시 일치)만 회수했다. 원본811파일·봉인 예측8파일, frozen renderer3,449파일 해시 불일치0이다([무결성](results/integrity-final.json), [renderer](operations/renderer-integrity.json), [회수](playback-retrieval.json)). 원본은 gcp5 디스크에 보존하며 별도 원격 백업으로 표현하지 않는다.

[재현 명령](reproduce.json), [모든 시도](operations/attempts.json), [환경](operations/environment.json). MuJoCo/MJWarp3.16.0·Warp1.15.0·g2-standard-8이다. git-shared.git이 shallow여서 --reference clone이 거부됐고, 해당 공유 저장소의 git archive만 사용했다. gc/prune·이력 사본 체인은 없다. 모델키·에이전트 자격증명 전송0, Mac 물리/렌더·GUI0, CPU VM 시작0이다. 첫30SIM 속도는 두 실행 모두 미완료이며 부분 wall/SIM10.896/10.421을 속도 통과로 보고하지 않는다.

비물리 `tests/test_mapbuild6.py` **5 passed**, CI 등록/분할 회귀 `tests/test_ci_sharding.py` **68 passed**, diff 검사 통과다. 기본 off, duty/명령 적분, 척도 불변 평가, loaded FK 미자격 시 LK 미호출을 확인했다. 실제 경로·학생·LLM·전체CI·병합 인수는 아니다. [다음 묶음 제안](next-proposal.md)은 native 닫힌 루프 교사 연결·자기 RGB 지도 등록·카메라 자격 공백 해결이며 이번에 실행하지 않았다. 실행 프로세스0·GPU0·타 임대0을 확인하고 자기 임대를 해제한 뒤 직접 정지했다. **gcp5 TERMINATED, 2026-10-17T01:34:44.069000+09:00** ([종료 영수증](operations/gcp5-after-stop.json), [실부하 점검](operations/close-preflight.json)). idle20·budget-stop ACTIVE를 유지했다. 실제 청구 비용은 미측정이다.
