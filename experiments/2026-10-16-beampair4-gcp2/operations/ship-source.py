import subprocess,sys
sha=subprocess.check_output(['git','rev-parse',sys.argv[1]],text=True).strip()
base=sys.argv[2]
pack=subprocess.Popen(['git','pack-objects','--revs','--stdout'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
r=subprocess.Popen(['ssh','gcp2','flock /home/ugrp/ugrp-sim/git-shared.lock git --git-dir=/home/ugrp/ugrp-sim/git-shared.git index-pack --stdin'],stdin=pack.stdout)
pack.stdout.close();pack.stdin.write((sha+'\n^'+base+'\n').encode());pack.stdin.close()
assert pack.wait()==0 and r.wait()==0
subprocess.run(['ssh','gcp2',f'git --git-dir=/home/ugrp/ugrp-sim/git-shared.git update-ref refs/heads/beam-source-{sha} {sha} && git clone -q --no-local --no-checkout --reference /home/ugrp/ugrp-sim/git-shared.git /home/ugrp/ugrp-sim/git-shared.git /home/ugrp/ugrp-sim/src/{sha} && git -C /home/ugrp/ugrp-sim/src/{sha} checkout -q --detach {sha} && ln -s /home/ugrp/ugrp-sim/ugrp/.venv-sim /home/ugrp/ugrp-sim/src/{sha}/.venv-sim'],check=True)
print(sha)
