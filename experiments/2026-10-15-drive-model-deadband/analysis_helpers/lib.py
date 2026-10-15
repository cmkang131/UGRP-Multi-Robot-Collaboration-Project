import json,subprocess,os,math
GAIN=.0325*150*2*math.pi/60
LYX=.1255
def zl(p):
    if p.endswith('.zst'): return subprocess.run(['zstd','-dc',p],capture_output=True,check=True).stdout.decode().splitlines()
    return open(p).read().splitlines()
def find(d,n):
    for suf in ('','.zst'):
        if os.path.exists(f'{d}/{n}{suf}'):return f'{d}/{n}{suf}'
def rawdir(run):
    return run+'/raw' if os.path.exists(run+'/raw') else run
def cdelta(wheels,dur,dt):
    a,b,c,d=[w*min(dt,t) for w,t in zip(wheels,dur)]
    return GAIN*(a+b+c+d)/4,GAIN*(-a+b+c-d)/4,GAIN*(-a+b-c+d)/(4*LYX)
def wrap(a):return math.atan2(math.sin(a),math.cos(a))
