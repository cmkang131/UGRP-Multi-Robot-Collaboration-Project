"""Two MasterPi bodies and one native-contact box. Only the handover driver imports this module."""
import math
import xml.etree.ElementTree as ET

from handover import layout
from scripts.solo_appearance_v1 import BLUE_RGBA, RED_RGBA


def numbers(values):
    return " ".join(f"{v:.10g}" for v in values)


def arena(xml, trial):
    """Keep the two complete robot trees and their box/finger pairs from the prepared executor XML."""
    if trial.get("schema") != "handover.trial.v1":
        raise ValueError("this scene builder requires an explicit handover.trial.v1 definition")
    root = ET.fromstring(xml)
    world = root.find("worldbody")
    keep = {"r1__robot", "r2__robot", layout.BODY, "floor"}
    for child in list(world):
        if child.get("name") not in keep and child.tag != "light":
            world.remove(child)
    for child in list(root.find("actuator")):
        if not child.get("joint", "").startswith(("r1__", "r2__")):
            root.find("actuator").remove(child)
    for section in ("equality", "keyframe"):
        node = root.find(section)
        if node is not None:
            root.remove(node)
    surviving = {n.get("name") for n in world.iter() if n.get("name")}
    for element in list(root.find("contact")):
        refs = [v for k, v in element.attrib.items() if k in ("geom1", "geom2", "body1", "body2")]
        if not all(ref in surviving for ref in refs):
            root.find("contact").remove(element)
        elif element.get("adhesion") == "0":
            # This source profile spells out zero adhesion. Stock MJCF contact pairs omit that attribute.
            del element.attrib["adhesion"]
    direction = trial["direction"]
    for rid, (x, y, angle) in trial["starts"].items():
        body = world.find(f"body[@name='{rid}__robot']")
        z = float(body.get("pos").split()[2])
        body.set("pos", numbers((x, y, z)))
        body.set("quat", numbers((math.cos(angle/2), 0, 0, math.sin(angle/2))))
    x, y, angle = trial["box_start"]
    cargo = world.find("body[@name='dispatch_box']")
    cargo.set("pos", numbers((x, y, 0.016)))
    cargo.set("quat", numbers((math.cos(angle/2), 0, 0, math.sin(angle/2))))
    cargo.find("geom[@name='dispatch_box_geom']").set("rgba", {"blue": BLUE_RGBA, "red": RED_RGBA}[trial["colour"]])
    floor = world.find("geom[@name='floor']")
    floor.set("pos", "0 0 0")
    floor.set("size", "4 4 0.1")

    def slab(name, u, v, hu, hv, h, colour, physical):
        x, y = layout.xy(direction, u, v)
        hx, hy = map(abs, layout.xy(direction, hu, hv))
        ET.SubElement(world, "geom", name=name, type="box", pos=numbers((x, y, h)),
                      size=numbers((hx, hy, h)), rgba=colour, contype="1" if physical else "0",
                      conaffinity="3" if physical else "0", mass="0")

    depth, span, half = layout.DEPTH, layout.HALF_SPAN, layout.WALL_HALF
    for side, name in ((-1, "a"), (1, "b")):
        colour = ".23 .28 .33 1"
        slab("end_"+name, side*depth, 0, half, span+half, .20, colour, True)
        slab("side_"+name, 0, side*span, depth, half, .20, colour, True)
        jamb = layout.OPENING/2
        slab("jamb_"+name, 0, side*(span+jamb)/2, half, (span-jamb)/2, .20, colour, True)
        # Thin matte floor tape, with a rectangular outline to show the nominal box axes.
        slab("tape_u_"+name, side*.037, 0, .002, .049, .00025, ".17 .17 .17 1", False)
        slab("tape_v_"+name, 0, side*.047, .037, .002, .00025, ".17 .17 .17 1", False)
    ET.SubElement(world, "camera", name="handover_overview", pos="0 0 6.4",
                  xyaxes="1 0 0 0 1 0", fovy="52")
    ET.SubElement(world, "light", name="gate_ceiling", pos="0 0 3.5", dir="0 0 -1",
                  diffuse=".55 .55 .55", castshadow="false")
    return ET.tostring(root, encoding="unicode")


def stock_xml(trial, out, hardware, drive):
    from harness import overhead_v1 as overhead, robot_tags_v1 as tags
    from sim import masterpi_camera_review_v3 as camera
    from sim import masterpi_drive_friction_v7 as wheels
    from sim.dispatch_contact_profile import contact_profile
    from sim.execution_contact_profile import apply_xml as native
    from sim.final_pair_highpose_nearclip import apply_xml as near_clip
    from sim.masterpi_robot_models import v3_robot_xml_transform
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.render_profile import apply_xml as lighting
    from sim.s2_servo_stiffness import transform_xml as stiffness
    from sim.warehouse_mission import CargoSpec, _cargo_body

    # The stock contact-profile builder needs the three template fingers and the beam.
    # Remove unused trees and every weld before compiling a model or constructing data.
    root = ET.fromstring(build_multi_robot_xml(hardware))
    cargo = _cargo_body(CargoSpec("small_box_01", "small_box", "small_box", layout.BODY,
                                  "dispatch_box_free", (.034, .040, .032), .030,
                                  (0, 0, .016), (0, 0, .016), .020, required_carriers=1))
    root.find("worldbody").append(cargo)
    xml = contact_profile(ET.tostring(root, encoding="unicode"), "local_contact_fine")
    xml = v3_robot_xml_transform(hardware, calibrated_keys=hardware)(xml)
    xml = arena(xml, trial)
    xml = camera.transform_xml(xml, profile_id=camera.PROFILE_ID)
    xml = near_clip(lighting(native(xml, "cargo_native_v1"), "floor_light_v1"))
    for rid in ("r1", "r2"):
        xml = stiffness(xml, servo_stiffness="real_v1", robot_id=rid)
    xml = wheels.transform_xml(xml, drive)
    textures = tags.write_textures(out / "cards", [11, 12, *overhead.card_numbers(("r1", "r2"))])
    xml = tags.add_signs(xml, textures, numbers=(11, 12))
    return overhead.add_to_scene(xml, ("r1", "r2"), textures)
