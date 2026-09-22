#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_split.py —— 为 MT-MFRNet 数据集生成**固定、可复现、无泄漏**的 train/val/test 划分，
并额外生成半监督实验所需的「有标签 / 无标签」子集。

设计要点
========
1. **按结构同构组划分**（group split）
   同一个「结构签名」的模型被视为一组，整组一起进入同一个划分。
   结构签名 = (面数, 实例数, 实例尺寸序列, 每类面数)。
   随机划分下会存在跨 train/test 的结构孪生模型（实测 710 组），按组划分后为 0。

2. **有效性过滤**（validity filter）
   - 缺少 bin 预处理文件的模型（无法参与训练）；
   - BRep 包围盒异常的模型：预处理 `multi_StepToBin.normalize_shape` 用
     `BRepBndLib.Add` 取包围盒，对含 BSpline（圆角/过渡）面的模型会按控制极点高估，
     实测最大高估 167 倍（9066 mm vs 真实 54 mm），导致这些模型在 bin 里被压成一点。
     本脚本读入 OCC 扫描结果（同时记录 `Add` 与 `AddOptimal` 两种包围盒），
     取两者较大者与阈值比较，剔除「已损坏」与「真异常」两类模型。

3. **半监督「有标签比例」子集：随机抽样 + 类别覆盖保证**
   数据池固定 = 训练集全体；无标签池 = 训练集减去有标签子集，由固定种子决定。
   子集大小严格等于 round(比例 x 训练集大小)，保持「比例」是唯一变量；
   在此之上加一层保险：若某个加工特征类在有标签子集中一个模型都没有，
   则用含该类的模型做一次替换。实测 r = 1% 时随机抽样已覆盖全部 27 类，该保险通常不触发。

用法
====
    python make_split.py \
        --root   /path/to/myNewDatasets \
        --out    ./splits \
        --ratios 0.7,0.1,0.2 \
        --seed   42 \
        --bbox-csv ./_occ_bbox_scan.csv --bbox-threshold 100 \
        --ratio-subsets 0.01,0.05,0.10,0.20,0.50,1.00 --ratio-seed 0

输出
====
    splits/train.txt val.txt test.txt          每行一个模型 ID（LF 行尾）
    splits/excluded_models.txt                 被剔除的模型及原因
    splits/split_report.md                     统计报告（每类模型数/实例数等）
    splits/labeled_rNN.txt unlabeled_rNN.txt   半监督子集
    splits/ratio_report.md                     各比例下的类别覆盖表

