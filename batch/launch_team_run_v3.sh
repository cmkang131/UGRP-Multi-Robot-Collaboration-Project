#!/bin/bash
# launch_team_run_v2.sh 의 후속(2026-11-15). 작업 VM 개발 실행 + 이 서버의 계획기. v2 와 같되:
#  - SERVER_ARGS(계획기 brain_server.py 추가 인자, 예 "--pre-exchange --option-order reverse")를 받는다.
#  - brain_server.py 위치는 BRAIN_DIR(기본 이 저장소의 team/). 기록은 EVIDENCE_DIR(기본 이 폴더의 evidence/physical).
#  - 끝날 때 종료 코드를 $EVIDENCE_DIR/<이름>.exit 에 남긴다(임시 파일 후 mv). TERM/INT 이면 143.
#  - 포트가 차 있으면 +1 씩 올리되 PORT_SPAN(기본 10) 칸 안에서만(다른 run 의 포트를 밟지 않게). 실패 96.
#  - 계획기가 바로 죽으면(예: 모르는 인자) ssh 로 넘어가지 않고 97. VM 접속 불가는 99(시작 안 한 것). 이름 중복(기록 폴더 있음) 98.
#  - NO_BRAIN=1(VM 인자에 --fixed 가 있는 기준선 실행): 계획기 서버를 안 띄우고 --brain-url 도 안 준다. run_team_carry.py 는
#    --brain-url 이 있으면 --fixed oracle 을 무시하고 LLM 계획기를 쓰기 때문이다. 기록 폴더만 만들어 이름 중복(98)을 막는다.
#  - ssh 의 종료 코드를 kill/ALERTS 보다 먼저 잡는다.
# Usage: VMHOST=<VM address> VM_WORKDIR=<folder on the VM> VMRUN=run_team_vNN.sh OUTROOT=<VM 결과 폴더> [VM_USER=<login>] [SSH_KEY=<key file>] \
#        [LEADER=r1] [ROBOTS=r1,r2] [MODEL=...] [SERVER_ARGS="..."] \
#        launch_team_run_v3.sh <sha> <team T0|T1|T2> <seed> <name> <port> [VM 실행 인자...]
# FAKE_LAUNCH=1 : ssh·계획기 없이 fake_launch.py 가 FAKE_VM_ROOT/<VMHOST>/ 아래에 가짜 결과를 쓴다(시험용).
sha=$1; team=$2; seed=$3; name=$4; port=$5; shift 5
: "${VMRUN:?set VMRUN (VM run script, e.g. run_team_v31.sh)}"; : "${OUTROOT:?set OUTROOT (VM result folder)}"
LEADER=${LEADER:-r1}; ROBOTS=${ROBOTS:-r1,r2}; MODEL=${MODEL:-z-ai/glm-5.3-flash}
SERVER_ARGS=${SERVER_ARGS:-}; NO_BRAIN=${NO_BRAIN:-0}; WALL_CAP=${WALL_CAP:-4.5h}; PORT_SPAN=${PORT_SPAN:-10}; RUN_ALERT=${RUN_ALERT:-1}
# WALL_CAP: VM-side wall-clock cap per run (PREREG D5; 4.5 h, above the 14400 s rollout cap in run_grasp_act_student.py so the code cap fires first); GNU timeout exits 124 when it fires
here=$(cd "$(dirname "$0")" && pwd)
BRAIN_DIR=${BRAIN_DIR:-$here/../team}
EVIDENCE_DIR=${EVIDENCE_DIR:-$here/evidence/physical}; log=$EVIDENCE_DIR/$name
DEFAULT_ALERTS=outputs/batch-alerts.log; ALERTS=${ALERTS_LOG:-$DEFAULT_ALERTS}
sshopt=(); [ -n "$SSH_KEY" ] && sshopt=(-i "$SSH_KEY")   # no key given: the ssh default identity
if [ "$FAKE_LAUNCH" = 1 ]; then
  VMHOST=${VMHOST:?FAKE_LAUNCH needs VMHOST}; : "${FAKE_VM_ROOT:?FAKE_LAUNCH needs FAKE_VM_ROOT}"
  [ "$ALERTS" = "$DEFAULT_ALERTS" ] && { echo "FAKE_LAUNCH refuses the real alert log; set ALERTS_LOG" >&2; exit 2; }
else
  VMHOST=${VMHOST:?set VMHOST (address of the work VM)}; : "${VM_WORKDIR:?set VM_WORKDIR (folder on the VM that holds the run script)}"
  target=${VM_USER:+$VM_USER@}$VMHOST   # no VM_USER: the ssh default login
