# 论文展示版加工特征图库设计

## 背景

当前 `visualization/` 目录中已有 27 类单特征 STEP 和 PNG，但它们存在两个问题：

1. 渲染颜色不符合论文展示需求。目标效果应与 MFInstSeg 示例图一致：stock faces 为棕色，feature non-bottom faces 为绿色，feature bottom faces 为红色。
2. 一些特征相对基体过小，不适合截图或放入论文总览图。

本设计新增一套独立的论文展示版图库生成流程，只服务论文配图，不改变数据集默认生成逻辑。

## 目标

新增 `visualization/generate_paper_feature_gallery.py`，一键生成 27 类加工特征的展示版资产：

- 27 个展示版 STEP 文件；
- 27 个包含 `cls`、`seg`、`bottom` 的 JSON 标签文件；
- 27 张三色单特征 PNG；
- 1 张 9 x 3 的 27 类总览图。

生成结果统一放在 `visualization/paper_feature_gallery/` 下，避免论文图库文件继续散落在 `visualization/` 根目录。

## 非目标

- 不修改 `main.py` 的数据集生成行为。
- 不永久修改 `Utils/parameters.py` 的默认参数。
- 不追求展示版几何分布符合训练数据分布。
- 不保留旧的 27 类单特征图库入口并与新入口并存。

## 输出结构

`generate_paper_feature_gallery.py` 默认输出到：

```text
visualization/paper_feature_gallery/
  steps/
    Chamfer.step
    Through_hole.step
    ...
  labels/
    Chamfer.json
    Through_hole.json
    ...
  png/
    Chamfer.png
    Through_hole.png
    ...
  Paper_Feature_Overview_9x3.png
```

`steps/`、`labels/`、`png/` 中的文件名使用现有 `pretty_name()` 规则，保持与当前图库命名一致。

## 特征范围和顺序

生成全部 27 类特征，顺序沿用当前 `feature_viewer_common.FEATURE_NAMES`：

```text
chamfer
through_hole
triangular_passage
rectangular_passage
6sides_passage
triangular_through_slot
rectangular_through_slot
circular_through_slot
rectangular_through_step
2sides_through_step
slanted_through_step
Oring
blind_hole
triangular_pocket
rectangular_pocket
6sides_pocket
circular_end_pocket
rectangular_blind_slot
v_circular_end_blind_slot
h_circular_end_blind_slot
triangular_blind_step
circular_blind_step
rectangular_blind_step
round
counterbore
countersunk_hole
variable_round
```

总览图使用 9 列 x 3 行，按以上顺序排列。

## 展示版几何策略

展示版生成优先保证“特征一眼可辨认”，不模拟真实数据分布。

### Stock 尺寸

脚本运行期间临时覆盖 stock 参数，使基体更规整、更稳定。例如使用固定或窄范围尺寸，约为 `24 x 24 x 18`。覆盖只在脚本内部生效，结束后恢复原值。

### 切削特征比例

对于 hole、passage、slot、pocket、counterbore、countersunk 等依赖 `MachiningFeature._shifter()` 控制 sketch 尺寸的特征，展示模式下将宽高缩放范围从原来的 `0.1-1.0` 调整为更大的区间，例如 `0.45-0.85`。

该调整只在新脚本运行时生效，目标是让孔径、槽宽、pocket 面积相对 stock 更大，便于论文截图。

### 倒角和圆角

`chamfer`、`round`、`variable_round` 不走普通 pocket/hole 的 `_shifter()`，需要单独放大展示参数：

- `chamfer_depth_min/max`
- `round_radius_min/max`
- `variable_round_radius_min/max`

这些参数同样只在新脚本运行期间临时覆盖。

### 可复现性

脚本提供 `--seed` 参数，默认固定 seed。生成效果不满意时，可以换 seed 重跑。

## 标签保存

生成每个特征时，复用 `feature_creation.shape_from_directive([feature_id])` 返回的标签：

- `seg_map`: face 到语义类别 id 的映射；
- `inst_label`: feature instance 标签；
- `bottom_map`: bottom face 标签。

输出规则：

- STEP 文件中继续将语义类别 id 写入 face name，兼容现有 `shape_with_fid_from_step()`。
- JSON 文件保存 `cls`、`seg`、`bottom`，其中 `bottom` 必须来自生成器返回的 `bottom_map`，不能在渲染阶段猜测。

