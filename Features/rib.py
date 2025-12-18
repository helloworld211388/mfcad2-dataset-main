import random

import numpy as np

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.gp import gp_Pnt

import Utils.occ_utils as occ_utils
from Features.machining_features import AdditiveFeature


class Rib(AdditiveFeature):
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = "blind"
        self.feat_type = "rib"

    def _add_sketch(self, bound):
        p0 = np.asarray(bound[0])
        p1 = np.asarray(bound[1])
        p2 = np.asarray(bound[2])

        dir_w = p2 - p1
        dir_h = p0 - p1
        width = np.linalg.norm(dir_w)
        height = np.linalg.norm(dir_h)

        if width <= 0 or height <= 0:
            return None

        if width >= height:
            long_dir = dir_w / width
            short_dir = dir_h / height
            long_len = width
            short_len = height
        else:
            long_dir = dir_h / height
            short_dir = dir_w / width
            long_len = height
            short_len = width

        margin = self.clearance
        usable_long = long_len - 2.0 * margin
        usable_short = short_len - 2.0 * margin

        if usable_long <= self.min_len or usable_short <= self.min_len:
            return None

        max_thick = min(usable_short, 2.0 * self.min_len)
        if max_thick <= self.min_len:
            thickness = usable_short
        else:
            thickness = random.uniform(self.min_len, max_thick)

        base_start = margin
        base_end = margin + usable_long

        origin = p1

        a = origin + long_dir * base_start + short_dir * margin
        b = origin + long_dir * base_end + short_dir * margin
        c = origin + long_dir * (0.5 * (base_start + base_end)) + short_dir * (margin + thickness)

        pa = occ_utils.as_occ(a.tolist(), gp_Pnt)
        pb = occ_utils.as_occ(b.tolist(), gp_Pnt)
        pc = occ_utils.as_occ(c.tolist(), gp_Pnt)

        e1 = BRepBuilderAPI_MakeEdge(pa, pb).Edge()
        e2 = BRepBuilderAPI_MakeEdge(pb, pc).Edge()
        e3 = BRepBuilderAPI_MakeEdge(pc, pa).Edge()

        wire = BRepBuilderAPI_MakeWire(e1, e2, e3).Wire()

        return BRepBuilderAPI_MakeFace(wire).Face()
