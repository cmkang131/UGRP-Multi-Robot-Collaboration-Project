# warp8d — native contact 관문 인수 (빔40 실행 중)

`nocap-ack nocpu-ack nativecontact-ack cap-ack ownership-ack`.
사용자 2026-10-16 23:1x 결정에 따라 `warp_native_contact_v1`로 빔40 → release A40 → B40을 새로 잰다.
warpfit PR #562 / `df5a1f86aad420f2fab2c10e3ee77cdb5ec11807`의
`sim/warp_native_contact.py`를 byte 그대로 가져왔으며 SHA-256은
`a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`다.
NoSlip0·elliptic·implicitfast·impratio5·Newton/LS80/50을 전 세계에서 검사한다.
기존 legacy-plane/dense capacity/C3.16 호환은 유지한다. 관련 비물리33PASS.

noslip10 빔R2의40/40은 역사적 별도 결과다. release A-S1은 조정자 SIGINT로
`SUPERVISOR_STOP / not_a_defect_profile_switch`이며 미완료다. 정확한 프로세스 exit code는
회수되지 않아 추정하지 않는다. 새 관문과 noslip10·CPU beampair7/release25·다른 호스트 결과는 합산하지 않는다.
원본은 gcp3에서 보존한다.

gcp3는 상한 없이 시작했고 live scheduling에서 `maxRunDuration`과
`instanceTerminationAction`이 없음을 확인했다. 자체 wall 시한도 없다. idle20·budget-stop 유지.
분석은 gcp3 CPU만 사용하며 CPU VM 시작0. 새 모델키·에이전트 자격증명 전송0.
[현재 실행 계획](native-gate-plan.json), [호스트 검증](native-host-start.json), [프로필 출처](native-preflight.json).

새 XML 참조80개를 gcp3 CPU에서 C3.12로 재컴파일했고 기존 참조의 actuator/material/geometry
배열 전수 일치를 확인했다. 빔40을14:25:57Z에 제출했다(driver3149/child3151, source3170d909).
[현재 대기열](native-gate-queue.json), [제출 근거](beam40-native-r1-submit.json). 준비 중 상대 asset 경로 오류1회와 camera housing 표시그룹 차이2회는
물리·교사 관문 실행이 아니며 원본/실패 산출물을 보존했다. 표시그룹의 근거는
`sim/multi_masterpi_production.py:930-933`의 로봇별 camera housing 숨김이다.
성공 조건·제어·접촉 상수는 추가하지 않았다.

warp8d가 앱 재시작 뒤 기존 PID3149/3151을 인수했다. 중복 제출0이며
실제 scheduling 상한 두 필드가 비어 있고 idle20은 ACTIVE임을 재확인했다.
[인수 원본 상태](warp8d-resume.json). SSH 별칭의 사라진 로컬 proxy 경로는
설정을 바꾸지 않고 명시적 gcloud 조회 IP·기존 strict host key로 접속했다.
첫30SIM 속도는 완료 뒤 noslip10 기준5.60/8.72와 나란히 기록한다.

아래는 noslip10 당시 기록이다. 그 안의8h 복원·CPU VM 분석 지시는 최신 사용자 지시로 폐기됐다.

---

# warp8 — gcp3 빔 짝·release MJWarp 관문 (빔 R2 40/40, release A-S1 진행)

warp6와 같은 `codex/warp6`, PR #557 DRAFT에서 이어간다. gcp2 R3의 CUDA700은
gcp3 단독·MPS off·원래 graph 25.3 SIM초에서 **단독 환경에서 미재현**이었다.
공유 GPU/MPS 다중 client와 양립하지만 원인을 확정하지 않는다.
새 CUDA700 발생 시 해당 시드만 memcheck로 재현하고 같은 결함 3라운드면 중단한다.

