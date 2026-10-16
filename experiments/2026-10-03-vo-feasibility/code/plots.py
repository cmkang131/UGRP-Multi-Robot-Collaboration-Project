import math, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
import summarize as S
OUT=S.OUT
C={"gpk":"#2a78d6","gpo":"#eb6834","ipm":"#1baf7a","cmd":"#eda100","zero":"#9a9a92","gt":"#2b2b29"}
LAB={"gpk":"VO: KLT + floor plane","gpo":"VO: ORB + floor plane","ipm":"VO: bird's-eye + ECC","cmd":"own-command dead reckoning (gain fit on v88)","zero":"assume no motion"}
plt.rcParams.update({"font.size":9,"axes.spines.top":False,"axes.spines.right":False,"axes.edgecolor":"#8a8a84","axes.labelcolor":"#3a3a37","xtick.color":"#55554f","ytick.color":"#55554f"})
a=pd.read_csv(f"{OUT}/drift_summary.csv"); a=a[a.win_s==10].set_index("seq").loc[["v88_r1","v92_r1","v92_r2","m1_s101"]]
fig,ax=plt.subplots(figsize=(7.5,3.6),dpi=130)
ms=["gpk","gpo","ipm","cmd","zero"]; x=np.arange(len(a)); w=0.16
for k,m in enumerate(ms):
    v=a[f"{m}_pos_med_m"].values*100
    ax.bar(x+(k-2)*w,v,w*0.88,color=C[m],label=LAB[m])
ax.set_xticks(x,[f"{s}\n(GT path {p:.2f} m)" for s,p in zip(a.index,a.gt_path_med_m)])
ax.set_ylabel("position error after 10 s (cm, median)"); ax.grid(axis="y",color="#e4e4df",lw=0.6); ax.set_axisbelow(True)
ax.legend(frameon=False,fontsize=7.5,loc="upper left")
ax.set_title("10-second drift on moving windows (arm still); lower is better",loc="left",fontsize=10,color="#2b2b29")
fig.tight_layout(); fig.savefig(f"{OUT}/drift_10s.png"); plt.close(fig)
# example m1 trajectory
p=pd.read_csv(f"{OUT}/m1_s101_pairs.csv"); ip=pd.read_csv(f"{OUT}/m1_s101_ipm.csv")[["i","ipm_ok_raw","eig_min","ipm_dx","ipm_dy","ipm_dyaw"]]
p=p.merge(ip,on="i",how="left"); p["ipm_ok"]=((p.ipm_ok_raw==1)&(p.eig_min>50)).astype(int)
p[["cf","cl","ct"]]=S.cmd_features("m1_s101",p)
import json; g=json.load(open(f"{OUT}/cmd_gain_fit_v88.json")); F=p[["cf","cl","ct"]].values
p["cmd_dx"],p["cmd_dy"],p["cmd_dyaw"]=F@np.array(g["dx"]),F@np.array(g["dy"]),F@np.array(g["dyaw"])
d=pd.read_csv(f"{OUT}/drift_windows.csv"); d=d[(d.seq=="m1_s101")&(d.win_s==10)&(d.arm_frac==0)].sort_values("gt_path_m").iloc[-1]
st=int(np.argmin(abs(p.t-d.start_t))); sl=slice(st,st+50)
def path(dx,dy,dyaw,ok):
    x=y=th=0; out=[(0,0)]
    for a_,b_,c_,o in zip(dx,dy,dyaw,ok):
        if o: x+=math.cos(th)*a_-math.sin(th)*b_; y+=math.sin(th)*a_+math.cos(th)*b_; th+=c_
        out.append((x,y))
    return np.array(out)
q=p.iloc[sl]
fig,ax=plt.subplots(figsize=(5.2,3.8),dpi=130)
for m,dat in [("gt",path(q.gt_dx,q.gt_dy,q.gt_dyaw,[1]*len(q))),("gpk",path(q.gpk_dx,q.gpk_dy,q.gpk_dyaw,q.gpk_ok==1)),("ipm",path(q.ipm_dx,q.ipm_dy,q.ipm_dyaw,q.ipm_ok==1)),("cmd",path(q.cmd_dx,q.cmd_dy,q.cmd_dyaw,[1]*len(q)))]:
    ax.plot(dat[:,0],dat[:,1],color=C[m],lw=2,label="ground truth (scoring only)" if m=="gt" else LAB[m])
    ax.plot(dat[-1,0],dat[-1,1],"o",color=C[m],ms=6,mec="white",mew=1.5)
ax.set_aspect("equal","datalim"); ax.set_xlabel("x in start frame (m)"); ax.set_ylabel("y (m)"); ax.grid(color="#e4e4df",lw=0.6)
ax.legend(frameon=False,fontsize=7.5); ax.set_title(f"m1_s101 driving, t={d.start_t:.0f}-{d.start_t+10:.0f} s (10 s window)",loc="left",fontsize=10,color="#2b2b29")
fig.tight_layout(); fig.savefig(f"{OUT}/m1_example_10s.png"); plt.close(fig)
print("ok", d.start_t, d.gt_path_m)
