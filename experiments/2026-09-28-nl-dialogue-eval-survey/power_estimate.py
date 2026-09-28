# Analytic power ESTIMATES (normal approx + Guenther correction). Not a substitute for pilot-based simulation.
from statistics import NormalDist
from math import asin, sqrt, ceil
N=NormalDist()
def z(p): return N.inv_cdf(p)
def n_paired(dz, alpha=0.05, power=0.8):
    za=z(1-alpha/2); zb=z(power)
    return ceil(((za+zb)/dz)**2 + za**2/2)
def n_twogroup_d(d, alpha=0.05, power=0.8):
    za=z(1-alpha/2); zb=z(power)
    return ceil(2*((za+zb)/d)**2 + za**2/4)
def h(p1,p2): return abs(2*asin(sqrt(p1))-2*asin(sqrt(p2)))
def n_prop(p1,p2,alpha=0.05,power=0.8):
    za=z(1-alpha/2); zb=z(power)
    return ceil(((za+zb)/h(p1,p2))**2)
def mde_paired(n, alpha=0.05, power=0.8):
    # smallest dz detectable (normal approx with correction solved numerically)
    for k in range(1,400):
        dz=k/100
        if n_paired(dz,alpha,power)<=n: return dz
def d_from_r(r): return 2*r/sqrt(1-r*r)
# Guo et al. 2024: mean±(reported ±) time steps, n=20 seeds/cond (± assumed SD)
def d_pooled(m1,s1,m2,s2): return abs(m1-m2)/sqrt((s1*s1+s2*s2)/2)
d_gpt35=d_pooled(102.95,21.88,92.90,14.70); d_gpt4=d_pooled(57.75,13.09,54.70,8.92)
print("Guo d GPT-3.5 %.3f  GPT-4 %.3f"%(d_gpt35,d_gpt4))
print("Guo t->d check 1.71*sqrt(2/20)=%.3f"%(1.71*sqrt(2/20)))
for name,r in [("Marlow overall",0.31),("Marlow frequency",0.19),("Marlow quality",0.36),("Marlow info elaboration",0.52)]:
    print(name,"r=%.2f -> d=%.3f"%(r,d_from_r(r)))
print("h HMAS2 vs DMAS BoxNet1 .825 v .25 = %.3f"%h(.825,.25))
print("h RoCo dialog vs central PackGrocery .44 v .82 = %.3f"%h(.44,.82))
print("h RoCo dialog vs central MoveRope .65 v .50 = %.3f"%h(.65,.50))
print()
print("Paired n (pairs) for alpha .05 two-sided / alpha .0167 (Holm-3 worst case), power .8")
for label,d in [("Guo GPT-4 d",d_gpt4),("Guo GPT-3.5 d",d_gpt35),("Marlow freq d",d_from_r(.19)),("Marlow overall d",d_from_r(.31)),("d=0.8",0.8),("d=1.0",1.0)]:
    for rho in (0.0,0.5,0.7):
        dz=d/sqrt(2*(1-rho))
        print(f"  {label:16s} d={d:.2f} rho={rho:.1f} dz={dz:.2f}  n={n_paired(dz)}  n(Holm3)={n_paired(dz,alpha=0.05/3)}")
print()
print("Min detectable dz at power .8:")
for n in (18,24,36,54,72):
    print(f"  pairs={n}: alpha.05 dz={mde_paired(n)}  alpha.0167 dz={mde_paired(n,alpha=0.05/3)}")
print()
print("Unpaired success-rate n per arm (arcsine), alpha .05 / .0167, power .8")
for p1,p2 in [(.825,.25),(.8,.5),(.8,.6),(.65,.5),(.9,.7)]:
    print(f"  {p1} vs {p2}: h={h(p1,p2):.2f} n={n_prop(p1,p2)} n(Holm3)={n_prop(p1,p2,alpha=.05/3)}")