빔40세계 한 배치, release A40·B40을 계획한다. release A40의 단일 배치 참조 초기화는 `canonical model free-root names differ`로
거부됐다. 서로 다른 모델 topology를 유지해 A/B 각각 S1 14·S3 13·S6 13으로
분리한다. 각 시나리오의 A/B plan은 바이트가 아닌 JSON 값으로 전수 동일함을 확인했고
참조는 실제 XML SHA로 엄격하게 대조한다. 메모리 부족은 세계 수를 줄여 실측을 기록한다.
판정 속도 = 배치 wall / (배치 SIM초 × 세계 수)다. 완료 세계의 padding도 이 물리 처리량 분모에 포함한다.
완료 시각을 반영한 실제 작업 처리량은 별도로 기록하며 판정에 섞지 않는다.
기존 >6 차단을 실행당 환산값에 적용하는 것은 **조정자 결정, 사용자 미확인**이다.
첫30SIM은 본 실행에서 측정하며 setup/compile 비용은 따로 적는다.
물리·NoSlip·시간 간격·성공식·교사 제어를 바꾸지 않는다.

새 후보는 placement_graspable_filter_v1 ON, weld OFF, held_world_reads=0,
학습RGB OFF, 모델호출0, 기존 계산량 예산 ON이다. 실패10SIM/10Hz 디스크 ring을
유지하고 cap_end·HOST_ERROR를 분리한다. CPU beampair7/release25·다른 호스트와 합산하지 않는다.
입력은 warp6 준비본의 알려진 실패 시드 우선 순서를 유지한다.

호스트는 gcp3 / ugrp-sim-c-1016 / ugrp-act-l4-gcp3 / L4 단독이다.
사용자 결정에 따라 VM·드라이버 wall 상한을 없애고 유휴20분·budget-stop을 유지한다. 작업 종료 후 타작업 부재를 확인해 정지한다.
gcp2 L4·gcp1을 건드리지 않는다. VM에 모델키·에이전트 자격증명은 보내지 않는다.
분석은 원본이 있는 gcp3 CPU에서만 한다. ugrp-sim-gcp2를 시작하지 않는다. Mac 회수는 요약·몽타주·실패 프레임과
8MB 이하 대표 성공1·실패1 영상이며 GUI를 열지 않는다.

원래 빔 관문 소스는 `f75e3442957e8e00c4ed894056b3e06ee32399f0`로 고정했다.
그 뒤 완료 세계 padding을 판정 분모에서 빼려던 기록 변경은 사용자 지정 식과 달라
채택하지 않았다. 후속 실제 실행은 지정 식을 명시한 소스35e94d5d 이후를 쓴다.
진행 중 빔 소스와 원래 기록은 유지하고, 원본으로 물리 처리량과 실제 작업 처리량을
각각 다시 센다. 제어·물리는 불변이며 관련 비물리11PASS다.

## warp8b 재개 지시 — 현행 운영 규칙

`nocap-ack nocpu-ack ownership-ack cap-ack`. 아래 과거 기록의 "8h 유지"·자체 정리 시한·gcp2 CPU 분석은 잘못 적용한 운영이며 후속 지시로 대체됐다. 사용자 "상한 좀 없애라고"가 우선한다. gcp2 CPU VM을 분석 때문에 다시 켜지 않는다.

13:48:34Z 제출된 release A-S1 14세계(driver1738/child1740)를 인수했고 중복 제출하지 않았다. VM 상한28800초/STOP과 기존 드라이버21:14Z 시한이 실제로 남아 있음을 조회했다. A-S1 종료 경계에서 gcp3 정지→상한 두 필드 clear→비어 있음 확인→상한 인자 없이 시작하며 다음 그룹으로 간다. 21:00Z까지 완료 전망이 아니면 그 전에 안전한 경계를 만든다. 신규 드라이버는 wall 시한을 읽거나 SIGINT하지 않으며, 비물리 가짜 시계 시험1PASS로 확인했다. 기존 작업 SIM 상한·물리·제어는 그대로다. VM 상한 제거 완료는 실제 경계에서 확인한 뒤 별도로 기록한다.

## R1 관문 중단과 R2 후보

