# Paper Feature Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一套论文展示版 27 类加工特征图库生成流程，并强制 viewer 使用 stock/feature/bottom 三色渲染。

**Architecture:** 将可测试的标签路径解析、JSON 校验、三色分类和展示参数管理放到 `feature_viewer_common.py`。`step_viewer_prototype.py` 只负责交互加载并调用公共三色逻辑。新增 `generate_paper_feature_gallery.py` 负责展示版 STEP/JSON/PNG/总览图生成和成功后的旧文件清理。

**Tech Stack:** Python 3.9, pythonocc-core/OCC, PyQt5 viewer, `unittest`, Windows `trash` for non-Git cleanup.

---

## File Structure

- Modify `visualization/feature_viewer_common.py`
  - 新增三色颜色常量、标签路径解析、JSON 读取校验、face index 映射、三色 AIS 构建、展示参数上下文管理。
- Modify `visualization/step_viewer_prototype.py`
  - 加载 STEP 时强制读取合法 JSON，渲染和导出都使用三色 AIS；失败时拒绝渲染。
- Create `visualization/generate_paper_feature_gallery.py`
  - 生成 27 类展示版 STEP/JSON/PNG/9x3 总览图；验证成功后用 `trash` 清理旧图库文件和重复脚本。
- Create `tests/test_feature_viewer_common.py`
  - 测试纯逻辑：标签路径解析、JSON 校验、三色分类、展示参数恢复。
- Keep `visualization/render_dataset_examples.py`
  - 数据集样例渲染脚本不属于 27 类单特征图库，保留。

---

### Task 1: Public Label and Color Helpers

**Files:**
- Modify: `visualization/feature_viewer_common.py`
- Test: `tests/test_feature_viewer_common.py`

- [ ] **Step 1: Write failing tests for label path resolution and JSON validation**

Create `tests/test_feature_viewer_common.py` with:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from visualization.feature_viewer_common import (
    classify_tricolor_face,
    load_and_validate_label_json,
    resolve_label_json_path,
)