fi
[ -n "$PIDFILE" ] && echo $$ > "$PIDFILE"   # dispatch.py reads this to re-adopt a live launcher after a restart
mkdir -p "$EVIDENCE_DIR"
[ -e "$log" ] && { echo "evidence dir exists, name reused: $log" >&2; exit 98; }   # .exit 를 덮어쓰지 않는다
rm -f "$EVIDENCE_DIR/$name.exit"   # 앞선 시도가 99(시작 못 함)였다면 남은 .exit 를 지운다: 중단됐을 때 낡은 99 로 읽히지 않게

server=""; sshpid=""; rc=1
finish() {
  if [ -n "$sshpid" ]; then
    kill "$sshpid" 2>/dev/null
    # 2026-11-16: killing the local ssh left the VM-side run alive (5 orphans). The remote run records its process
    # group in $VM_WORKDIR/.launch-pgid/<name>; stop that whole group too.
    [ "$FAKE_LAUNCH" = 1 ] || timeout 30 ssh "${sshopt[@]}" -o BatchMode=yes -o ConnectTimeout=15 "$target" \
      "g=\$(cat $VM_WORKDIR/.launch-pgid/$name 2>/dev/null) && [ -n \"\$g\" ] && kill -TERM -- -\$g" 2>/dev/null
  fi
  [ -n "$server" ] && kill "$server" 2>/dev/null
  printf '%s\n' "$rc" > "$EVIDENCE_DIR/$name.exit.tmp" && mv -f "$EVIDENCE_DIR/$name.exit.tmp" "$EVIDENCE_DIR/$name.exit"
  [ "$RUN_ALERT" = 1 ] && echo "$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') [팀 실행 끝] $name ($team, leader $LEADER, $MODEL, seed $seed, rc=$rc)" >> "$ALERTS"
}
trap 'rc=143; exit 143' TERM INT
trap finish EXIT

# VM 접속 확인(시작 전). 실패 = 99, 아직 아무것도 시작하지 않았다.
if [ "$FAKE_LAUNCH" = 1 ]; then
  [ -e "$FAKE_VM_ROOT/$VMHOST.down" ] && { echo "VM unreachable (fake)" >&2; rc=99; exit 99; }
else
  ssh "${sshopt[@]}" -o BatchMode=yes -o ConnectTimeout=15 "$target" true || { echo "VM unreachable" >&2; rc=99; exit 99; }
fi

# 빈 포트: port 부터 +1, PORT_SPAN 칸 안에서만.
p=$port
while ss -ltn | grep -q ":$p "; do
  p=$((p+1)); [ "$p" -lt $((port+PORT_SPAN)) ] || { echo "no free port in $port..$((port+PORT_SPAN-1))" >&2; rc=96; exit 96; }
done
port=$p

printf -v vmargs '%q ' "$@"
if [ "$FAKE_LAUNCH" = 1 ]; then
  python3 -B "$here/fake_launch.py" "$sha" "$team" "$seed" "$name" "$port" "$@" &
  sshpid=$!; wait $sshpid; rc=$?; sshpid=""
elif [ "$NO_BRAIN" = 1 ]; then
  mkdir -p "$log"
  ssh "${sshopt[@]}" -o BatchMode=yes -o ServerAliveInterval=30 "$target" \
    "cd $VM_WORKDIR && mkdir -p .launch-pgid && setsid --wait sh -c 'echo \$\$ > .launch-pgid/\$0; exec \"\$@\"' $name timeout --kill-after=60 $WALL_CAP ./$VMRUN $sha $seed $OUTROOT $name $vmargs" &
  sshpid=$!; wait $sshpid; rc=$?; sshpid=""
else
  read -r -a sargs <<< "$SERVER_ARGS"
  python3 -B "$BRAIN_DIR/brain_server.py" --team "$team" --robots "$ROBOTS" --leader "$LEADER" --model "$MODEL" --port "$port" --log-dir "$log" "${sargs[@]}" > "$EVIDENCE_DIR/$name.server.log" 2>&1 &
  server=$!
  sleep 3
  kill -0 "$server" 2>/dev/null || { echo "brain_server exited early; see $EVIDENCE_DIR/$name.server.log" >&2; rc=97; exit 97; }
  ssh "${sshopt[@]}" -o BatchMode=yes -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -R "$port:localhost:$port" "$target" \
    "cd $VM_WORKDIR && mkdir -p .launch-pgid && setsid --wait sh -c 'echo \$\$ > .launch-pgid/\$0; exec \"\$@\"' $name timeout --kill-after=60 $WALL_CAP ./$VMRUN $sha $seed $OUTROOT $name --brain-url http://localhost:$port $vmargs" &
  sshpid=$!; wait $sshpid; rc=$?; sshpid=""
fi
exit $rc
