"""Evaluation-only contact assignment; never imported by the policy worker."""
import math


def assigned_forces(contacts, ends, roles):
    """Assign contact to the nearest authored colored end; ties are ambiguous.

    This is the exact Voronoi partition of the two existing endpoint positions,
    not a fitted distance tolerance. Existing .5N/3s lift thresholds are reused.
    Input coordinates/forces belong exclusively to the evaluation ledger.
    """
    result={rid:[0.,0.] for rid in roles}
    for row in contacts:
        rid=row['robot'];role=roles[rid];other='blue' if role=='teal' else 'teal'
        point=row['position_xyz']
        if math.dist(point,ends[role])<math.dist(point,ends[other]):
            result[rid][row['finger']]+=row['normal_force_n']
    return result