`beam40-r1`은 control225/+22.5SIM까지 정상 저장 뒤 step226에서 world008/seed8318706의
NVMAX bit128로 중단됐다. 완료 성공1(world028, task17.4SIM), cap_end0, 미완료 HOST_ERROR39다.
물리 실패0이라는 뜻이 아니라39건의 물리 결과를 모른다는 뜻이다. CUDA700은 미재현이다.
첫30SIM은 미완료라 속도 관문 통과로 보고하지 않는다. [원본 거부표](beam-r1-rejection_table.json).

실제 초기110→할당128, 마지막 활성156, 총 nv222다. 기본off `full_active_dof_workspace_v1`로
공식 기본 방식인 정확한 전체 nv를 할당하는 후보를 만들었다([근거](references.md)). NoSlip10,
dt, 접촉·마찰·m.opt solver 설정과 행동 경로는 유지한다. upstream compact 정규화의 pad/ctol은
할당 크기에 따라 바뀌므로 기록하며 바이트 동등성을 주장하지 않는다. 관련 비물리30PASS다.
R2는 새 실패seed8318706을 맨 앞에 놓고 원래 canonical XML과40건의 참조를 재사용한다.
R1과 R2는 합산하지 않는다. R2는08:38:49UTC 제출했고 아직 완료되지 않았다. release는 미제출이다. R2 고정 소스는 `175281c8922453465f8bf32707e22988e78b8812`다.

성공1개·HOST_ERROR1개의 원본 재계수와 대표 영상을 회수했다. full2Hz의 초기0.5SIM 동기화 오류는
native NPZ로 고쳐 중복174/221행 qpos가 비트 일치함을 확인했다. 수정본 전체2Hz36/46장과
마지막10SIM/10Hz 각100장을 전부 봤다. [대표 영상·검증](representative-native-sync.json),
[영상 검토](playback-review.md). 원래 파생본은 보존하고 수정본을 최종 대표 영상으로 쓴다.

R2 제출 전 실제 VM scheduling에서8h 필드가 제거된 것을 확인했다. warp8의 명시적8h 유지 지시에 따라
타 lease/GPU client 부재 확인 후 gcp3만 정지했고, maxRunDuration28800/STOP을 복원·조회했다.
재시작으로 VM 상한 기준 시각이 바뀌어도 현재 빔 세션의 기존 정리 시한14:05UTC는 연장하지 않는다.
빔이 정상 완주하면 VM 정지·원본 검증 후 release를 별도 유한 세션으로 진행한다.
시간·budget-stop이 실제 발동하면 새 실행을 내지 않는다. 각 세션의8h STOP·idle20·budget-stop을 유지한다.
[설정 복원 기록](scheduling-restored.json). gcp2는 변경하지 않았다.

R1의별도재계수는실제`claude-haiku-4-5-20251001`이생성한독립판정코드를gcp2 CPU에서실행해확인했다.
작업자가상태명complete·누락감사필드·SHA메타타입만스키마에맞췄으며물리계산은바꾸지않았다.
결과complete1/HOST_ERROR39,175평가행·연속hold3.0000000000000036초·교사2/2,
원본과불일치0·오류0·입력감사0값40건(전체1/prefix39)으로기존계수와같다.
[R1 Haiku코드실행결과](R1-haiku-counter-result.json), [코드/보정근거](R1-haiku-counter-provenance.json).
모델의문장응답은원본증거로쓰지않았고,잘못된상태분류/소스불일치지적을거부했다.

## R2 첫30SIM 원본 점검 (전체40관문은 진행 중)

배치 loop6,722.934wall초/(30SIM×40)=**5.6024**로조정자차단기준6.0미만이며3.5경고다.
원래기록의보조값5.7466은진행중세계와완료세계의시작시각기준이섞여있다.
원본평가시작시각으로통일한교사작업처리량은5.8288이다([시각검증](R2-first30-episode-clock.json)).
이수정은보고용이며수용값5.6024와원본JSON은변경하지않는다. setup/compile408.9초는제외했다.
[측정](R2-first30-speed.json),[CPU재계수/단계](R2-first30-analysis.json),[관문/거부표](R2-first30-rejection_table.json).
완료7세계는독립평가원장재계수7/7일치,나머지33은진행중이다. CPU원본스냅샷1,277파일SHA일치·JSON오류0.
40세계저장진단감사0값은완료7의전체결과와나머지33의진단시점prefix범위이며전체관문통과가아니다.
최빈거부기록은peer_destination_reservation5,270건이다(고유후보수가아님). 영상과종료결과없이실패원인으로단정하지않는다.

