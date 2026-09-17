import argparse
import json
import math
import multiprocessing as mp
import random
import shutil
import subprocess
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPConstruct import stepconstruct_FindEntity
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCC.Core.TCollection import TCollection_HAsciiString
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Display.SimpleGui import init_display
from PIL import Image, ImageDraw, ImageFont

import feature_creation
import Utils.occ_utils as occ_utils
import Utils.parameters as param
from Features.machining_features import MachiningFeature
from Features.variable_round import VariableRound
from Utils.shape import shape_with_fid_from_step
from feature_viewer_common import (
    FEATURE_NAMES,
    apply_camera,
    build_tricolor_ais,
    compute_auto_camera,
    compute_paper_camera,
    load_and_validate_label_json,
    load_view_presets,
    pretty_name,
    set_standard_display_style,
    temporary_parameter_overrides,
)


PAPER_PARAMETER_OVERRIDES = {
    "stock_min_x": 24.0,
    "stock_max_x": 24.0,
    "stock_min_y": 24.0,
    "stock_max_y": 24.0,
    "stock_min_z": 18.0,
    "stock_max_z": 18.0,
    "min_len": 4.0,
    "clearance": 1.0,
    "inner_bounds_clearance": 2,
    "chamfer_depth_min": 1.2,
    "chamfer_depth_max": 2.4,
    "round_radius_min": 0.8,
    "round_radius_max": 2.4,
    "variable_round_radius_min": 0.6,
    "variable_round_radius_max": 2.2,
}

PAPER_SHIFTER_MIN = 0.45
PAPER_SHIFTER_MAX = 0.85
PAPER_LARGE_OPENING_FEATURES = {
    "6sides_pocket",
    "6sides_passage",
    "rectangular_passage",
    "triangular_passage",
    "triangular_pocket",
    "blind_hole",
    "h_circular_end_blind_slot",
}
PAPER_TOP_OPENING_FEATURES = {
    "6sides_pocket",
    "6sides_passage",
    "rectangular_passage",
    "triangular_passage",
    "triangular_pocket",
}
PAPER_LARGEST_BOUND_FEATURES = PAPER_TOP_OPENING_FEATURES | {
    "blind_hole",
    "h_circular_end_blind_slot",
}
PAPER_LARGE_SHIFTER_MIN = 0.72
PAPER_LARGE_SHIFTER_MAX = 0.95
PAPER_SHALLOW_BLIND_FEATURES = {
    "6sides_pocket",
    "triangular_pocket",
    "rectangular_pocket",
    "circular_end_pocket",
}
PAPER_BLIND_DEPTH_MIN_RATIO = 0.28
PAPER_BLIND_DEPTH_MAX_RATIO = 0.45


def validate_features(feature_names):
    invalid = [name for name in feature_names if name not in param.feat_names]
    if invalid:
        raise ValueError(f"Unknown feature names: {invalid}")


def paper_shifter_range_for_feature(feature_name):
    if feature_name in PAPER_LARGE_OPENING_FEATURES:
        return PAPER_LARGE_SHIFTER_MIN, PAPER_LARGE_SHIFTER_MAX
    return PAPER_SHIFTER_MIN, PAPER_SHIFTER_MAX


def paper_prefers_top_opening(feature_name):
    return feature_name in PAPER_TOP_OPENING_FEATURES


def paper_bound_area(bound):
    if len(bound) < 4:
        return 0.0

    width = math.sqrt(sum((float(bound[2][i]) - float(bound[1][i])) ** 2 for i in range(3)))
    height = math.sqrt(sum((float(bound[0][i]) - float(bound[1][i])) ** 2 for i in range(3)))
    return width * height


def paper_bounds_for_feature(feature_name, bounds):
    if not paper_prefers_top_opening(feature_name):
        if feature_name in PAPER_LARGEST_BOUND_FEATURES and bounds:
            return [max(bounds, key=paper_bound_area)]
        return bounds

    top_bounds = [bound for bound in bounds if len(bound) > 4 and bound[4][2] < -0.9]
    if not top_bounds:
        return bounds

    return [max(top_bounds, key=paper_bound_area)]


def paper_variable_round_radius_pair(min_radius, max_radius):
    if max_radius <= min_radius:
        return min_radius, max_radius

    span = max_radius - min_radius
    return min_radius + span * 0.08, min_radius + span * 0.94



def paper_blind_depth_range_for_feature(feature_name, min_depth, max_depth):
    if feature_name not in PAPER_SHALLOW_BLIND_FEATURES or max_depth <= min_depth:
        return min_depth, max_depth

    capped_min = max(min_depth, max_depth * PAPER_BLIND_DEPTH_MIN_RATIO)
    capped_max = min(max_depth, max(capped_min, max_depth * PAPER_BLIND_DEPTH_MAX_RATIO))
    return capped_min, capped_max


