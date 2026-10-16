"""Explicit input-side stick/slip hysteresis candidate; no policy state feedback.

Static release follows the user's 32.5/100 observation bracket. Sliding loss
is Tc/T0=I0/Is=1/12 (Hiwonder analogue, unconfirmed installed motor). A signed
Schmitt relay holds the sliding branch until the input falls to Tc/T0 or
reverses without crossing the new-direction start threshold. This is a
command-state approximation of Karnopp's two regimes, not full Karnopp
force cancellation/velocity detection. It cannot detect an externally stalled
shaft from command history alone. See experiment README and official Relay.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from sim.masterpi_drive_friction import FrictionWorld
from sim.masterpi_drive_friction_v2 import DriveParameters as V2Parameters
from sim.masterpi_drive_friction_v6 import transform_xml as v6_xml
from sim.multi_masterpi_production import MultiMasterPiProductionV2
PROFILE='masterpi_drive_friction_v7'
# Opt-in, default-off speed option. The default 'mesh' leaves the XML byte-identical.
ROLLER_COLLISION_MODES=('mesh','sphere6_v1')
IDLE_ROBOT_CONTACT_MODES=('off','freeze_v1')
SPHERE6_ASSETS=Path(__file__).resolve().parent/'assets/masterpi_drive_friction_v7_sphere6'

@dataclass(frozen=True)
class DriveParameters(V2Parameters):
    start_fraction: float = .325
    no_load_current_a: float = .1
    stall_current_a: float = 1.2

    def __post_init__(self):
        super().__post_init__()
        if not 0 < self.kinetic_fraction < self.start_fraction < 1:
            raise ValueError('requires 0 < kinetic < start < 1')

    @property
    def kinetic_fraction(self):
        return self.no_load_current_a/self.stall_current_a

    @property
    def kinetic_torque_nm(self):
        return self.torque_cap_nm*self.kinetic_fraction

    @property
    def speed_loss_nm_s(self):
        # 150rpm is measured no-load, so do not charge the Coulomb loss twice.
        return (self.torque_cap_nm-self.kinetic_torque_nm)/self.omega

    def command_step(self, command, previous_direction):
        u=np.asarray(command,dtype=float);state=np.asarray(previous_direction,dtype=int)
        if u.shape!=state.shape or not np.isfinite(u).all() or np.any(np.abs(u)>1) or not np.isin(state,[-1,0,1]).all():
            raise ValueError('requires finite normalized command and matching signed relay state')
        sign=np.sign(u).astype(int);level=np.abs(u)
        same=(state!=0)&(sign==state)
        on=(level>self.start_fraction)|(same&(level>self.kinetic_fraction))
        new_state=np.where(on,sign,0)
        return np.where(on,u-sign*self.kinetic_fraction,0.),new_state

    def record(self):
        r=super().record()
        r.update(profile=PROFILE,qualification='INPUT_STICK_SLIP_CANDIDATE',
            actuator_model='native motor T0*(u-sign(u)*bk) on input-latched sliding branch; zero source torque on stick branch',
            zero_command='input relay resets; passive DC speed loss remains',
            state_scope='per-wheel command sign/history only; not measured motion or policy observation',
            reset_rule='world.reset clears all input relay states before normal scene reset',
            friction_model='input hysteresis replaces wheel joint dry loss; roller contact/bearing unchanged',
            start_source='user observation <=30 rest >=35 sustained; midpoint32.5 fixed before v6',
            kinetic_fraction=self.kinetic_fraction,kinetic_torque_nm=self.kinetic_torque_nm,
            kinetic_source='Hiwonder encoder TT I0=.1A Is=1.2A; Tc/T0=I0/Is conditional all no-load loss Coulomb',
            diagnostic_scope='v6 stall contact normal torque is external geometry/load resistance; not subtracted from motor I0/Is',
            speed_loss_nm_s=self.speed_loss_nm_s,
            implementation_source='MathWorks Relay on/off hysteresis; Karnopp stick/slip principle adapted to user-requested input state',
            unconfirmed=['installed TT and stall torque','PWM transfer','Coulomb versus viscous no-load split',
                         'load-dependent start threshold','external stall/re-stick','brake versus coast'])
        r.pop('sha256');r['sha256']=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
        return r


def sphere6_source():
    """TIAGo public USD sphere layout (provenance in assets/.../source.json)."""
    return json.loads((SPHERE6_ASSETS/'source.json').read_text())


def sphere6_layout():
    """Six (axis_x_m, radius_m) pairs for one MasterPi roller, TIAGo values x 65/205."""
    from sim.masterpi_geometry_v3 import OFFICIAL_WHEEL_DIAMETER_M
    from sim.masterpi_drive_friction_v2 import SOURCE as FUJI
    src=sphere6_source()
    # Same scale the v2 port applies to the FUJI barrel mesh.
    scale=OFFICIAL_WHEEL_DIAMETER_M/(2*FUJI['source_radius_m'])
    return [(s['axis_x_m']*scale,s['radius_m']*scale) for s in src['spheres_tiago_m']]


def apply_sphere6(root):
    """Replace each FUJI mesh roller collider by six spheres on the roller axis.

    Only the collision geom changes: body, hinge, inertia, damping, material,
    contype/conaffinity/condim/priority and the self-collision excludes stay.
    """
    layout=sphere6_layout()
    targets=[(parent,geom) for parent in root.iter() for geom in parent.findall('geom')
             if geom.get('type')=='mesh' and geom.get('mesh')=='fuji_roller_v2']
    if not targets or len(targets)%36:
        raise ValueError('sphere6_v1 requires the v2 FUJI mesh rollers (36 per robot)')
    for parent,geom in targets:
        index=list(parent).index(geom)
        parent.remove(geom)
        for k,(x,r) in enumerate(layout):
            attrs={key:value for key,value in geom.attrib.items() if key not in ('name','type','mesh')}
            attrs.update(name=f"{geom.get('name')}_s{k}",type='sphere',pos=f'{x!r} 0 0',size=repr(r))
            parent.insert(index+k,ET.Element('geom',attrs))
    asset=root.find('asset')
    if asset is not None:
        for mesh in asset.findall("mesh[@name='fuji_roller_v2']"):
            asset.remove(mesh)  # no geom references it any more
    custom=root.find('custom')
    ET.SubElement(custom,'text',name='roller_collision',data='sphere6_v1')
    return len(targets)


def apply_freeze(root):
    """MuJoCo native sleeping for idle robots (opt-in, `idle_robot_contacts=freeze_v1`).

    Official sleeping islands skip all contacts of a resting island, including its
    roller/floor contacts. Robot trees are allowed to sleep (actuated trees are not
    by default) and every other free body is `never`, so a robot holding cargo, or
    touching a free object, is never frozen. Waking by command is done in the world
    step (MuJoCo does not wake on actuator changes). Hidden while asleep: contacts
    with static geometry and inside the island, so contact-based evaluation readouts
    of a frozen robot are empty.
    """
    option=root.find('option')
    flag=option.find('flag')
    if flag is None:flag=ET.SubElement(option,'flag')
    flag.set('sleep','enable')
    robots=0
    for body in root.findall('worldbody/body'):
        if body.find('freejoint') is None and not any(j.get('type')=='free' for j in body.findall('joint')):
            continue
        if body.get('name','').endswith('__robot'):
            body.set('sleep','allowed');robots+=1
        else:
            body.set('sleep','never')
    if not robots:raise ValueError('freeze_v1 requires namespaced robots')
    ET.SubElement(root.find('custom'),'text',name='idle_robot_contacts',data='freeze_v1')
    return robots


def transform_xml(xml,params,roller_collision='mesh',idle_robot_contacts='off'):
    if roller_collision not in ROLLER_COLLISION_MODES:
        raise ValueError(f'roller_collision must be one of {ROLLER_COLLISION_MODES}')
    if idle_robot_contacts not in IDLE_ROBOT_CONTACT_MODES:
        raise ValueError(f'idle_robot_contacts must be one of {IDLE_ROBOT_CONTACT_MODES}')
    root=ET.fromstring(v6_xml(xml,params))
    root.find("custom/text[@name='drive_profile']").set('data',PROFILE)
    if roller_collision=='sphere6_v1':
        apply_sphere6(root)
    if idle_robot_contacts=='freeze_v1':
        apply_freeze(root)
    return ET.tostring(root,encoding='unicode')


def option_record(roller_collision='mesh',idle_robot_contacts='off'):
    """Extra audit fields; empty for the defaults so the default record is unchanged."""
    r={}
    if roller_collision!='mesh':
        src=sphere6_source()
        r.update(roller_collision=roller_collision,
           roller_collision_spheres_m=sphere6_layout(),
           roller_collision_source={k:src['values_source'][k] for k in ('repository','commit','wheel_file','roller_file')},
           roller_collision_paper=src['method_source']['paper']+' '+src['method_source']['section'],
           roller_collision_unconfirmed=src['unconfirmed'])
        r['roller_collision_sha256']=hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()
    if idle_robot_contacts!='off':
        f=dict(idle_robot_contacts=idle_robot_contacts,
           idle_robot_contacts_method='MuJoCo native sleeping islands (flag sleep); robot trees allowed, other free bodies never; manual wake on command/ctrl change',
           idle_robot_contacts_source='https://mujoco.readthedocs.io/en/3.12.0/programming/simulation.html#sleeping-islands',
           idle_robot_contacts_caveat='contacts of a sleeping robot with static geometry and inside its island are skipped, so contact-based readouts are empty; velocities below sleep_tolerance are zeroed when it falls asleep')
        r.update(f)
        r['idle_robot_contacts_sha256']=hashlib.sha256(json.dumps(f,sort_keys=True).encode()).hexdigest()
    return r


class HysteresisWorld(FrictionWorld):
    idle_robot_contacts='off'

    def reset(self,*args,**kwargs):
        self.drive_input_state={}
        self._freeze_state={}
        return super().reset(*args,**kwargs)

    def _freeze_wake(self,rid,c,effective):
        """Wake a sleeping robot when its commands change (MuJoCo does not wake on ctrl)."""
        m,d=self.model,self.data
        state=self._freeze_state.get(rid)
        if state is None:
            tree=int(m.body_treeid[c.robot_bid])
            joint=m.actuator_trnid[:,0]
            ids=np.flatnonzero((m.actuator_trntype==mujoco.mjtTrn.mjTRN_JOINT)&(m.body_treeid[m.jnt_bodyid[joint]]==tree))
            state=self._freeze_state[rid]={'tree':tree,'ids':ids,'prev':None}
        ctrl=d.ctrl[state['ids']]
        changed=state['prev'] is None or not np.array_equal(ctrl,state['prev'])
        state['prev']=ctrl.copy()
        if (changed or np.any(effective)) and d.tree_asleep[state['tree']]>=0:
            d.qfrc_applied[c.base_dadr]=-0.0  # bytewise non-zero: official manual wake
            return c.base_dadr
        return None

    def _physics_step_for(self,active,commands=None):
        if any(getattr(self,k,None) is not None for k in ('_fast_drive_kernel','_mixed_engine','_warehouse_crew')):
            raise RuntimeError('legacy drive incompatible with '+PROFILE)
        with self.physics_lock:
            if commands is not None: active.set_motor_commands(commands)
            if not hasattr(self,'drive_input_state'):self.drive_input_state={}
            freeze=self.idle_robot_contacts=='freeze_v1'
            woken=[]
            if freeze and not hasattr(self,'_freeze_state'):self._freeze_state={}
            for rid,c in self.controllers.items():
                previous=self.drive_input_state.get(rid)
                if previous is None:previous=np.zeros(4,dtype=int)
                effective,state=self.drive_parameters.command_step(c.motor_command,previous)
                self.drive_input_state[rid]=state
                c.motor_state[:]=c.motor_command
                self.data.ctrl[c.wheel_act]=self.drive_parameters.torque_cap_nm*effective
                if freeze:
                    dof=self._freeze_wake(rid,c,effective)
                    if dof is not None:woken.append(dof)
            mujoco.mj_step(self.model,self.data)
            for dof in woken:self.data.qfrc_applied[dof]=0.0
            for c in self.controllers.values():c._presentation_dirty=True


def build_world(scene, *, drive_profile, params=None, roller_collision='mesh', idle_robot_contacts='off', exact_speedups=None, **kwargs):
    if drive_profile != PROFILE:
        raise ValueError('explicit '+PROFILE+' required')
    if roller_collision not in ROLLER_COLLISION_MODES:
        raise ValueError(f'roller_collision must be one of {ROLLER_COLLISION_MODES}')
    if idle_robot_contacts not in IDLE_ROBOT_CONTACT_MODES:
        raise ValueError(f'idle_robot_contacts must be one of {IDLE_ROBOT_CONTACT_MODES}')
    from sim.session_scenes import Scene
    from sim.masterpi_model_v3 import v3_hardware
    from sim.masterpi_robot_models import V3_DRAWING_HARDWARE_KEYS
    from sim.zone_cargo_contact import apply
    if not isinstance(scene, Scene) or not hasattr(scene, 'robot_transform'):
        raise ValueError('requires standard v3 Scene adapter')
    world = HysteresisWorld.__new__(HysteresisWorld)
    world.drive_parameters = params or DriveParameters()
    from sim.v7_exact_speedups import configure
    configure(world, exact_speedups)

    def transform(xml):
        xml = apply(scene.transform(xml), 'cargo_noslip_v1')
        xml = scene.robot_transform(xml, hardware=world.physical_params,
                                    calibrated_keys=world.calibration_parameters)
        return transform_xml(xml, world.drive_parameters, roller_collision, idle_robot_contacts)

    MultiMasterPiProductionV2.__init__(world, xml_transform=transform, **kwargs)
    hw = dict(world.physical_params)
    for key in V3_DRAWING_HARDWARE_KEYS:
        if key not in world.calibration_parameters:
            hw.pop(key, None)
    world.physical_params.update(v3_hardware(hw))
    world.calibration_status = 'INPUT_STICK_SLIP_CANDIDATE'
    world.roller_collision = roller_collision
    world.idle_robot_contacts = idle_robot_contacts
    world.drive_profile_record = world.drive_parameters.record()
    world.drive_profile_record.update(option_record(roller_collision, idle_robot_contacts))
    world.drive_profile_record['xml_sha256'] = hashlib.sha256(world.scene_xml.encode()).hexdigest()
    return world
