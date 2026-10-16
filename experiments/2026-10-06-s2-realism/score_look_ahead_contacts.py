"""Post-run only: count positive-force wall contact episodes at recorded20Hz."""

def summary(rows):
    out={}
    for cat in ('wheel','body','finger','cargo'):
        live=[any(c['category']==cat and c['normal_force_n']>0 for c in row['contacts']) for row in rows]
        starts=[i for i,on in enumerate(live) if on and (i==0 or not live[i-1])]
        forces=[sum(c['normal_force_n'] for c in row['contacts'] if c['category']==cat and c['normal_force_n']>0) for row in rows]
        out[cat]=dict(contact_samples=sum(live),sampled_contact_s=sum(live)*.05,continuous_episodes=len(starts),episode_start_times=[rows[i]['t'] for i in starts],
            positive_force_geom_pair_samples=sum(sum(c['category']==cat and c['normal_force_n']>0 for c in row['contacts']) for row in rows),peak_normal_force_sum_n=max(forces,default=0))
    return out
