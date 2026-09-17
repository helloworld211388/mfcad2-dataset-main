import os
import sys
from multiprocessing import Process
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from OCC.Core.STEPConstruct import stepconstruct_FindEntity
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCC.Core.TCollection import TCollection_HAsciiString
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopoDS import TopoDS_CompSolid, TopoDS_Compound, TopoDS_Solid

import Utils.occ_utils as occ_utils
import Utils.parameters as param
import feature_creation


CHAMFER = 0
THROUGH_HOLE = 1
TRI_PASSAGE = 2
RECT_PASSAGE = 3
SIX_PASSAGE = 4
TRI_THROUGH_SLOT = 5
RECT_THROUGH_SLOT = 6
CIRC_THROUGH_SLOT = 7
RECT_THROUGH_STEP = 8
TWO_SIDES_STEP = 9
SLANTED_STEP = 10
ORING = 11
BLIND_HOLE = 12
TRI_POCKET = 13
RECT_POCKET = 14
SIX_POCKET = 15
CIRC_END_POCKET = 16
RECT_BLIND_SLOT = 17
V_CIRC_BLIND_SLOT = 18
H_CIRC_BLIND_SLOT = 19
TRI_BLIND_STEP = 20
CIRC_BLIND_STEP = 21
RECT_BLIND_STEP = 22
ROUND = 23
COUNTERBORE = 24
COUNTERSUNK = 25
VAR_ROUND = 26


COMPLEX_PARTS = {
    "generated_complex_01": [
        RECT_THROUGH_STEP, TWO_SIDES_STEP, SLANTED_STEP,
        THROUGH_HOLE, BLIND_HOLE, COUNTERBORE,
        RECT_THROUGH_SLOT, RECT_POCKET, CHAMFER, ROUND,
    ],
    "generated_complex_02": [
        RECT_THROUGH_STEP, TRI_PASSAGE, RECT_PASSAGE,
        CIRC_THROUGH_SLOT, COUNTERSUNK, CIRC_END_POCKET,
        RECT_BLIND_SLOT, VAR_ROUND, VAR_ROUND,
    ],
    "generated_complex_03": [
        RECT_THROUGH_STEP, RECT_BLIND_STEP,
        SIX_PASSAGE, TRI_POCKET, SIX_POCKET,
        ORING, COUNTERBORE, V_CIRC_BLIND_SLOT,
        H_CIRC_BLIND_SLOT, ROUND,
    ],
    "generated_complex_04": [
        RECT_THROUGH_STEP, TRI_BLIND_STEP, CIRC_BLIND_STEP,
        TRI_THROUGH_SLOT, RECT_THROUGH_SLOT, BLIND_HOLE,
        RECT_POCKET, COUNTERSUNK, VAR_ROUND,
    ],
    "generated_complex_05": [
        RECT_THROUGH_STEP, TWO_SIDES_STEP,
        THROUGH_HOLE, THROUGH_HOLE, COUNTERBORE,
        COUNTERSUNK, RECT_POCKET, CHAMFER, CHAMFER, ROUND,
    ],
    "generated_complex_06": [
        SLANTED_STEP, RECT_THROUGH_SLOT, CIRC_THROUGH_SLOT,
        TRI_PASSAGE, SIX_PASSAGE, RECT_BLIND_SLOT,
        CIRC_END_POCKET, VAR_ROUND, ROUND,
    ],
    "generated_complex_07": [
        RECT_THROUGH_STEP, RECT_BLIND_STEP, TRI_BLIND_STEP,
        TRI_POCKET, RECT_POCKET, SIX_POCKET,
        BLIND_HOLE, ORING, COUNTERBORE,
    ],
    "generated_complex_08": [
        RECT_THROUGH_STEP, TWO_SIDES_STEP,
        RECT_PASSAGE, TRI_PASSAGE, THROUGH_HOLE,
        RECT_THROUGH_SLOT, TRI_THROUGH_SLOT,
        CHAMFER, VAR_ROUND,
    ],
    "generated_complex_09": [
        RECT_THROUGH_STEP, SLANTED_STEP,
        BLIND_HOLE, COUNTERSUNK, COUNTERBORE,
        RECT_BLIND_SLOT, V_CIRC_BLIND_SLOT, ROUND, ROUND,
    ],
    "generated_complex_10": [
        RECT_THROUGH_STEP, CIRC_BLIND_STEP, RECT_BLIND_STEP,
        CIRC_END_POCKET, RECT_POCKET, SIX_POCKET,
        H_CIRC_BLIND_SLOT, VAR_ROUND, CHAMFER,
    ],
    "generated_complex_11": [
        RECT_THROUGH_STEP, TWO_SIDES_STEP, SLANTED_STEP,
        SIX_PASSAGE, RECT_PASSAGE, THROUGH_HOLE,
        COUNTERBORE, RECT_POCKET, VAR_ROUND,
    ],
    "generated_complex_12": [
        RECT_THROUGH_STEP, TRI_BLIND_STEP,
        TRI_THROUGH_SLOT, RECT_THROUGH_SLOT, CIRC_THROUGH_SLOT,
        BLIND_HOLE, COUNTERSUNK, RECT_POCKET, ROUND,
    ],
    "generated_complex_13": [
        RECT_THROUGH_STEP, RECT_BLIND_STEP,
        ORING, SIX_PASSAGE, TRI_POCKET,
        CIRC_END_POCKET, COUNTERBORE, COUNTERSUNK,
        H_CIRC_BLIND_SLOT, VAR_ROUND,
    ],
}


