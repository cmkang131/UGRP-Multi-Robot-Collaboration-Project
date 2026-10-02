import os, pathlib, subprocess, sys
scratch=pathlib.Path(__file__).parent
candidate=scratch/'candidate'
review=pathlib.Path('/Users/changmin/projects/ugrp-wt/review-351')
suite=sys.argv[1]
env=dict(os.environ)
env.pop('PYTEST_ADDOPTS',None)
env.update(PYTHONPATH=str(scratch/'guard')+os.pathsep+str(candidate), PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1', GIT_OPTIONAL_LOCKS='0', REVIEW_351_ROOT=str(candidate), GIT_DIR='/Users/changmin/projects/ugrp/.git/worktrees/review-351', GIT_WORK_TREE=str(candidate))
files = ['tests/test_final_pair_calibration_assembly.py','tests/test_review_351.py','tests/test_review_351b.py','tests/test_consumer_criterion_b.py','tests/test_final_environment_unloaded_fit.py','tests/test_zone_final_pair_v3.py','tests/test_zone_final_pair_review_fixes.py','tests/test_ci_sharding.py'] if suite == 'related' else [str(review/'tests'/('test_review_'+name+'.py')) for name in (['351','351b'] if suite=='original' else ['351c'])]
cmd=['/opt/anaconda3/bin/python3','-B','-m','pytest','-q',*files,'--runxfail','-p','no:cacheprovider','--basetemp='+str(scratch/(suite+'-tmp')),'--junitxml='+str(scratch/(suite+'.xml'))]
with (scratch/(suite+'.txt')).open('w') as stream:
    code=subprocess.call(cmd,cwd=candidate,env=env,stdout=stream,stderr=subprocess.STDOUT)
print((scratch/(suite+'.txt')).read_text())
sys.exit(code)