@contextmanager
def paper_shifter_range(min_scale=PAPER_SHIFTER_MIN, max_scale=PAPER_SHIFTER_MAX):
    original_shifter = MachiningFeature._shifter

    def display_shifter(self, bounds_max):
        original_uniform = random.uniform

        def patched_uniform(a, b):
            if a == 0.1 and b == 1.0:
                feature_min, feature_max = paper_shifter_range_for_feature(self.feat_type)
                return original_uniform(feature_min, feature_max)
            return original_uniform(a, b)

        random.uniform = patched_uniform
        try:
            return original_shifter(self, bounds_max)
        finally:
            random.uniform = original_uniform

    MachiningFeature._shifter = display_shifter
    try:
        yield
    finally:
        MachiningFeature._shifter = original_shifter


@contextmanager
def paper_bound_orientation():
    original_get_bounds = MachiningFeature._get_bounds

    def display_get_bounds(self):
        original_get_bounds(self)
        self.bounds = paper_bounds_for_feature(self.feat_type, self.bounds)

    MachiningFeature._get_bounds = display_get_bounds
    try:
        yield
    finally:
        MachiningFeature._get_bounds = original_get_bounds


@contextmanager
def paper_blind_depth_range():
    original_depth_blind = MachiningFeature._depth_blind

    def display_depth_blind(self, bound, triangles):
        original_uniform = random.uniform

        def patched_uniform(a, b):
            if a == self.min_len:
                depth_min, depth_max = paper_blind_depth_range_for_feature(self.feat_type, a, b)
                return original_uniform(depth_min, depth_max)
            return original_uniform(a, b)

        random.uniform = patched_uniform
        try:
            return original_depth_blind(self, bound, triangles)
        finally:
            random.uniform = original_uniform

    MachiningFeature._depth_blind = display_depth_blind
    try:
        yield
    finally:
        MachiningFeature._depth_blind = original_depth_blind


@contextmanager
def paper_variable_round_contrast():
    original_add_feature = VariableRound.add_feature

    def display_add_feature(self):
        original_uniform = random.uniform
        radius_queue = []

        def patched_uniform(a, b):
            if b > a:
                if not radius_queue:
                    radius_queue.extend(paper_variable_round_radius_pair(a, b))
                return radius_queue.pop(0)
            return original_uniform(a, b)

        random.uniform = patched_uniform
        try:
            return original_add_feature(self)
        finally:
            random.uniform = original_uniform

    VariableRound.add_feature = display_add_feature
    try:
        yield
    finally:
        VariableRound.add_feature = original_add_feature