def save_step(step_path, shape, seg_map):
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    finderp = writer.WS().TransferWriter().FinderProcess()
    faces = occ_utils.list_face(shape)
    loc = TopLoc_Location()
    for face in faces:
        item = stepconstruct_FindEntity(finderp, face, loc)
        if item is not None:
            item.SetName(TCollection_HAsciiString(str(seg_map[face])))
    writer.Write(str(step_path))


def generate_one(step_dir, combo, name):
    shape, labels = feature_creation.shape_from_directive(combo)
    if shape is None:
        raise RuntimeError(f"shape is None for {name}")
    if not isinstance(shape, (TopoDS_Solid, TopoDS_Compound, TopoDS_CompSolid)):
        raise RuntimeError(f"unsupported shape type for {name}: {type(shape)}")
    seg_map, _, _ = labels
    if len(occ_utils.list_face(shape)) == 0:
        raise RuntimeError(f"no faces for {name}")
    save_step(step_dir / f"{name}.step", shape, seg_map)


def worker(step_dir_str, combo, name):
    generate_one(Path(step_dir_str), combo, name)


def generate_with_retry(step_dir, combo, name, retries=5, timeout_s=180):
    step_path = step_dir / f"{name}.step"
    for attempt in range(1, retries + 1):
        if step_path.exists():
            step_path.unlink()
        process = Process(target=worker, args=(str(step_dir), combo, name))
        process.start()
        process.join(timeout=timeout_s)
        if process.is_alive():
            process.terminate()
            process.join()
            print(f"[TIMEOUT] {name} attempt {attempt}/{retries}")
            continue
        if process.exitcode == 0 and step_path.exists():
            print(f"[OK] {name}")
            return True
        print(f"[RETRY] {name} attempt {attempt}/{retries} exit={process.exitcode}")
    return False


def main():
    step_dir = Path(__file__).resolve().parent / "generated_complex_steps"
    step_dir.mkdir(parents=True, exist_ok=True)

    success = []
    failed = []
    for name, combo in COMPLEX_PARTS.items():
        print(f"Generating {name}: {[param.feat_names[i] for i in combo]}")
        if generate_with_retry(step_dir, combo, name):
            success.append(name)
        else:
            failed.append(name)

    print(f"Success: {success}")
    print(f"Failed: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