## 三色渲染

在 `feature_viewer_common.py` 中新增三色构建逻辑，例如：

```text
build_tricolor_ais(shape, id_map, feature_name, bottom_label)
```

颜色规则固定为：

- target feature 且 `bottom=1`：红色；
- target feature 且 `bottom=0`：绿色；
- 其它所有 face：棕色 stock。

stock 面无论语义标签是 `plane`、`cylinder` 还是 `cone`，都统一显示为棕色。

## `step_viewer_prototype.py` 强制三色

`step_viewer_prototype.py` 必须展示三色，不允许静默降级为两色。

加载 STEP 时必须找到对应 JSON，查找顺序为：

1. STEP 同目录下的同名 `.json`；
2. 如果 STEP 位于 `paper_feature_gallery/steps/`，则查找 `paper_feature_gallery/labels/<same>.json`。

如果出现以下情况，viewer 应报错并拒绝渲染当前 STEP：

- 找不到 JSON；
- JSON 不包含 `cls`、`seg`、`bottom`；
- STEP face 数量与 JSON 中 `bottom` face 数量不一致；
- 无法推断当前 STEP 对应的目标 feature name。

## PNG 导出

`generate_paper_feature_gallery.py` 直接批量渲染 27 张三色 PNG，不依赖人工打开 viewer。

相机策略：

1. 如果 `view_presets.json` 中存在对应条目，优先使用 preset；
2. 否则使用 `compute_auto_camera()`；
3. 如果自动相机失败，退回等轴测视角并 `FitAll()`。

PNG 默认输出到 `paper_feature_gallery/png/`。

## 总览图

新脚本生成 `Paper_Feature_Overview_9x3.png`，放在 `paper_feature_gallery/` 根目录。

总览图要求：

- 白色背景；
- 9 列 x 3 行；
- 每格包含单特征 PNG 和英文标签；
- 标签使用当前 pretty name，将下划线替换为空格；
- 排版可复用现有 `make_feature_overview.ps1` 的尺寸和字体逻辑，或迁移为 Python 实现。

## 旧文件清理

新图库成功生成并验证后，清理旧的论文图库相关文件。

应删除的旧文件包括：

- `visualization/` 根目录下旧的 27 个单特征 `.step`；
- `visualization/` 根目录下旧的 27 个单特征 `.png`；
- `visualization/Feature_Overview_9x3.png`；
- 与生成 27 类单特征图库或总览图作用重复的旧脚本，例如：
  - `visualization/generate_single_feature_gallery.py`
  - `visualization/make_feature_overview.ps1`

应保留的文件包括：

- `visualization/step_viewer_prototype.py`
- `visualization/feature_viewer_common.py`
- `visualization/render_dataset_examples.py`
- `visualization/make_dataset_examples_overview.ps1`
- 数据集样例、复杂样例相关脚本和选择文件

如果旧脚本中仍有必要逻辑，应迁移到新脚本或公共模块中，不继续保留重复入口。

删除操作遵循本机 `AGENTS.md` 规则：非 Git 删除使用全局 `trash` 命令，将文件移动到 Windows 回收站，不做永久删除。

## 验证

新脚本完成后必须验证：

- `steps/` 中存在 27 个 STEP；
- `labels/` 中存在 27 个 JSON；
- `png/` 中存在 27 个 PNG；
- `Paper_Feature_Overview_9x3.png` 存在；
- 每个 JSON 均包含 `cls`、`seg`、`bottom`；
- 每个 STEP 读取出的 face 数量与对应 JSON 的 `bottom` 数量一致；
- 每个目标 feature 至少有一个 feature face 被渲染为绿色或红色；
- `step_viewer_prototype.py` 在缺少 JSON 或 JSON 不合法时拒绝渲染并提示错误；
- `main.py` 和默认数据集生成参数不受展示版流程影响。

## 实施顺序

1. 扩展三色渲染公共函数和标签读取/校验逻辑。
2. 修改 `step_viewer_prototype.py`，强制读取 JSON 并使用三色渲染。
3. 新增 `generate_paper_feature_gallery.py`，实现展示版生成、标签保存、PNG 渲染和总览图合成。
4. 运行新脚本生成并验证 27 类展示版图库。
5. 成功后使用 `trash` 清理旧的散落文件和重复脚本。
6. 运行必要的 smoke test，确认 viewer 和新脚本行为符合设计。
