import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_Reader
import Utils.occ_utils as occ_utils


def numeric_sort_key(path):
    stem = path.stem
    return (0, int(stem)) if stem.isdigit() else (1, stem.lower())


def face_count(step_path):
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_path))
    if status != IFSelect_RetDone:
        return -1
    if reader.TransferRoots() == 0:
        return -1
    shape = reader.OneShape()
    if shape.IsNull():
        return -1
    return len(occ_utils.list_face(shape))


def main():
    parser = argparse.ArgumentParser(description="Pick 18 complex STEP examples.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--demo-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--demo-count", type=int, default=5)
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    demo_dir = Path(args.demo_dir).resolve()
    output_json = Path(args.output_json).resolve()

    demo_steps = sorted(demo_dir.glob("*.step"))
    data_steps = sorted(data_dir.glob("*.step"), key=numeric_sort_key)

    selected = []
    for path in demo_steps[: args.demo_count]:
        selected.append({"path": str(path), "name": path.name, "faces": face_count(path), "source": "demo"})

    remaining = max(0, args.count - len(selected))
    ranked_data = []
    for path in data_steps:
        ranked_data.append({"path": str(path), "name": path.name, "faces": face_count(path), "source": "data"})
    ranked_data.sort(key=lambda item: (item["faces"], item["name"]), reverse=True)

    selected.extend(ranked_data[:remaining])

    with output_json.open("w", encoding="utf8") as fp:
        json.dump(selected, fp, indent=2, ensure_ascii=False)

    print(json.dumps(selected, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
