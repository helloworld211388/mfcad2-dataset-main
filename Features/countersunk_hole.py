import random
import math

import numpy as np

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCone
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.gp import gp_Circ, gp_Ax2, gp_Pnt, gp_Dir
from OCC.Extend.TopologyUtils import TopologyExplorer

import Utils.occ_utils as occ_utils
import Utils.shape_factory as shape_factory
from Features.machining_features import MachiningFeature


class CountersunkHole(MachiningFeature):
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = "through"
        self.feat_type = "countersunk_hole"

    def _compute_radii_and_center(self, bound):
        p0 = np.asarray(bound[0])
        p1 = np.asarray(bound[1])
        p2 = np.asarray(bound[2])
        p3 = np.asarray(bound[3])

        dir_w = p2 - p1
        dir_h = p0 - p1
        width = np.linalg.norm(dir_w)
        height = np.linalg.norm(dir_h)

        if width <= 0 or height <= 0:
            return None

        max_radius = min(width, height) / 2.0
        if max_radius <= 0:
            return None

        r_inner_min = self.min_len / 2.0
        r_inner_max = max_radius - self.clearance
        if r_inner_max <= r_inner_min:
            return None

        r_inner = random.uniform(r_inner_min, r_inner_max)

        r_outer_min = r_inner + self.clearance
        r_outer_max = max_radius
        if r_outer_max <= r_outer_min:
            r_outer = r_outer_min
        else:
            r_outer = random.uniform(r_outer_min, r_outer_max)

        center = (p0 + p1 + p2 + p3) / 4.0
        surf_normal = -np.asarray(bound[4])

        return center, surf_normal, r_inner, r_outer

    def _make_circle_face(self, center, normal, radius):
        axis = gp_Ax2(gp_Pnt(center[0], center[1], center[2]), occ_utils.as_occ(normal.tolist(), gp_Dir))
        circ = gp_Circ(axis, radius)
        edge = BRepBuilderAPI_MakeEdge(circ, 0.0, 2.0 * math.pi).Edge()
        wire = BRepBuilderAPI_MakeWire(edge).Wire()
        return BRepBuilderAPI_MakeFace(wire).Face()

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

            feat_face_cyl = None
            center = None
            surf_normal = None
            r_inner = 0.0
            r_outer = 0.0
            depth_through = 0.0
            cs_height = 0.0

            try_cnt = 0
            while try_cnt < len(self.bounds):
                bound_max = random.choice(self.bounds)
                bound_max = self._shifter(bound_max)

                params = self._compute_radii_and_center(bound_max)
                if params is None:
                    try_cnt += 1
                    continue

                center, surf_normal, r_inner, r_outer = params

                depth_through = self._depth_through()
                depth_blind_max = self._depth_blind(bound_max, triangles)

                if depth_through <= 0 or depth_blind_max <= 0:
                    try_cnt += 1
                    continue

                max_height = min(depth_blind_max, depth_through - self.min_len - self.clearance)
                if max_height <= self.min_len:
                    try_cnt += 1
                    continue

                cs_height = random.uniform(self.min_len, max_height)

                feat_face_cyl = self._make_circle_face(center, surf_normal, r_inner)
                if feat_face_cyl is None:
                    try_cnt += 1
                    continue

                break

        except Exception as e:
            print(e)
            return self.shape, self.label_map, bounds

        if feat_face_cyl is None:
            return self.shape, self.label_map, bounds

        try:
            # Step 1: cylindrical through-hole
            shape, label_map = self._apply_feature(self.shape, self.label_map, self.feat_type,
                                                   feat_face_cyl, bound_max[4] * depth_through)

            # Step 2: conical countersink cut
            axis_cone = gp_Ax2(gp_Pnt(center[0], center[1], center[2]),
                               occ_utils.as_occ(bound_max[4].tolist(), gp_Dir))
            cone_maker = BRepPrimAPI_MakeCone(axis_cone, r_outer, r_inner, cs_height)
            cone_shape = cone_maker.Shape()

            cut_maker = BRepAlgoAPI_Cut(shape, cone_shape)
            cut_maker.Build()

            shape2 = cut_maker.Shape()

            fmap = shape_factory.map_face_before_and_after_feat(shape, cut_maker)
            label_map2 = shape_factory.map_from_shape_and_name(fmap, label_map, shape2,
                                                               self.feat_names.index(self.feat_type))
        except Exception as e:
            print(e)
            return self.shape, self.label_map, bounds

        topo = TopologyExplorer(shape2)
        if topo.number_of_solids() > 1:
            return self.shape, self.label_map, bounds

        return shape2, label_map2, self.bounds
