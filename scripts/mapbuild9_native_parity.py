"""Compile unchanged upstream numeric bodies in a tiny ABI shim, on gcp5 only.

Tests numerical translation, not real ROS execution or localization success.
Gaussian draws are supplied identically; no libc/NumPy RNG identity claim.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def body(text, marker):
    start=text.index(marker);brace=text.index('{',start);level=1;end=brace+1
    while level:
        if text[end]=='{':level+=1
        elif text[end]=='}':level-=1
        end+=1
    return text[start:end]


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    root=Path(__file__).resolve().parents[1]
    if not (root/'harness/mapbuild_amcl_vendor').exists():root=a.source
    sys.path.insert(0,str(root))
    import numpy as np
    from harness.mapbuild_amcl_vendor import algorithms as port
    upstream=root/'harness/mapbuild_amcl_vendor/upstream'
    motion=(upstream/'differential_motion_model.cpp').read_text();pf=(upstream/'pf.c').read_text()
    parts=[body(motion,'void\nDifferentialMotionModel::initialize('),body(motion,'void\nDifferentialMotionModel::odometryUpdate('),body(pf,'int pf_resample_limit(pf_t * pf, int k)\n{')]
    prelude=r'''
#include <cmath>
#include <algorithm>
using namespace std;
struct pf_vector_t {double v[3];};
struct pf_sample_t {pf_vector_t pose; double weight;};
struct pf_sample_set_t {int sample_count;pf_sample_t *samples;};
struct pf_t {int current_set;pf_sample_set_t sets[2];int max_samples,min_samples;double pop_z,pop_err;};
static const double *draws;static int draw_index;
double pf_ran_gaussian(double sigma){return sigma*draws[draw_index++];}
pf_vector_t pf_vector_sub(pf_vector_t a,pf_vector_t b){pf_vector_t r;for(int i=0;i<3;i++)r.v[i]=a.v[i]-b.v[i];return r;}
namespace angleutils {double angle_diff(double a,double b){return atan2(sin(a-b),cos(a-b));}}
class DifferentialMotionModel {double alpha1_,alpha2_,alpha3_,alpha4_,alpha5_;
public: void initialize(double,double,double,double,double);void odometryUpdate(pf_t*,const pf_vector_t&,const pf_vector_t&);};
'''
    trailer=r'''
extern "C" void run_motion(int n,double *px,const double *d,const double *a,const double *normal){
 pf_sample_t *samples=new pf_sample_t[n];for(int j=0;j<n;j++)for(int k=0;k<3;k++)samples[j].pose.v[k]=px[3*j+k];
 pf_t pf{};pf.sets[0].sample_count=n;pf.sets[0].samples=samples;
 pf_vector_t delta{{d[0],d[1],d[2]}};draws=normal;draw_index=0;
 DifferentialMotionModel m;m.initialize(a[0],a[1],a[2],a[3],0);m.odometryUpdate(&pf,delta,delta);
 for(int j=0;j<n;j++)for(int k=0;k<3;k++)px[3*j+k]=samples[j].pose.v[k];delete[] samples;
}
extern "C" int run_limit(int k){pf_t pf{};pf.min_samples=2000;pf.max_samples=100000;pf.pop_z=.99;pf.pop_err=.05;return pf_resample_limit(&pf,k);}
'''
    with tempfile.TemporaryDirectory(prefix='mapbuild9-parity-') as tmp:
        tmp=Path(tmp);source=tmp/'upstream.cpp';library=tmp/'upstream.so'
        source.write_text(prelude+'\n'+'\n'.join(parts)+'\n'+trailer)
        command=['g++','-std=c++17','-O2','-fPIC','-shared',str(source),'-o',str(library)]
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        lib=ctypes.CDLL(str(library));pointer=ctypes.POINTER(ctypes.c_double)
        lib.run_motion.argtypes=[ctypes.c_int,pointer,pointer,pointer,pointer];lib.run_limit.argtypes=[ctypes.c_int];lib.run_limit.restype=ctypes.c_int
        rng=np.random.default_rng(100);results=[];alpha=np.array([.0755723472,.0001127158,.0812268715,.0141937258],float)
        for delta in ([.3,.1,.15],[-.3,.1,-.4],[.001,.002,.3],[0,0,-.2],[.2,-.3,2.9]):
            initial=rng.uniform(-3,3,(200,3));normal=np.random.default_rng(42).normal(size=(200,3));native=initial.copy();d=np.array(delta,float)
            lib.run_motion(len(native),native.ctypes.data_as(pointer),d.ctypes.data_as(pointer),alpha.ctypes.data_as(pointer),normal.ctypes.data_as(pointer))
            translated=initial.copy();port.motion(translated,d,alpha,np.random.default_rng(42))
            diff=translated-native;diff[:,2]=port.wrap(diff[:,2]);maximum=float(np.max(abs(diff)))
            np.testing.assert_allclose(diff,0,atol=2e-14,rtol=0)
            results.append(dict(delta=delta,particles=200,max_absolute_SE2_difference=maximum))
        limits=[]
        for k in [0,1,2,3,5,10,50,100,500,1000,5000,10000]:
            native=lib.run_limit(k);translated=port.sample_limit(k);assert native==translated
            limits.append(dict(bins=k,native=native,python=translated))
        report=dict(status='PASS',scope='unchanged upstream motion/KLD numeric bodies in ABI shim; normal variates supplied, sensor adapter not native ROS qualified',motion_cases=results,kld_cases=limits,
            compiled_body_sha256=[hashlib.sha256(x.encode()).hexdigest() for x in parts],source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [upstream/'differential_motion_model.cpp',upstream/'pf.c']},
            generated_shim_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],reproduction=sys.argv,physics_steps=0)
        with a.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
        print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--source',type=Path);main(p.parse_args())
