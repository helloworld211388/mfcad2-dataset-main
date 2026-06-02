import json
import math
from pathlib import Path

from OCC.Core.AIS import AIS_ColoredShape
from OCC.Core.BRep import BRep_Tool_Surface
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core.BRepGProp import brepgprop_SurfaceProperties
from OCC.Core.BRepTools import breptools_UVBounds
from OCC.Core.GProp import GProp_GProps
from OCC.Core.GeomLProp import GeomLProp_SLProps
from OCC.Core.Quantity import Quantity_Color, Quantity_NOC_WHITE, Quantity_TOC_RGB
from OCC.Core.TopAbs import TopAbs_REVERSED

import Utils.occ_utils as occ_utils
import Utils.parameters as param


FEATURE_NAMES = [
    "chamfer",
    "through_hole",
    "triangular_passage",
    "rectangular_passage",
    "6sides_passage",
    "triangular_through_slot",
    "rectangular_through_slot",
    "circular_through_slot",
    "rectangular_through_step",
    "2sides_through_step",
    "slanted_through_step",
    "Oring",
    "blind_hole",
    "triangular_pocket",
    "rectangular_pocket",
    "6sides_pocket",
    "circular_end_pocket",
    "rectangular_blind_slot",
    "v_circular_end_blind_slot",
    "h_circular_end_blind_slot",
    "triangular_blind_step",
    "circular_blind_step",
    "rectangular_blind_step",
    "round",
    "counterbore",
    "countersunk_hole",
    "variable_round",
]

BASE_COLOR = Quantity_Color(0.83, 0.83, 0.83, Quantity_TOC_RGB)
HIGHLIGHT_COLOR = Quantity_Color(0.93, 0.35, 0.14, Quantity_TOC_RGB)
STOCK_COLOR = Quantity_Color(0.62, 0.38, 0.02, Quantity_TOC_RGB)
FEATURE_COLOR = Quantity_Color(0.0, 0.78, 0.0, Quantity_TOC_RGB)
BOTTOM_COLOR = Quantity_Color(0.86, 0.0, 0.0, Quantity_TOC_RGB)


def pretty_name(feature_name):
    if not feature_name:
        return feature_name
    if feature_name[0].isalpha():
        return feature_name[0].upper() + feature_name[1:]
    return feature_name


def infer_feature_name_from_stem(stem):
    for feature_name in FEATURE_NAMES:
        if pretty_name(feature_name) == stem:
            return feature_name
    lowered = stem[0].lower() + stem[1:] if stem else stem
    if lowered in FEATURE_NAMES:
        return lowered
    return None


def infer_feature_name_from_labels(id_map):
    labels = sorted(set(id_map.values()))
    for label in labels:
        if 0 <= label < len(param.feat_names):
            feature_name = param.feat_names[label]
            if feature_name in FEATURE_NAMES:
                return feature_name
    return None


def resolve_label_json_path(step_path):
    step_path = Path(step_path).resolve()
    same_dir = step_path.with_suffix(".json")
    if same_dir.exists():
        return same_dir

    if step_path.parent.name == "steps" and step_path.parent.parent.name == "paper_feature_gallery":
        gallery_label = step_path.parent.parent / "labels" / f"{step_path.stem}.json"
        if gallery_label.exists():
            return gallery_label

    raise FileNotFoundError(f"Missing label JSON for STEP: {step_path}")


def load_and_validate_label_json(label_path, expected_face_count):
    label_path = Path(label_path)
    with label_path.open("r", encoding="utf8") as fp:
        labels = json.load(fp)

    for key in ("cls", "seg", "bottom"):
        if key not in labels:
            raise ValueError(f"Label JSON missing '{key}': {label_path}")

    bottom = labels["bottom"]
    if not isinstance(bottom, dict):
        raise ValueError(f"Label JSON bottom must be an object: {label_path}")

    if len(bottom) != expected_face_count:
        raise ValueError(
            f"Label JSON face count mismatch: bottom={len(bottom)} faces={expected_face_count}"
        )

    return labels


def classify_tricolor_face(face_label, target_label, bottom_value):
    if face_label != target_label:
        return "stock"
    return "bottom" if int(bottom_value) == 1 else "feature"


def face_index_map(shape):
    return {face: idx for idx, face in enumerate(occ_utils.list_face(shape))}


def load_view_presets(path):
    preset_path = Path(path)
    if not preset_path.exists():
        return {}
    with preset_path.open("r", encoding="utf8") as fp:
        return json.load(fp)


def save_view_presets(path, presets):
    preset_path = Path(path)
    with preset_path.open("w", encoding="utf8") as fp:
        json.dump(presets, fp, indent=2, ensure_ascii=False, sort_keys=True)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def _length(v):
    return math.sqrt(_dot(v, v))


def _normalize(v, fallback=(0.0, 0.0, 1.0)):
    norm = _length(v)
    if norm < 1e-9:
        return fallback
    return (v[0] / norm, v[1] / norm, v[2] / norm)


def _orthogonal_component(v, direction):
    return _sub(v, _scale(direction, _dot(v, direction)))


def _blend(a, b, ratio_b):
    ratio_a = 1.0 - ratio_b
    return (
        a[0] * ratio_a + b[0] * ratio_b,
        a[1] * ratio_a + b[1] * ratio_b,
        a[2] * ratio_a + b[2] * ratio_b,
    )


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _choose_up(camera_dir):
    candidates = [(0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)]
    for candidate in candidates:
        if abs(_dot(candidate, camera_dir)) < 0.92:
            up = _orthogonal_component(candidate, camera_dir)
            return _normalize(up, (0.0, 0.0, 1.0))
    sideways = _cross(camera_dir, (1.0, 0.0, 0.0))
    return _normalize(_cross(sideways, camera_dir), (0.0, 0.0, 1.0))