依赖：仅标准库。
"""

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict

# 27 个加工特征类（0-26）；27/28/29 = plane / cylinder / cone，毛坯基体面
BACKGROUND_CLASSES = {27, 28, 29}
N_FEATURE_CLASSES = 27


# ---------------------------------------------------------------------------
# 标注读取
# ---------------------------------------------------------------------------

def _to_face_map(obj):
    out = {}
    if obj is None:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            try:
                out[int(k)] = int(v)
            except (TypeError, ValueError):
                pass
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            try:
                out[i] = int(v)
            except (TypeError, ValueError):
                pass
    return out


def _to_instance_list(obj):
    out = []
    if obj is None:
        return out
    seq = list(obj.values()) if isinstance(obj, dict) else (list(obj) if isinstance(obj, (list, tuple)) else [])
    for v in seq:
        if isinstance(v, (list, tuple)):
            faces = []
            for x in v:
                try:
                    faces.append(int(x))
                except (TypeError, ValueError):
                    pass
            out.append(faces)
    return out


def load_model(json_path):
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    cls_map = _to_face_map(data.get("cls") or data.get("class") or data.get("semantic"))
    inst = _to_instance_list(data.get("seg") or data.get("i") or data.get("instance"))
    bottom = _to_face_map(data.get("bottom") or data.get("bottom_face"))

    if cls_map:
        face_count = max(cls_map.keys()) + 1
    elif inst:
        face_count = max(max(f) for f in inst) + 1
    else:
        return None

    class_face_counts = Counter(cls_map.values())
    class_bottom_counts = Counter()
    for fidx, is_bottom in bottom.items():
        if is_bottom and fidx in cls_map:
            class_bottom_counts[cls_map[fidx]] += 1

    class_instance_counts = Counter()
    for faces in inst:
        ids = [cls_map[f] for f in faces if f in cls_map]
        if ids:
            class_instance_counts[Counter(ids).most_common(1)[0][0]] += 1

    return {
        "face_count": face_count,
        "n_instances": len(inst),
        "n_nonempty_instances": sum(1 for f in inst if f),
        "instance_sizes": sorted(len(f) for f in inst),
        "class_face_counts": dict(class_face_counts),
        "class_instance_counts": dict(class_instance_counts),
        "class_bottom_counts": dict(class_bottom_counts),
        "labeled_faces": len(cls_map),
    }


# ---------------------------------------------------------------------------
# 结构签名与按组分层划分
# ---------------------------------------------------------------------------

def structure_signature(m):
    """结构同构判据：面数 + 实例数 + 实例尺寸序列 + 每类面数 全部一致。"""
    return (
        m["face_count"],
        m["n_instances"],
        tuple(m["instance_sizes"]),
        tuple(sorted(m["class_face_counts"].items())),
    )


def stratified_group_split(models, ratios, seed):
    """以结构同构组为单位的多标签迭代分层划分。

    稀有类优先：每一步把「当前最缺的类别」的组放进该类别最匮乏的划分，
    使每个类别在三个划分中的比例都接近目标。
    """
    rng = random.Random(seed)
    names = ["train", "val", "test"]
    ratios = list(ratios) + [0.0] * (3 - len(ratios))
    ratios = ratios[:3]
    tot = sum(ratios)
    ratios = [r / tot for r in ratios]

    groups = defaultdict(list)
    for s, m in models.items():
        groups[structure_signature(m)].append(s)
    group_classes = {
        k: set().union(*[set(models[s]["class_face_counts"].keys()) for s in v])
        for k, v in groups.items()
    }

    n_total = len(models)
    targets = [int(round(r * n_total)) for r in ratios]
    while sum(targets) < n_total:
        targets[max(range(3), key=lambda i: targets[i] / max(ratios[i], 1e-9))] += 1
    while sum(targets) > n_total:
        targets[min(range(3), key=lambda i: targets[i] / max(ratios[i], 1e-9))] -= 1

    class_totals = Counter()
    for cs in group_classes.values():
        class_totals.update(cs)

    desired = [{c: class_totals[c] * r for c in class_totals} for r in ratios]
    current = [Counter() for _ in names]
    sizes = [0, 0, 0]

    order = sorted(
        groups.keys(),
        key=lambda k: (min((class_totals[c] for c in group_classes[k]), default=0), rng.random()),
    )

    out = {n: [] for n in names}
    for gk in order:
        members = groups[gk]
        cs = group_classes[gk]
        best, best_score = 0, -1e18
        for i in range(3):
            if sizes[i] >= targets[i]:
                continue
            score = 0.0
            for c in cs:
                d = desired[i].get(c, 0.0)
                if d > 0:
                    score += (d - current[i][c]) / d
            score += 1e-6 * (targets[i] - sizes[i])
            if score > best_score:
                best, best_score = i, score
        out[names[best]].extend(members)
        sizes[best] += len(members)
        current[best].update(cs)

    return out, groups


# ---------------------------------------------------------------------------
# 多标签迭代分层（有标签 / 无标签子集）
# ---------------------------------------------------------------------------

def stratified_sample(items, labels_of, ratio, rng, class_universe):
    """随机抽样 + 类别覆盖保证。

    协议要求「有标签子集的比例」是唯一变量，所以子集大小必须严格等于 round(ratio * N)，
    不能因为要照顾稀有类而改变规模。因此这里采用：

      1. 先按比例**随机**抽取 k = round(ratio * N) 个模型（保持无偏）；
      2. 再检查类别覆盖：若某个加工特征类在子集中一个模型都没有，
         就用一个含该类的未抽中模型，替换掉一个「删掉后不会让任何类别掉到 0」的已抽中模型。

    实测本数据集在 r = 1%（k ≈ 204）时随机抽样已能覆盖全部 27 个加工特征类
    （最稀有类患病率 6.96%，期望 14.2 个），因此第 2 步通常不触发，仅作为保险。
    """
    n = len(items)
    k = int(round(ratio * n))
    if k >= n:
        return sorted(items)
    if k <= 0:
        return []

    picked = set(rng.sample(sorted(items), k))
    counts = Counter()
    for it in picked:
        counts.update(labels_of[it])

    for c in class_universe:
        if counts.get(c, 0) > 0:
            continue
        cands = [it for it in items if it not in picked and c in labels_of[it]]
        if not cands:
            continue
        removable = [it for it in picked if all(counts[cc] > 1 for cc in labels_of[it])]
        if not removable:
            break
        victim = removable[rng.randrange(len(removable))]
        picked.discard(victim)
        for cc in labels_of[victim]:
            counts[cc] -= 1
        new = cands[rng.randrange(len(cands))]
        picked.add(new)
        for cc in labels_of[new]:
            counts[cc] += 1

    return sorted(picked)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def read_bbox_exclusions(csv_path, threshold):
    """返回 (超阈值模型集合, 读取失败的模型集合)。

    CSV 列：id,status,add_extent,optimal_extent,n_faces

    判据取 `max(add_extent, optimal_extent)` 与阈值比较，即两者的并集：
      - `add_extent` 大  → 现有 `multi_StepToBin.normalize_shape`（用 BRepBndLib.Add）
                            会把这个模型的包围盒放大，bin 里几何被压扁（**实际已损坏**）；
      - `optimal_extent` 大 → 即使改用 AddOptimal，几何本身就超出毛坯尺寸（**真异常**）。
    毛坯 x/y/z 各 uniform(10,50) mm，加工特征只做材料去除，故包围盒最长边不应超过 50 mm。
    """
    over, failed = set(), set()
    if not csv_path or not os.path.exists(csv_path):
        return over, failed
    with open(csv_path, "r", encoding="utf-8") as f:
        f.readline()  # header
        for ln in f:
            parts = ln.strip().split(",")
            if len(parts) < 5:
                continue
            mid, status = parts[0], parts[1]
            try:
                e = max(float(parts[2]), float(parts[3]))
            except ValueError:
                e = -1.0
            if status != "ok":
                failed.add(mid)
            elif e > threshold:
                over.add(mid)
    return over, failed


def main():
    ap = argparse.ArgumentParser(description="生成固定划分 + 半监督子集")
    ap.add_argument("--root", required=True, help="数据集根目录（含 labels/ bin/ steps/）")
    ap.add_argument("--out", default="./splits", help="输出目录")
    ap.add_argument("--ratios", default="0.7,0.1,0.2", help="train,val,test 比例")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--bbox-csv", default=None, help="OCC 包围盒扫描结果 CSV（可选）")
    ap.add_argument("--bbox-threshold", type=float, default=100.0,
                    help="包围盒最长边超过该值即剔除（毛坯上限 50 mm）")
    ap.add_argument("--no-exclude-missing-bin", action="store_true",
                    help="默认剔除缺 bin 的模型，加此开关则不剔除")
    ap.add_argument("--ratio-subsets", default="",
                    help="生成半监督子集的比例，如 0.01,0.05,0.10,0.20,0.50,1.00")
    ap.add_argument("--ratio-seed", type=int, default=0)
    args = ap.parse_args()

    root = args.root
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    label_dir = os.path.join(root, "labels")
    if not os.path.isdir(label_dir):
        sys.exit("找不到 labels 目录: %s" % label_dir)

    # ---- 1. 读取全部标注 ----
    print("读取标注 ...")
    models = {}
    bad = []
    for fn in sorted(os.listdir(label_dir)):
        if not fn.lower().endswith(".json"):
            continue
        stem = os.path.splitext(fn)[0]
        m = load_model(os.path.join(label_dir, fn))
        if m is None:
            bad.append(stem)
        else:
            models[stem] = m
    print("  解析成功 %d，失败 %d" % (len(models), len(bad)))

    # ---- 2. 有效性过滤 ----
    exclude = {}
    if not args.no_exclude_missing_bin:
        bin_dir = os.path.join(root, "bin")
        if os.path.isdir(bin_dir):
            have = {os.path.splitext(f)[0] for f in os.listdir(bin_dir)}
            for s in models:
                if s not in have:
                    exclude[s] = "missing_bin"
    over, failed = read_bbox_exclusions(args.bbox_csv, args.bbox_threshold)
    for s in over:
        exclude.setdefault(s, "bbox_extent_gt_%.0fmm" % args.bbox_threshold)
    for s in failed:
        exclude.setdefault(s, "step_read_failed")
    for s in bad:
        exclude.setdefault(s, "label_parse_failed")

    kept = {s: m for s, m in models.items() if s not in exclude}
    print("  剔除 %d 个，保留 %d 个" % (len(exclude), len(kept)))

    # ---- 3. 按结构组划分 ----
    ratios = [float(x) for x in args.ratios.split(",")]
    print("按结构同构组分层划分 ratios=%s seed=%d ..." % (ratios, args.seed))
    generated, groups = stratified_group_split(kept, ratios, args.seed)
    sizes = {k: len(v) for k, v in generated.items()}
    print("  划分规模:", sizes)
    print("  结构同构组数: %d（最大组 %d 个模型）" % (len(groups), max(len(v) for v in groups.values())))

    for name in ("train", "val", "test"):
        with open(os.path.join(out_dir, name + ".txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(sorted(generated[name], key=lambda x: (len(x), x))) + "\n")

    with open(os.path.join(out_dir, "excluded_models.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# 被剔除的模型（共 %d 个）\n" % len(exclude))
        f.write("# id\treason\n")
        for s in sorted(exclude, key=lambda x: (len(x), x)):
            f.write("%s\t%s\n" % (s, exclude[s]))

    # ---- 4. 统计报告 ----
    assign = {}
    for name, lst in generated.items():
        for s in lst:
            assign[s] = name

    def stats(subset):
        n = len(subset)
        if n == 0:
            return None
        cface = Counter()
        cinst = Counter()
        cbot = Counter()
        for s in subset:
            m = kept[s]
            cface.update(m["class_face_counts"])
            cinst.update(m["class_instance_counts"])
            cbot.update(m["class_bottom_counts"])
        return {
            "n": n,
            "cface": cface,
            "cinst": cinst,
            "cbot": cbot,
            "faces": sorted(kept[s]["face_count"] for s in subset),
            "insts": sorted(kept[s]["n_instances"] for s in subset),
        }

    L = []

    def P(s=""):
        print(s)
        L.append(s)

    P("# MT-MFRNet 数据集划分报告")
    P()
    P("本报告由 `make_split.py` 自动生成，对应论文返修意见 R2-Q2 中「固定划分 + 每类计数 + "
      "生成范围 + 有效性过滤 + 近重复检查」的要求。")
    P()
    P("- 数据集根目录：`%s`" % os.path.abspath(root))
    P("- 标注文件解析成功：**%d** 个（失败 %d 个）" % (len(models), len(bad)))
    P("- 有效性过滤剔除：**%d** 个" % len(exclude))
    P("- 参与划分：**%d** 个" % len(kept))
    P("- 划分比例 train:val:test = %s，随机种子 **%d**" % (":".join("%g" % r for r in ratios), args.seed))
    P("- 划分方式：**按结构同构组分层**（同一结构签名的模型不跨划分）")
    P("- 结构同构组数：%d，最大组 %d 个模型" % (len(groups), max(len(v) for v in groups.values())))
    P("- 类别约定：语义类别 0–26 为 **27 个加工特征类**；27/28/29（plane/cylinder/cone）为"
      "**毛坯基体面（背景类）**，在训练与评测中被掩码，不产生损失。")
    P()

    P("## 1. 有效性过滤明细")
    P()
    P("| 剔除原因 | 模型数 |")
    P("|---|---|")
    for reason, n in Counter(exclude.values()).most_common():
        P("| %s | %d |" % (reason, n))
    P("| **合计** | **%d** |" % len(exclude))
    P()

    P("## 2. 划分规模")
    P()
    P("| 划分 | 模型数 | 占比 | 面数中位数 | 面数 P95 | 面数最大 | 实例数中位数 |")
    P("|---|---|---|---|---|---|---|")
    for name in ("train", "val", "test"):
        st = stats(generated[name])
        f = st["faces"]
        i = st["insts"]
        P("| %s | %d | %.2f%% | %d | %d | %d | %d |"
          % (name, st["n"], 100.0 * st["n"] / len(kept),
             f[len(f) // 2], f[int(0.95 * (len(f) - 1))], f[-1], i[len(i) // 2]))
    P("| **合计** | **%d** | 100%% | | | | |" % len(kept))
    P()

    P("## 3. 每类模型数 / 实例数 / 面数（按划分）")
    P()
    P("类别名对照见 `Utils/parameters.py` 的 `feat_names`。")
    P()
    P("| 类 | 名称 | train 模型 | val 模型 | test 模型 | train 实例 | val 实例 | test 实例 | train 面 | val 面 | test 面 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    sts = {name: stats(generated[name]) for name in ("train", "val", "test")}
    names_tbl = FEATURE_NAMES
    for c in range(28):
        nm = names_tbl[c] if c < len(names_tbl) else "?"
        row = [str(c), nm]
        for name in ("train", "val", "test"):
            st = sts[name]
            row.append(str(sum(1 for s in generated[name] if st is not None and c in kept[s]["class_face_counts"])))
        for name in ("train", "val", "test"):
            row.append(str(sts[name]["cinst"].get(c, 0)))
        for name in ("train", "val", "test"):
            row.append(str(sts[name]["cface"].get(c, 0)))
        P("| " + " | ".join(row) + " |")
    P()

    P("## 4. 底面标签有效性（按类）")
    P()
    P("底面 = 特征新增面中法向与进刀方向平行的面。贯通类特征（through hole / passage / "
      "through slot / through step）与无方向特征（chamfer / round）**按构造就不存在底面**，"
      "其底面计数为 0 属正常，不代表标注缺失。")
    P()
    P("| 类 | 名称 | train 底面数 | val 底面数 | test 底面数 |")
    P("|---|---|---|---|---|")
    for c in range(28):
        nm = names_tbl[c] if c < len(names_tbl) else "?"
        P("| %d | %s | %d | %d | %d |"
          % (c, nm, sts["train"]["cbot"].get(c, 0), sts["val"]["cbot"].get(c, 0),
             sts["test"]["cbot"].get(c, 0)))
    P()

    P("## 5. 跨划分结构同构检查")
    P()
    sig2split = defaultdict(set)
    for name, lst in generated.items():
        for s in lst:
            sig2split[structure_signature(kept[s])].add(name)
    cross = sum(1 for k, v in sig2split.items() if len(v) > 1)
    P("- 参与划分的结构同构组数：**%d**" % len(sig2split))
    P("- 同时出现在多个划分中的结构同构组数：**%d**" % cross)
    P()
    if cross == 0:
        P("**结论**：不存在跨 train/val/test 的结构同构模型，结构级泄漏为 0。")
    else:
        P("**警告**：仍有 %d 组跨划分，需要检查划分逻辑。" % cross)
    P()

    with open(os.path.join(out_dir, "split_report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    print("已写出 %s" % os.path.join(out_dir, "split_report.md"))

    # ---- 5. 半监督有标签/无标签子集 ----
    if args.ratio_subsets:
        train_ids = sorted(generated["train"])
        cls_of = {}
        for s in train_ids:
            cs = {int(c) for c in kept[s]["class_face_counts"].keys()
                  if int(c) not in BACKGROUND_CLASSES}
            cls_of[s] = cs
        ratios_l = [float(x) for x in args.ratio_subsets.split(",")]
        R = []
        R.append("# 半监督「有标签比例」子集")
        R.append("")
        R.append("协议：数据池固定 = 训练集全体（%d 个模型）；无标签池 = 训练集减去有标签子集；"
                 "不额外生成无标签数据。有标签子集按比例**随机**抽取（随机种子 %d），"
                 "并加一层「每个加工特征类至少 1 个模型」的覆盖保证；"
                 "子集大小严格等于 round(比例 x 训练集大小)，不因覆盖保证而改变规模。"
                 % (len(train_ids), args.ratio_seed))
        R.append("")
        R.append("| 有标签比例 | 有标签模型数 | 无标签模型数 | 缺席类别数 | 最小类模型数 |")
        R.append("|---|---|---|---|---|")
        detail = {}
        for r in ratios_l:
            rng = random.Random(args.ratio_seed)
            sub = stratified_sample(train_ids, cls_of, r, rng, range(N_FEATURE_CLASSES))
            rest = [s for s in train_ids if s not in set(sub)]
            tag = "r%03d" % int(round(r * 100))
            with open(os.path.join(out_dir, "labeled_%s.txt" % tag), "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(sorted(sub, key=lambda x: (len(x), x))) + "\n")
            with open(os.path.join(out_dir, "unlabeled_%s.txt" % tag), "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(sorted(rest, key=lambda x: (len(x), x))) + "\n")
            c2 = Counter()
            for s in sub:
                c2.update(cls_of[s])
            zero = sum(1 for c in range(N_FEATURE_CLASSES) if c2.get(c, 0) == 0)
            mn = min(c2.get(c, 0) for c in range(N_FEATURE_CLASSES))
            R.append("| %g%% | %d | %d | %d | %d |" % (r * 100, len(sub), len(rest), zero, mn))
            detail[r] = c2
        R.append("")
        R.append("## 各比例下每类有标签模型数")
        R.append("")
        R.append("| 类 | 名称 | " + " | ".join("%g%%" % (r * 100) for r in ratios_l) + " |")
        R.append("|---" * (2 + len(ratios_l)) + "|")
        for c in range(N_FEATURE_CLASSES):
            nm = names_tbl[c] if c < len(names_tbl) else "?"
            R.append("| %d | %s | " % (c, nm)
                     + " | ".join(str(detail[r].get(c, 0)) for r in ratios_l) + " |")
        R.append("")
        with open(os.path.join(out_dir, "ratio_report.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(R) + "\n")
        print("已写出 %s" % os.path.join(out_dir, "ratio_report.md"))

    print("完成。")


# 与 Utils/parameters.py 的 feat_names 一致
FEATURE_NAMES = [
    "chamfer", "through_hole", "triangular_passage", "rectangular_passage",
    "6sides_passage", "triangular_through_slot", "rectangular_through_slot",
    "circular_through_slot", "rectangular_through_step", "2sides_through_step",
    "slanted_through_step", "Oring", "blind_hole", "triangular_pocket",
    "rectangular_pocket", "6sides_pocket", "circular_end_pocket",
    "rectangular_blind_slot", "v_circular_end_blind_slot", "h_circular_end_blind_slot",
    "triangular_blind_step", "circular_blind_step", "rectangular_blind_step",
    "round", "counterbore", "countersunk_hole", "variable_round",
    "plane", "cylinder", "cone",
]


if __name__ == "__main__":
    main()
