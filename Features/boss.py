import random
import math

import numpy as np

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.gp import gp_Circ, gp_Ax2, gp_Pnt, gp_Dir

import Utils.occ_utils as occ_utils
from Features.machining_features import AdditiveFeature


class Boss(AdditiveFeature):
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = "blind"
        self.feat_type = "boss"

    def _add_sketch(self, bound):
        dir_w = bound[2] - bound[1]
        dir_h = bound[0] - bound[1]
        width = np.linalg.norm(dir_w)
        height = np.linalg.norm(dir_h)

        if width <= 0 or height <= 0:
            return None

        dir_w = dir_w / width
        dir_h = dir_h / height
        normal = np.cross(dir_w, dir_h)

        max_radius = min(width / 2.0, height / 2.0)
        if max_radius <= 0:
            return None

        r_min = self.min_len / 2.0
        r_max = max_radius - self.clearance
        if r_max <= r_min:
            radius = r_min
        else:
            radius = random.uniform(r_min, r_max)

        center = (bound[0] + bound[1] + bound[2] + bound[3]) / 4.0

        axis = gp_Ax2(gp_Pnt(center[0], center[1], center[2]), occ_utils.as_occ(normal, gp_Dir))

        circ = gp_Circ(axis, radius)
        edge = BRepBuilderAPI_MakeEdge(circ, 0.0, 2.0 * math.pi).Edge()
        outer_wire = BRepBuilderAPI_MakeWire(edge).Wire()

        face_maker = BRepBuilderAPI_MakeFace(outer_wire)

        return face_maker.Face()