알려진시드world000의+.5~29.5SIM2Hz59장·+20.1~29.9SIM10Hz99쌍,성공world028의+.5~17.5SIM2Hz35장·+8.0~17.9SIM10Hz100쌍을모두직접봤다.
진행중RGB100쌍해시는모두맞지만최신1프레임평가상태는다음틱에저장되어개요동기화는99쌍이다.
종료영상의100쌍요구는유지했다. live NPZ는아직저장되지않아startup처음.5SIM은이미지개요에서빠졌고,현재미리보기를전체원본영상으로주장하지않는다.
[회수/시각범위검증](R2-first30-playback-verification.json). Mac에새영상은가져오지않고몽타주와메타만회수했다.
현재새제어결함을확정하지않았고R2를계속한다. release는미제출이다.

알려진NVMAX시드8318706은R2에서task38.1SIM에양교사성공으로종료했고,CPU재계수382행·연속hold3.0초·입력감사0/0·weld off를확인했다.
2Hz77장/마지막10Hz100쌍을모두직접봤다([원본검증](R2-known-seed-success.json)). 전체40완료나CUDA700원인확정으로확대하지않는다.

12:14UTC 진행 스냅샷은42.9SIM·성공31/진행9·오류0·cap_end0이다. 누적환산7.2849는첫30수용5.6024와구분하며전체속도통과를주장하지않는다.

## R2 종료 검증

고정 소스175281c8922453465f8bf32707e22988e78b8812의 빔40 배치는 종료코드0, **성공40/40·cap_end0·HOST_ERROR0**이다. 물리 배치52.5SIM(스케줄러 마지막 tick 표시는52.6), loop17,238.570wall초이며 환산8.2088이다. 실제 교사 작업 합계1,472.3SIM 기준은11.7086이다. 첫30 판정5.6024는 통과/3.5경고이고, 전체 속도 통과로 확대하지 않는다. setup408.9초는 별도다.

CPU 원본 재계수40/40, Haiku 생성 독립 코드 재계수40/40·불일치0, 전체 입력감사40건 held_world_reads=0/invisible_measurements=0, weld off. [원장 재계수](R2-summary.json), [독립계수](R2-haiku-counter-result.json), [검증/자원](R2-terminal-validation.json). GPU 사용률 중앙값100%(1,762표본), physics가 loop94.2%이므로 후반 지연을 GPU가 놀기 때문이라고 단정하지 않는다. NoSlip10은 유지했다.

선언 원본26,060파일/382,010,624바이트 SHA 전수 일치([검증](R2-native-integrity.json)). summary와 manifest 자체는 선언 목록 밖이며, 종료 전송925파일 해시와 대표 선택 snapshot1,558파일 해시에서 따로 확인했다. 대표 성공13파일·108KB 영상과 전체78/최근100쌍을 Mac에서 검증했다([영상](R2-representative-artifacts.json)). R1과 CPU 결과는 합산하지 않는다.

gcp3는 타 lease/작업PID/GPU client 부재를 확인한 뒤 정지했고13:37:28UTC TERMINATED를 확인했다. 정지 직후 별도 set-scheduling 호출로8h 필드가 없어졌음을 감사로그에서 확인하여 정지 상태에서28800초/STOP을 다시 설정했다. 실행 중12:14UTC 변경 시도는 API가 거부했다([로그](R2-scheduling-audit.json),[정지](R2-host-stop.json),[복원](release-scheduling-restored.json)). release는 미제출이며 전체 MJWarp 전환/데이터 수용은 아직 not-ready다. 정상 종료한 빔 세션과 별개의 유한 release 세션에서도8h STOP·idle20·budget-stop을 유지한다.
