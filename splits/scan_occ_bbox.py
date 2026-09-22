#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量 OCC 包围盒扫描：给每个模型算出真实 BRep 包围盒，用于剔除「归一化会失效」的模型。

背景
----
multi_StepToBin.normalize_shape 用 `Bnd_Box` + `brepbndlib.Add(shape, box)` 取包围盒，
再按最长边缩放到 2.0。但对含 BSpline（圆角/过渡）面的模型，`brepbndlib.Add` 会按
**控制极点**估算包围盒，实测最大高估 167 倍（9066 mm vs 真实 54 mm），
导致这些模型在 bin 里被压成一个点。

本脚本对每个 STEP 同时记录：
  - add_extent      ：brepbndlib.Add 的包围盒最长边（复现 multi_StepToBin 的现有行为）
  - optimal_extent  ：brepbndlib.AddOptimal 的包围盒最长边（真实几何）
  - n_faces

判据：毛坯 x/y/z 各 uniform(10,50) mm，加工特征只做材料去除，不会超出毛坯。
因此任何 optimal_extent > 100 mm 的模型都属异常，应从数据集中剔除（或修正预处理）。

输出：_occ_bbox_scan.csv
"""
import os
import sys
import time
from multiprocessing import Pool, cpu_count

ROOT = r"C:\Users\MR\Desktop\论文代码\ReferenceDataset\myNewDatasets\steps"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_occ_bbox_scan.csv")

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE


def extent(box):
    if box.IsVoid():
        return None
    x0, y0, z0, x1, y1, z1 = box.Get()
    return max(x1 - x0, y1 - y0, z1 - z0)


def work(fn):
    mid = fn[:-5] if fn.lower().endswith(".step") else fn
    path = os.path.join(ROOT, fn)
    try:
        r = STEPControl_Reader()
        if r.ReadFile(path) != IFSelect_RetDone:
            return (mid, "read_failed", -1.0, -1.0, -1)
        r.TransferRoots()
        s = r.OneShape()

        b1 = Bnd_Box()
        brepbndlib.Add(s, b1)
        e1 = extent(b1)

        b2 = Bnd_Box()
        try:
            brepbndlib.AddOptimal(s, b2, True, False)
        except TypeError:
            brepbndlib.AddOptimal(s, b2)
        e2 = extent(b2)

        nf = 0
        ex = TopExp_Explorer(s, TopAbs_FACE)
        while ex.More():
            nf += 1
            ex.Next()
        return (mid, "ok", -1.0 if e1 is None else e1, -1.0 if e2 is None else e2, nf)
    except Exception as e:
        return (mid, "exception:" + type(e).__name__, -1.0, -1.0, -1)


if __name__ == "__main__":
    files = sorted(f for f in os.listdir(ROOT) if f.lower().endswith(".step"))
    print("step files:", len(files), flush=True)
    nw = int(os.environ.get("SCAN_WORKERS", "6"))
    t0 = time.time()
    rows = []
    with Pool(nw) as pool:
        for i, r in enumerate(pool.imap_unordered(work, files, chunksize=16)):
            rows.append(r)
            if (i + 1) % 3000 == 0:
                el = time.time() - t0
                print("  %d/%d  %.0fs  eta %.0fs" % (i + 1, len(files), el,
                      el / (i + 1) * (len(files) - i - 1)), flush=True)
    rows.sort(key=lambda r: r[0])
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("id,status,add_extent,optimal_extent,n_faces\n")
        for r in rows:
            f.write("%s,%s,%.4f,%.4f,%d\n" % r)
    print("done in %.0fs -> %s" % (time.time() - t0, OUT), flush=True)

    bad = [r for r in rows if r[1] == "ok" and r[3] > 100]
    print("optimal_extent > 100mm : %d" % len(bad), flush=True)
    bad2 = [r for r in rows if r[1] == "ok" and r[2] > 100]
    print("add_extent     > 100mm : %d" % len(bad2), flush=True)
    print("status counts:", flush=True)
    from collections import Counter
    print(Counter(r[1].split(":")[0] for r in rows), flush=True)
