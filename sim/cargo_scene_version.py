"""Cargo scene versions (toggle; default = the catalogue masses, the old behaviour).

``crate_mass_030_v1`` (user decision 2026-10-14, docs/act_execution_decisions.md): the heavy crate
weighs 0.300 kg instead of 0.900 kg. Reason: with the ``real_v1`` servo model (elbow/wrist limit
0.1765 N m) one robot holds at most about 0.18 kg at the lift pose, so 0.9 kg (0.45 kg per robot,
elbow 0.39-0.43 N m) is out of reach for two robots; 0.30 kg is 0.15 kg per robot, the beam load
that already passes, and still needs two robots.

Only the mass attribute of the geoms of the named cargo body changes (inertia is recomputed by
MuJoCo). Geometry, friction, contact, colours and cameras are untouched. Results under different
versions are never pooled. Pure XML transform: no simulator import.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET

DEFAULT = 'catalogue_v1'
VERSIONS = {DEFAULT: {}, 'crate_mass_030_v1': {'heavy_crate': .300}}


def check(version):
    if version not in VERSIONS:
        raise ValueError(f'unknown cargo scene version: {version}')
    return version


def scale_body_mass(xml, item_id, mass_kg):
    """Scale every geom mass of body ``cargo_<item_id>`` so that the total is ``mass_kg``."""
    tree = ET.fromstring(xml)
    bodies = tree.findall(f".//body[@name='cargo_{item_id}']")
    if len(bodies) != 1:
        raise ValueError(f'one cargo body required: {item_id}')
    geoms = [g for g in bodies[0].iter('geom') if g.get('mass') is not None]
    total = sum(float(g.get('mass')) for g in geoms)
    if not geoms or total <= 0:
        raise ValueError(f'cargo geom masses required: {item_id}')
    k = float(mass_kg)/total
    for g in geoms:
        g.set('mass', repr(float(g.get('mass'))*k))
    return ET.tostring(tree, encoding='unicode'), {'catalogue_mass_kg': total, 'mass_kg': float(mass_kg), 'scale': k}


def apply_version(xml, version, cargo):
    """``cargo``: iterable of (item_id, kind). Returns (xml, record). The default returns ``xml`` unchanged."""
    masses = VERSIONS[check(version)]
    record = {'version': version, 'items': {}}
    if not masses:
        return xml, record
    for item_id, kind in cargo:
        if kind in masses:
            xml, info = scale_body_mass(xml, item_id, masses[kind])
            record['items'][item_id] = {'kind': kind, **info}
    return xml, record
