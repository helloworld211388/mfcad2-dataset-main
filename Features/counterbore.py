import random
import math

import numpy as np

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.gp import gp_Circ, gp_Ax2, gp_Pnt, gp_Dir
from OCC.Extend.TopologyUtils import TopologyExplorer

import Utils.occ_utils as occ_utils
from Features.machining_features import MachiningFeature


class Counterbore(MachiningFeature):
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = "through"
        self.feat_type = "counterbore"

    def _circle_faces(self, bound):
        dir_w = bound[2] - bound[1]
        dir_h = bound[0] - bound[1]
        width = np.linalg.norm(dir_w)
        height = np.linalg.norm(dir_h)

        if width <= 0 or height <= 0:
            return None, None

        dir_w = dir_w / width
        dir_h = dir_h / height
        normal = np.cross(dir_w, dir_h)

        max_radius = min(width / 2.0, height / 2.0)
        if max_radius <= 0:
            return None, None

        r_inner_min = self.min_len / 2.0
        r_inner_max = max_radius - self.clearance

        if r_inner_max <= r_inner_min:
            return None, None

        r_inner = random.uniform(r_inner_min, r_inner_max)

        r_outer_min = r_inner + self.clearance
        r_outer_max = max_radius

        if r_outer_max <= r_outer_min:
            r_outer = r_outer_min
        else:
            r_outer = random.uniform(r_outer_min, r_outer_max)

        center = (bound[0] + bound[1] + bound[2] + bound[3]) / 4.0

        axis = gp_Ax2(gp_Pnt(center[0], center[1], center[2]), occ_utils.as_occ(normal, gp_Dir))

        circ_inner = gp_Circ(axis, r_inner)
        edge_inner = BRepBuilderAPI_MakeEdge(circ_inner, 0.0, 2.0 * math.pi).Edge()
        wire_inner = BRepBuilderAPI_MakeWire(edge_inner).Wire()
        face_inner = BRepBuilderAPI_MakeFace(wire_inner).Face()

        circ_outer = gp_Circ(axis, r_outer)
        edge_outer = BRepBuilderAPI_MakeEdge(circ_outer, 0.0, 2.0 * math.pi).Edge()
        wire_outer = BRepBuilderAPI_MakeWire(edge_outer).Wire()
        face_outer = BRepBuilderAPI_MakeFace(wire_outer).Face()

        return face_inner, face_outer

    def add_feature(self, bounds, find_bounds=True):
        try:
            if find_bounds is True:
                self._get_bounds()
            else:
                self.bounds = bounds

            if len(self.bounds) < 1:
                return self.shape, self.label_map, self.bounds

            faces = occ_utils.list_face(self.shape)
            triangles = self._triangles_from_faces(faces)

            random.shuffle(self.bounds)

            feat_face_inner = None
            feat_face_outer = None
            depth_through = 0.0
            depth_cb = 0.0

            try_cnt = 0
            while try_cnt < len(self.bounds):
                bound_max = random.choice(self.bounds)
                bound_max = self._shifter(bound_max)

                depth_through = self._depth_through()
                depth_blind_max = self._depth_blind(bound_max, triangles)

                if depth_through <= 0 or depth_blind_max <= 0:
                    try_cnt += 1
                    continue

                max_cb = min(depth_blind_max, depth_through - self.min_len - self.clearance)
                if max_cb <= self.min_len:
                    try_cnt += 1
                    continue

                depth_cb = random.uniform(self.min_len, max_cb)

                feat_face_inner, feat_face_outer = self._circle_faces(bound_max)
                if feat_face_inner is None or feat_face_outer is None:
                    try_cnt += 1
                    continue

                break

        except Exception as e:
            print(e)
            return self.shape, self.label_map, bounds

        if feat_face_inner is None or feat_face_outer is None:
            return self.shape, self.label_map, bounds

        try:
            shape, label_map = self._apply_feature(self.shape, self.label_map, self.feat_type,
                                                   feat_face_inner, bound_max[4] * depth_through, bound_max)

            shape, label_map = self._apply_feature(shape, label_map, self.feat_type,
                                                   feat_face_outer, bound_max[4] * depth_cb, bound_max)
        except Exception as e:
            print(e)
            return self.shape, self.label_map, bounds

        topo = TopologyExplorer(shape)
        if topo.number_of_solids() > 1:
            return self.shape, self.label_map, bounds

        return shape, label_map, self.bounds