def save_step_with_face_labels(step_path, shape, seg_map):
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    finderp = writer.WS().TransferWriter().FinderProcess()
    faces = occ_utils.list_face(shape)
    loc = TopLoc_Location()
    for face in faces:
        item = stepconstruct_FindEntity(finderp, face, loc)
        if item is not None:
            item.SetName(TCollection_HAsciiString(str(seg_map[face])))
    status = writer.Write(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed: {step_path}")


def save_label_json(label_path, shape, labels):
    seg_map, inst_label, bottom_map = labels
    faces = occ_utils.list_face(shape)
    cls_label = feature_creation.get_cls_label(faces, seg_map)
    seg_label = feature_creation.get_seg_label(faces, inst_label)
    bottom_label = feature_creation.get_bottom_label(faces, bottom_map)
    if len(cls_label) != len(faces) or len(bottom_label) != len(faces):
        raise RuntimeError(f"Label count mismatch for {label_path.stem}")

    data = {
        "cls": cls_label,
        "seg": seg_label,
        "bottom": bottom_label,
    }
    with label_path.open("w", encoding="utf8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


def export_step_preview(step_path, image_path, feature_name, label_path, presets):
    shape, id_map = shape_with_fid_from_step(str(step_path))
    labels = load_and_validate_label_json(label_path, len(occ_utils.list_face(shape)))

    display, _, _, _ = init_display()
    display.EraseAll()
    display.Context.RemoveAll(False)
    set_standard_display_style(display)

    ais = build_tricolor_ais(shape, id_map, feature_name, labels["bottom"])
    display.Context.Display(ais, True)

    preset = presets.get(step_path.stem)
    if preset:
        apply_camera(display, preset, fit_after=False)
    else:
        camera = compute_paper_camera(shape, id_map, feature_name) or compute_auto_camera(shape, id_map, feature_name)
        if camera:
            apply_camera(display, camera, fit_after=True)
        else:
            display.View_Iso()
            display.FitAll()
            display.View.ZFitAll()
            display.View.Redraw()

    display.ExportToImage(str(image_path))


def generate_feature_once(feature_name, output_dir, presets, seed):
    random.seed(seed)
    feature_id = param.feat_names.index(feature_name)
    pretty = pretty_name(feature_name)
    step_path = output_dir / "steps" / f"{pretty}.step"
    label_path = output_dir / "labels" / f"{pretty}.json"
    image_path = output_dir / "png" / f"{pretty}.png"

    with temporary_parameter_overrides(PAPER_PARAMETER_OVERRIDES), paper_bound_orientation(), paper_shifter_range(), paper_blind_depth_range(), paper_variable_round_contrast():
        shape, labels = feature_creation.shape_from_directive([feature_id])

    if shape is None:
        raise RuntimeError(f"shape_from_directive returned None for {feature_name}")
    if len(occ_utils.list_face(shape)) == 0:
        raise RuntimeError(f"No faces generated for {feature_name}")

    seg_map, _, _ = labels
    save_step_with_face_labels(step_path, shape, seg_map)
    save_label_json(label_path, shape, labels)
    export_step_preview(step_path, image_path, feature_name, label_path, presets)


def worker(feature_name, output_dir_str, presets_path_str, seed):
    try:
        output_dir = Path(output_dir_str)
        presets = load_view_presets(presets_path_str)
        generate_feature_once(feature_name, output_dir, presets, seed)
        print(f"[OK] {feature_name}")
    except Exception:
        traceback.print_exc()
        raise


def run_with_retry(feature_name, output_dir, presets_path, seed, retries, timeout_s):
    pretty = pretty_name(feature_name)
    paths = [
        output_dir / "steps" / f"{pretty}.step",
        output_dir / "labels" / f"{pretty}.json",
        output_dir / "png" / f"{pretty}.png",
    ]

    for attempt in range(1, retries + 1):
        for path in paths:
            if path.exists():
                trash_path(path)

        attempt_seed = seed + (attempt - 1) * 1009 + FEATURE_NAMES.index(feature_name)
        process = mp.Process(
            target=worker,
            args=(feature_name, str(output_dir), str(presets_path), attempt_seed),
        )
        process.start()
        process.join(timeout=timeout_s)

        if process.is_alive():
            process.terminate()
            process.join()
            print(f"[TIMEOUT] {feature_name} attempt {attempt}/{retries}")
            continue

        if process.exitcode == 0 and all(path.exists() for path in paths):
            return True

        print(f"[RETRY] {feature_name} attempt {attempt}/{retries} exit={process.exitcode}")

    return False


def trash_path(path):
    trash = shutil.which("trash")
    if trash is None:
        raise RuntimeError("Global 'trash' command not found on PATH")
    subprocess.run([trash, str(path)], check=True)


def wrap_label(draw, text, font, max_width):
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def load_overview_font(size):
    candidates = [
        "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/timesbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def build_overview_image(output_dir, feature_names):
    png_dir = output_dir / "png"
    output_path = output_dir / "Paper_Feature_Overview_9x3.png"
    columns = 9
    rows = 3
    cell_width = 310
    image_width = 280
    image_height = 210
    label_height = 72
    margin = 18
    top_padding = 10
    canvas_width = columns * cell_width + (columns + 1) * margin
    canvas_height = rows * (image_height + label_height + top_padding) + (rows + 1) * margin

    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    draw = ImageDraw.Draw(canvas)
    font = load_overview_font(24)

    for index, feature_name in enumerate(feature_names):
        pretty = pretty_name(feature_name)
        png_path = png_dir / f"{pretty}.png"
        if not png_path.exists():
            raise FileNotFoundError(f"Missing PNG for overview: {png_path}")

        col = index % columns
        row = index // columns
        cell_x = margin + col * (cell_width + margin)
        cell_y = margin + row * (image_height + label_height + top_padding + margin)

        with Image.open(png_path) as source:
            image = source.convert("RGB")
            image.thumbnail((image_width, image_height), Image.Resampling.LANCZOS)
            draw_x = cell_x + (cell_width - image.width) // 2
            draw_y = cell_y + (image_height - image.height) // 2
            canvas.paste(image, (draw_x, draw_y))

        label = pretty.replace("_", " ")
        lines = wrap_label(draw, label, font, cell_width - 20)
        line_height = int(font.size * 1.1) if hasattr(font, "size") else 24
        text_y = cell_y + image_height + top_padding
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            draw.text((cell_x + (cell_width - text_w) / 2, text_y), line, fill="black", font=font)
            text_y += line_height

    canvas.save(output_path)
    return output_path


def validate_gallery(output_dir, feature_names):
    failures = []
    for feature_name in feature_names:
        pretty = pretty_name(feature_name)
        step_path = output_dir / "steps" / f"{pretty}.step"
        label_path = output_dir / "labels" / f"{pretty}.json"
        image_path = output_dir / "png" / f"{pretty}.png"
        for path in (step_path, label_path, image_path):
            if not path.exists():
                failures.append(f"Missing {path}")
                continue

        if step_path.exists() and label_path.exists():
            try:
                shape, id_map = shape_with_fid_from_step(str(step_path))
                labels = load_and_validate_label_json(label_path, len(occ_utils.list_face(shape)))
                target_label = param.feat_names.index(feature_name)
                has_feature = any(id_map.get(face) == target_label for face in occ_utils.list_face(shape))
                if not has_feature:
                    failures.append(f"No target feature faces in {step_path.name}")
                bottom = labels["bottom"]
                if not any(str(i) in bottom for i, _ in enumerate(occ_utils.list_face(shape))):
                    failures.append(f"Bottom labels are not indexed for {label_path.name}")
            except Exception as exc:
                failures.append(f"{step_path.name}: {exc}")

    overview = output_dir / "Paper_Feature_Overview_9x3.png"
    if not overview.exists():
        failures.append(f"Missing {overview}")

    if failures:
        raise RuntimeError("Gallery validation failed:\n" + "\n".join(failures))


def cleanup_old_gallery_files(visualization_dir, feature_names):
    trash = shutil.which("trash")
    if trash is None:
        raise RuntimeError("Cannot cleanup old files: global 'trash' command not found on PATH")

    targets = []
    for feature_name in feature_names:
        pretty = pretty_name(feature_name)
        targets.append(visualization_dir / f"{pretty}.step")
        targets.append(visualization_dir / f"{pretty}.png")
    targets.extend(
        [
            visualization_dir / "Feature_Overview_9x3.png",
            visualization_dir / "generate_single_feature_gallery.py",
            visualization_dir / "make_feature_overview.ps1",
        ]
    )
    existing = [str(path) for path in targets if path.exists()]
    if not existing:
        return
    subprocess.run([trash, *existing], check=True)


def build_parser():
    parser = argparse.ArgumentParser(description="Generate paper-ready tricolor previews for all single features.")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "paper_feature_gallery"),
        help="Directory for steps, labels, PNGs, and overview image.",
    )
    parser.add_argument("--features", nargs="*", default=FEATURE_NAMES, help="Feature names to generate.")
    parser.add_argument("--seed", type=int, default=20260602, help="Base random seed.")
    parser.add_argument("--retries", type=int, default=8, help="Maximum retries per feature.")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout in seconds per feature attempt.")
    parser.add_argument(
        "--view-presets",
        default=str(Path(__file__).resolve().parent / "view_presets.json"),
        help="Optional per-feature camera preset JSON.",
    )
    parser.add_argument("--validate-only", action="store_true", help="Validate an existing gallery and exit.")
    parser.add_argument("--skip-cleanup", action="store_true", help="Do not move old root-level gallery files to trash.")
    return parser


def main():
    mp.freeze_support()
    parser = build_parser()
    args = parser.parse_args()
    validate_features(args.features)

    output_dir = Path(args.output_dir).resolve()
    for child in ("steps", "labels", "png"):
        (output_dir / child).mkdir(parents=True, exist_ok=True)
    presets_path = Path(args.view_presets).resolve()

    if args.validate_only:
        validate_gallery(output_dir, args.features)
        print(f"Validated gallery: {output_dir}")
        return 0

    success = []
    failed = []
    print(f"Output directory: {output_dir}")
    print(f"Features to generate: {len(args.features)}")

    for feature_name in args.features:
        print(f"Generating {feature_name} ...")
        if run_with_retry(feature_name, output_dir, presets_path, args.seed, args.retries, args.timeout):
            success.append(feature_name)
        else:
            failed.append(feature_name)

    if failed:
        print(f"Failed ({len(failed)}): {failed}")
        return 1

    overview = build_overview_image(output_dir, args.features)
    validate_gallery(output_dir, args.features)
    print(f"Saved overview image: {overview}")

    if not args.skip_cleanup:
        cleanup_old_gallery_files(Path(__file__).resolve().parent, FEATURE_NAMES)
        print("Moved old root-level gallery files to Recycle Bin.")

    print(f"Success ({len(success)}): {success}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