class FeatureViewerCommonTest(unittest.TestCase):
    def test_resolve_label_json_same_directory(self):
        with TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "Chamfer.step"
            json_path = Path(tmp) / "Chamfer.json"
            step_path.write_text("", encoding="utf8")
            json_path.write_text('{"cls": {}, "seg": [], "bottom": {}}', encoding="utf8")

            self.assertEqual(resolve_label_json_path(step_path), json_path)

    def test_resolve_label_json_paper_gallery_layout(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "paper_feature_gallery"
            step_dir = root / "steps"
            label_dir = root / "labels"
            step_dir.mkdir(parents=True)
            label_dir.mkdir()
            step_path = step_dir / "Through_hole.step"
            json_path = label_dir / "Through_hole.json"
            step_path.write_text("", encoding="utf8")
            json_path.write_text('{"cls": {}, "seg": [], "bottom": {}}', encoding="utf8")

            self.assertEqual(resolve_label_json_path(step_path), json_path)

    def test_missing_label_json_raises(self):
        with TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "Blind_hole.step"
            step_path.write_text("", encoding="utf8")

            with self.assertRaisesRegex(FileNotFoundError, "Missing label JSON"):
                resolve_label_json_path(step_path)

    def test_load_and_validate_label_json_requires_bottom_count(self):
        with TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "Rectangular_pocket.json"
            json_path.write_text(
                json.dumps({"cls": {"0": 14}, "seg": [[0]], "bottom": {"0": 1}}),
                encoding="utf8",
            )

            labels = load_and_validate_label_json(json_path, expected_face_count=1)
            self.assertEqual(labels["bottom"], {"0": 1})

            with self.assertRaisesRegex(ValueError, "face count"):
                load_and_validate_label_json(json_path, expected_face_count=2)

    def test_classify_tricolor_face(self):
        self.assertEqual(classify_tricolor_face(14, 14, 1), "bottom")
        self.assertEqual(classify_tricolor_face(14, 14, 0), "feature")
        self.assertEqual(classify_tricolor_face(27, 14, 0), "stock")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest tests.test_feature_viewer_common -v
```

Expected: FAIL because `classify_tricolor_face`, `load_and_validate_label_json`, and `resolve_label_json_path` do not exist.

- [ ] **Step 3: Implement helpers in `feature_viewer_common.py`**

Add imports and functions:

```python
STOCK_COLOR = Quantity_Color(0.62, 0.38, 0.02, Quantity_TOC_RGB)
FEATURE_COLOR = Quantity_Color(0.0, 0.78, 0.0, Quantity_TOC_RGB)
BOTTOM_COLOR = Quantity_Color(0.86, 0.0, 0.0, Quantity_TOC_RGB)


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
    with Path(label_path).open("r", encoding="utf8") as fp:
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
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
python -m unittest tests.test_feature_viewer_common -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add visualization/feature_viewer_common.py tests/test_feature_viewer_common.py
git commit -m "添加三色标签公共工具"
```

---

### Task 2: Build Three-Color AIS and Force Viewer Labels

**Files:**
- Modify: `visualization/feature_viewer_common.py`
- Modify: `visualization/step_viewer_prototype.py`
- Test: `tests/test_feature_viewer_common.py`

- [ ] **Step 1: Extend tests for strict label errors**

Add to `FeatureViewerCommonTest`:

```python
    def test_load_and_validate_label_json_requires_all_keys(self):
        with TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "bad.json"
            json_path.write_text(json.dumps({"cls": {}, "bottom": {}}), encoding="utf8")

            with self.assertRaisesRegex(ValueError, "missing 'seg'"):
                load_and_validate_label_json(json_path, expected_face_count=0)
```

- [ ] **Step 2: Run tests and verify current behavior**

Run:

```powershell
python -m unittest tests.test_feature_viewer_common -v
```

Expected: PASS after helper behavior is correct.

- [ ] **Step 3: Add `build_tricolor_ais()`**

In `feature_viewer_common.py`, add:

```python
def face_index_map(shape):
    return {face: idx for idx, face in enumerate(occ_utils.list_face(shape))}


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
        role = classify_tricolor_face(id_map.get(face), target_label, bottom_label[face_idx])
        ais.SetCustomColor(face, role_colors[role])

    return ais
```

- [ ] **Step 4: Modify viewer loading and export**

In `step_viewer_prototype.py`:

- Replace import of `build_colored_ais` with `build_tricolor_ais`, `load_and_validate_label_json`, and `resolve_label_json_path`.
- Add `self.current_labels = None` in `__init__`.
- In `load_step()`:
  - Load `faces = occ_utils.list_face(shape)` through common helper indirectly by using `len(id_map)` only if all face labels exist; better use `len(occ_utils.list_face(shape))` after importing `Utils.occ_utils as occ_utils`.
  - Resolve JSON.
  - Validate JSON.
  - On error: clear display, reset current state, show message, raise or return without rendering.
  - Use `build_tricolor_ais(shape, id_map, feature_name, labels["bottom"])`.
- In `save_png()`, use `self.current_labels["bottom"]` and `build_tricolor_ais()`.

- [ ] **Step 5: Run syntax and unit verification**

Run:

```powershell
python -m unittest tests.test_feature_viewer_common -v
python -m py_compile visualization/feature_viewer_common.py visualization/step_viewer_prototype.py
```

Expected: both commands pass.

- [ ] **Step 6: Commit**

```powershell
git add visualization/feature_viewer_common.py visualization/step_viewer_prototype.py tests/test_feature_viewer_common.py
git commit -m "强制STEP查看器使用三色标签"
```

---

### Task 3: Paper Gallery Generator

**Files:**
- Create: `visualization/generate_paper_feature_gallery.py`
- Modify: `visualization/feature_viewer_common.py`
- Test: `tests/test_feature_viewer_common.py`

- [ ] **Step 1: Add tests for temporary parameter restoration**

Add to `tests/test_feature_viewer_common.py`:

```python
from visualization.feature_viewer_common import temporary_parameter_overrides
import Utils.parameters as param


    def test_temporary_parameter_overrides_restore_values(self):
        original = param.stock_min_x
        with temporary_parameter_overrides({"stock_min_x": original + 10.0}):
            self.assertEqual(param.stock_min_x, original + 10.0)
        self.assertEqual(param.stock_min_x, original)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest tests.test_feature_viewer_common -v
```

Expected: FAIL because `temporary_parameter_overrides` does not exist.

- [ ] **Step 3: Implement parameter context manager**

In `feature_viewer_common.py`, add:

```python
from contextlib import contextmanager


@contextmanager
def temporary_parameter_overrides(overrides):
    previous = {name: getattr(param, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(param, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(param, name, value)
```

- [ ] **Step 4: Create generator script**

Implement `visualization/generate_paper_feature_gallery.py` with:

- argparse options: `--output-dir`, `--features`, `--seed`, `--retries`, `--timeout`, `--view-presets`, `--skip-cleanup`.
- `PAPER_PARAMETER_OVERRIDES`:
  - stock dimensions fixed/narrow around 24, 24, 18;
  - `min_len = 4.0`;
  - `clearance = 1`;
  - `chamfer_depth_min = 1.2`, `chamfer_depth_max = 2.4`;
  - `round_radius_min = 0.8`, `round_radius_max = 2.4`;
  - `variable_round_radius_min = 0.6`, `variable_round_radius_max = 2.2`.
- monkey patch or context for `MachiningFeature._shifter` using scale range `0.45-0.85`.
- Save STEP with face labels.
- Save JSON labels with `feature_creation.get_cls_label`, `get_seg_label`, `get_bottom_label`.
- Render PNG with `build_tricolor_ais`.
- Compose overview using PIL if available, otherwise System.Drawing via PowerShell is not embedded; prefer Python standard fallback with `PIL` optional check. If PIL is unavailable, use `System.Drawing` through pythonnet is not guaranteed, so keep the existing PowerShell logic migrated only if available. For this environment, use PIL only if import succeeds and fail clearly otherwise.

- [ ] **Step 5: Run unit and syntax verification**

Run:

```powershell
python -m unittest tests.test_feature_viewer_common -v
python -m py_compile visualization/generate_paper_feature_gallery.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add visualization/generate_paper_feature_gallery.py visualization/feature_viewer_common.py tests/test_feature_viewer_common.py
git commit -m "添加论文展示特征图库生成器"
```

---

### Task 4: Generate, Validate, and Cleanup Old Gallery Assets

**Files:**
- Generated: `visualization/paper_feature_gallery/steps/*.step`
- Generated: `visualization/paper_feature_gallery/labels/*.json`
- Generated: `visualization/paper_feature_gallery/png/*.png`
- Generated: `visualization/paper_feature_gallery/Paper_Feature_Overview_9x3.png`
- Remove via trash: old scattered gallery files and duplicate scripts

- [ ] **Step 1: Run generator in the OCC conda environment**

Run:

```powershell
cmd.exe /c "call C:\ProgramData\miniconda3\condabin\conda.bat activate myoccwlenv && python visualization\generate_paper_feature_gallery.py --retries 8 --timeout 180"
```

Expected: 27 successes, no failed features.

- [ ] **Step 2: Validate generated output counts**

Run:

```powershell
(Get-ChildItem visualization\paper_feature_gallery\steps -Filter *.step).Count
(Get-ChildItem visualization\paper_feature_gallery\labels -Filter *.json).Count
(Get-ChildItem visualization\paper_feature_gallery\png -Filter *.png).Count
Test-Path visualization\paper_feature_gallery\Paper_Feature_Overview_9x3.png
```

Expected:

```text
27
27
27
True
```

- [ ] **Step 3: Run generator validation-only path**

Run:

```powershell
cmd.exe /c "call C:\ProgramData\miniconda3\condabin\conda.bat activate myoccwlenv && python visualization\generate_paper_feature_gallery.py --validate-only"
```

Expected: validation summary reports all 27 STEP/JSON/PNG assets valid.

- [ ] **Step 4: Clean old scattered gallery files with `trash`**

Use `trash` for non-Git deletion:

```powershell
trash visualization\*.step
trash visualization\Chamfer.png visualization\Through_hole.png visualization\Triangular_passage.png visualization\Rectangular_passage.png visualization\6sides_passage.png visualization\Triangular_through_slot.png visualization\Rectangular_through_slot.png visualization\Circular_through_slot.png visualization\Rectangular_through_step.png visualization\2sides_through_step.png visualization\Slanted_through_step.png visualization\Oring.png visualization\Blind_hole.png visualization\Triangular_pocket.png visualization\Rectangular_pocket.png visualization\6sides_pocket.png visualization\Circular_end_pocket.png visualization\Rectangular_blind_slot.png visualization\V_circular_end_blind_slot.png visualization\H_circular_end_blind_slot.png visualization\Triangular_blind_step.png visualization\Circular_blind_step.png visualization\Rectangular_blind_step.png visualization\Round.png visualization\Counterbore.png visualization\Countersunk_hole.png visualization\Variable_round.png
trash visualization\Feature_Overview_9x3.png
trash visualization\generate_single_feature_gallery.py
trash visualization\make_feature_overview.ps1
```

Expected: files move to Recycle Bin. Keep dataset-example scripts and complex-example scripts.

- [ ] **Step 5: Final verification**

Run:

```powershell
python -m unittest tests.test_feature_viewer_common -v
python -m py_compile visualization/feature_viewer_common.py visualization/step_viewer_prototype.py visualization/generate_paper_feature_gallery.py
git status --short
```

Expected: unit tests and compile pass. `git status` shows only intended modified/new/deleted files plus pre-existing unrelated dirty files.

- [ ] **Step 6: Commit implementation and generated gallery**

```powershell
git add visualization/feature_viewer_common.py visualization/step_viewer_prototype.py visualization/generate_paper_feature_gallery.py tests/test_feature_viewer_common.py visualization/paper_feature_gallery docs/superpowers/plans/2026-06-02-paper-feature-gallery.md
git add -u visualization
git commit -m "生成论文展示版三色特征图库"
```

---

## Self-Review

- Spec coverage: plan covers strict tricolor viewer, paper gallery generator, JSON labels, enlarged display parameters, overview image, validation, and old file cleanup.
- Placeholder scan: no TBD/TODO steps; each task has concrete files, commands, expected results, and code snippets for pure helpers.
- Type consistency: helper names are consistent across tasks: `resolve_label_json_path`, `load_and_validate_label_json`, `classify_tricolor_face`, `build_tricolor_ais`, `temporary_parameter_overrides`.
