import argparse
import json
import math
import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from OCC.Core.AIS import AIS_ColoredShape
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Quantity import Quantity_Color, Quantity_NOC_WHITE, Quantity_TOC_RGB
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Display.SimpleGui import init_display
import Utils.occ_utils as occ_utils


BROWN = Quantity_Color(0.66, 0.43, 0.05, Quantity_TOC_RGB)
WHITE = Quantity_Color(Quantity_NOC_WHITE)


def numeric_sort_key(path):
    stem = path.stem
    return (0, int(stem)) if stem.isdigit() else (1, stem.lower())


def select_examples(step_dir, count):
    step_files = sorted(step_dir.glob("*.step"), key=numeric_sort_key)
    if len(step_files) < count:
        raise ValueError(f"Only found {len(step_files)} STEP files in {step_dir}, need {count}.")
    if len(step_files) == count:
        return step_files
    if count == 1:
        return [step_files[0]]

    selected = []
    last_index = len(step_files) - 1
    for i in range(count):
        idx = round(i * last_index / (count - 1))
        selected.append(step_files[idx])

    deduped = []
    seen = set()
    for path in selected:
        if path not in seen:
            deduped.append(path)
            seen.add(path)

    if len(deduped) < count:
        for path in step_files:
            if path not in seen:
                deduped.append(path)
                seen.add(path)
            if len(deduped) == count:
                break

    return deduped[:count]


def load_step_shape(step_path):
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed: {step_path}")
    transferred = reader.TransferRoots()
    if transferred == 0:
        raise RuntimeError(f"STEP transfer failed: {step_path}")
    shape = reader.OneShape()
    if shape.IsNull():
        raise RuntimeError(f"STEP shape is null: {step_path}")
    return shape


def apply_soft_shadow(image_path, offset=(14, 18), blur_radius=12, opacity=95, padding=26):
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        print("[WARN] Pillow is not installed; exported brown render without soft shadow.")
        return

    source = Image.open(image_path).convert("RGBA")
    rgb = source.convert("RGB")
    pixels = rgb.load()
    mask = Image.new("L", source.size, 0)
    mask_pixels = mask.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b = pixels[x, y]
            if r > 115 and 75 <= g <= 190 and b < 95 and (r - b) > 70:
                mask_pixels[x, y] = 255

    canvas_size = (
        source.width + (padding * 2) + abs(offset[0]),
        source.height + (padding * 2) + abs(offset[1]),
    )
    model_x = padding + max(0, -offset[0])
    model_y = padding + max(0, -offset[1])
    shadow_x = model_x + offset[0]
    shadow_y = model_y + offset[1]

    shadow_alpha = mask.filter(ImageFilter.GaussianBlur(blur_radius)).point(
        lambda value: int(value * (opacity / 255.0))
    )
    shadow = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    shadow_color = Image.new("RGBA", source.size, (80, 52, 18, 255))
    shadow.paste(shadow_color, (shadow_x, shadow_y), shadow_alpha)

    model = Image.new("RGBA", source.size, (0, 0, 0, 0))
    model.paste(source, (0, 0), mask)

    canvas = Image.new("RGBA", canvas_size, (255, 255, 255, 255))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(model, (model_x, model_y))
    canvas.convert("RGB").save(image_path)


def send_to_trash(path):
    subprocess.run(["cmd.exe", "/c", "trash", str(path)], check=False)


def render_one(step_path, image_path, shadow=True, shadow_offset=(14, 18), shadow_blur=12, shadow_opacity=95):
    shape = load_step_shape(step_path)
    display, _, _, _ = init_display()
    display.EraseAll()
    display.Context.RemoveAll(False)
    display.View.SetBackgroundColor(WHITE)
    display.hide_triedron()
    display.View.TriedronErase()
    display.SetModeShaded()
    display.default_drawer.SetFaceBoundaryDraw(True)

    ais = AIS_ColoredShape(shape)
    for face in occ_utils.list_face(shape):
        ais.SetCustomColor(face, BROWN)

    display.Context.Display(ais, True)
    display.View_Iso()
    display.FitAll()
    display.View.ZFitAll()
    display.View.Redraw()
    display.ExportToImage(str(image_path))
    if shadow:
        apply_soft_shadow(
            image_path,
            offset=shadow_offset,
            blur_radius=shadow_blur,
            opacity=shadow_opacity,
        )


def render_worker(step_path_str, image_path_str, shadow, shadow_offset, shadow_blur, shadow_opacity):
    step_path = Path(step_path_str)
    image_path = Path(image_path_str)
    render_one(step_path, image_path, shadow, shadow_offset, shadow_blur, shadow_opacity)


def render_with_retry(step_path, image_path, retries, timeout_s, shadow, shadow_offset, shadow_blur, shadow_opacity):
    for attempt in range(1, retries + 1):
        if image_path.exists():
            send_to_trash(image_path)

        process = mp.Process(
            target=render_worker,
            args=(str(step_path), str(image_path), shadow, shadow_offset, shadow_blur, shadow_opacity),
        )
        process.start()
        process.join(timeout=timeout_s)

        if process.is_alive():
            process.terminate()
            process.join()
            print(f"[TIMEOUT] {step_path.name} attempt {attempt}/{retries}")
            continue

        if process.exitcode == 0 and image_path.exists():
            print(f"[OK] {step_path.name}")
            return True

        print(f"[RETRY] {step_path.name} attempt {attempt}/{retries} exit={process.exitcode}")

    return False


def main():
    mp.freeze_support()
    parser = argparse.ArgumentParser(description="Render a fixed set of dataset STEP examples to PNG images.")
    parser.add_argument("--step-dir", required=True, help="Directory containing STEP files.")
    parser.add_argument("--output-dir", required=True, help="Directory to save rendered PNG files.")
    parser.add_argument("--count", type=int, default=18, help="Number of STEP files to render.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per STEP file.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per STEP render in seconds.")
    parser.add_argument("--selection-json", help="Optional JSON file listing exact STEP file paths to render.")
    parser.add_argument("--no-shadow", action="store_true", help="Disable PNG soft shadow post-processing.")
    parser.add_argument("--shadow-blur", type=int, default=12, help="Soft shadow blur radius in pixels.")
    parser.add_argument("--shadow-opacity", type=int, default=95, help="Soft shadow opacity from 0 to 255.")
    parser.add_argument("--shadow-offset-x", type=int, default=14, help="Horizontal soft shadow offset in pixels.")
    parser.add_argument("--shadow-offset-y", type=int, default=18, help="Vertical soft shadow offset in pixels.")
    args = parser.parse_args()

    step_dir = Path(args.step_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.selection_json:
        selection_json = Path(args.selection_json).resolve()
        with selection_json.open("r", encoding="utf8") as fp:
            selected = [Path(item["path"]) for item in json.load(fp)]
    else:
        selected = select_examples(step_dir, args.count)
    print(f"Rendering {len(selected)} STEP files from {step_dir}")

    failed = []
    shadow_offset = (args.shadow_offset_x, args.shadow_offset_y)
    for step_path in selected:
        image_path = output_dir / f"{step_path.stem}.png"
        if not render_with_retry(
            step_path,
            image_path,
            args.retries,
            args.timeout,
            not args.no_shadow,
            shadow_offset,
            args.shadow_blur,
            args.shadow_opacity,
        ):
            failed.append(step_path.name)

    print(f"Rendered: {len(selected) - len(failed)} / {len(selected)}")
    if failed:
        print(f"Failed files: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