def face_area(face):
    props = GProp_GProps()
    brepgprop_SurfaceProperties(face, props)
    return props.Mass()


def face_center_and_normal(face):
    u_min, u_max, v_min, v_max = breptools_UVBounds(face)
    u_mid = (u_min + u_max) / 2.0
    v_mid = (v_min + v_max) / 2.0
    point = BRepAdaptor_Surface(face).Value(u_mid, v_mid)
    surface = BRep_Tool_Surface(face)
    props = GeomLProp_SLProps(surface, u_mid, v_mid, 1, 0.01)
    normal = props.Normal()
    if face.Orientation() == TopAbs_REVERSED:
        normal.Reverse()
    return tuple(point.Coord()), tuple(normal.Coord())


def bbox_center_and_diag(shape):
    bbox = occ_utils.get_boundingbox(shape)
    center = (
        (bbox[0] + bbox[3]) / 2.0,
        (bbox[1] + bbox[4]) / 2.0,
        (bbox[2] + bbox[5]) / 2.0,
    )
    diag = math.sqrt((bbox[6] ** 2) + (bbox[7] ** 2) + (bbox[8] ** 2))
    return center, diag


def get_highlight_faces(shape, id_map, feature_name):
    target_label = param.feat_names.index(feature_name)
    return [face for face in occ_utils.list_face(shape) if id_map.get(face) == target_label]


def build_colored_ais(shape, id_map, feature_name, base_color=None, highlight_color=None):
    ais = AIS_ColoredShape(shape)
    target_label = param.feat_names.index(feature_name)
    base = base_color or BASE_COLOR
    highlight = highlight_color or HIGHLIGHT_COLOR

    for face in occ_utils.list_face(shape):
        ais.SetCustomColor(face, highlight if id_map.get(face) == target_label else base)

    return ais


def build_tricolor_ais(shape, id_map, feature_name, bottom_label):
    ais = AIS_ColoredShape(shape)
    target_label = param.feat_names.index(feature_name)
    indices = face_index_map(shape)
    role_colors = {
        "stock": STOCK_COLOR,
        "feature": FEATURE_COLOR,
        "bottom": BOTTOM_COLOR,
    }

    for face in occ_utils.list_face(shape):
        face_idx = str(indices[face])
        if face_idx not in bottom_label:
            raise ValueError(f"Missing bottom label for face index {face_idx}")
        role = classify_tricolor_face(id_map.get(face), target_label, bottom_label[face_idx])
        ais.SetCustomColor(face, role_colors[role])

    return ais


def compute_auto_camera(shape, id_map, feature_name):
    highlight_faces = get_highlight_faces(shape, id_map, feature_name)
    if not highlight_faces:
        return None

    shape_center, diag = bbox_center_and_diag(shape)

    face_infos = []
    for face in highlight_faces:
        center, normal = face_center_and_normal(face)
        area = face_area(face)
        face_infos.append(
            {
                "face": face,
                "type": occ_utils.type_face(face),
                "center": center,
                "normal": _normalize(normal),
                "area": area,
            }
        )

    total_area = sum(info["area"] for info in face_infos) or float(len(face_infos))
    highlight_center = (0.0, 0.0, 0.0)
    for info in face_infos:
        weight = info["area"] / total_area if total_area > 0 else 1.0 / len(face_infos)
        highlight_center = _add(highlight_center, _scale(info["center"], weight))

    plane_infos = [info for info in face_infos if info["type"] == "plane"]

    if plane_infos:
        dominant = max(plane_infos, key=lambda info: info["area"])
        axis = max(range(3), key=lambda idx: abs(dominant["normal"][idx]))
        normal_sign = 1.0 if dominant["normal"][axis] >= 0.0 else -1.0
        feature_sign = 1.0 if dominant["center"][axis] >= shape_center[axis] else -1.0
        camera_dir = dominant["normal"] if normal_sign == feature_sign else _scale(dominant["normal"], -1.0)
        drift = _orthogonal_component(_sub(highlight_center, shape_center), camera_dir)
        if _length(drift) > 1e-9:
            camera_dir = _normalize(_add(_scale(camera_dir, 1.0), _scale(_normalize(drift), 0.45)))
        at = _blend(shape_center, highlight_center, 0.65)
    else:
        dominant = max(face_infos, key=lambda info: info["area"])
        camera_dir = dominant["normal"]
        vertical_hint = 0.25 if highlight_center[2] >= shape_center[2] else -0.25
        camera_dir = _normalize((camera_dir[0], camera_dir[1], camera_dir[2] + vertical_hint))
        at = _blend(shape_center, highlight_center, 0.72)

    up = _choose_up(camera_dir)
    distance = max(diag * 2.4, 1.0)
    eye = _add(at, _scale(camera_dir, distance))

    return {
        "eye": [eye[0], eye[1], eye[2]],
        "at": [at[0], at[1], at[2]],
        "up": [up[0], up[1], up[2]],
    }


def capture_camera(display):
    return {
        "eye": list(display.View.Eye()),
        "at": list(display.View.At()),
        "up": list(display.View.Up()),
        "scale": display.View.Scale(),
    }


def apply_camera(display, camera, fit_after=False):
    display.View.SetAt(*camera["at"])
    display.View.SetEye(*camera["eye"])
    display.View.SetUp(*camera["up"])
    if fit_after:
        display.FitAll()
        display.View.ZFitAll()
    elif "scale" in camera:
        display.View.SetScale(float(camera["scale"]))
    display.View.Redraw()


def set_standard_display_style(display):
    display.View.SetBackgroundColor(Quantity_Color(Quantity_NOC_WHITE))
    display.default_drawer.SetFaceBoundaryDraw(True)
    display.SetModeShaded()
