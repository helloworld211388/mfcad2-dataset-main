import random
import math
import numpy as np

from OCC.Core.BRepFeat import BRepFeat_MakePrism
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCC.Core.TopoDS import TopoDS_Face
from OCC.Core.gp import gp_Circ, gp_Ax2, gp_Pnt, gp_Dir, gp_Vec, gp_Dir2d, gp_Pnt2d, gp_Ax2d, gp_Ax3
from OCC.Core.Geom import Geom_CylindricalSurface
from OCC.Core.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve
from OCC.Core.GCE2d import GCE2d_MakeSegment
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCC.Core.BRepLib import breplib_BuildCurves3d

import Utils.occ_utils as occ_utils
import Utils.parameters as param
import Utils.shape_factory as shape_factory
from Features.machining_features import AdditiveFeature
from Utils.thread_utils import create_thread_solid


class Stud(AdditiveFeature):
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = "blind"
        self.feat_type = "stud"
        self.thread_axis = None
        self.r_major = None
        self.r_groove = None

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

        r_major = max(self.min_len / 2.0, max_radius - self.clearance)
        if r_major <= 0:
            return None

        scale = random.uniform(param.thread_profile_scale_min, param.thread_profile_scale_max)
        r_groove = r_major * scale
        if r_groove <= 0:
            return None

        center = (bound[0] + bound[1] + bound[2] + bound[3]) / 4.0
        axis = gp_Ax2(gp_Pnt(center[0], center[1], center[2]), occ_utils.as_occ(normal, gp_Dir))

        self.thread_axis = axis
        self.r_major = r_major
        self.r_groove = r_groove

        circ = gp_Circ(axis, r_major)
        edge = BRepBuilderAPI_MakeEdge(circ, 0.0, 2.0 * math.pi).Edge()
        outer_wire = BRepBuilderAPI_MakeWire(edge).Wire()

        face_maker = BRepBuilderAPI_MakeFace(outer_wire)
        return face_maker.Face()

    @staticmethod
    def _merge_label_map(old_map, old_shape, new_shape, feat_idx):
        new_labels = {}
        old_faces = occ_utils.list_face(old_shape)
        new_faces = occ_utils.list_face(new_shape)

        for of in old_faces:
            same = shape_factory.same_shape_in_list(of, new_faces)
            if same is not None:
                new_labels[same] = old_map.get(of, feat_idx)
                new_faces.remove(same)

        for nf in new_faces:
            new_labels[nf] = feat_idx

        return new_labels

    def _apply_feature(self, old_shape, old_labels, feat_type, feat_face, depth_dir):
        feature_maker = BRepFeat_MakePrism()
        feature_maker.Init(old_shape, feat_face, TopoDS_Face(), occ_utils.as_occ(-depth_dir, gp_Dir), True, False)
        feature_maker.Build()

        depth = np.linalg.norm(depth_dir)
        feature_maker.Perform(depth)
        shape = feature_maker.Shape()

        fmap = shape_factory.map_face_before_and_after_feat(old_shape, feature_maker)
        base_labels = shape_factory.map_from_shape_and_name(fmap, old_labels, shape, self.feat_names.index(self.feat_type))

        if depth <= 0 or self.thread_axis is None or self.r_major is None or self.r_groove is None:
            return shape, base_labels

        try:
            base_radius = self.r_major
            if base_radius <= 0:
                return shape, base_labels

            inner_radius = max(self.r_groove, base_radius * 0.85) * 0.99
            outer_radius = base_radius * 1.02
            if inner_radius <= 0 or outer_radius <= inner_radius:
                return shape, base_labels

            ax3 = gp_Ax3(self.thread_axis.Location(), self.thread_axis.Direction())

            cyl1 = Geom_CylindricalSurface(ax3, inner_radius)
            cyl2 = Geom_CylindricalSurface(ax3, outer_radius)

            thread_height = depth
            if thread_height <= 0:
                return shape, base_labels

            base_pitch = max(self.min_len * 0.8, 1.0)
            turns = max(3, int(thread_height / base_pitch))

            du = 2.0 * math.pi * turns
            dv = thread_height

            base_pnt = gp_Pnt2d(0.0, 0.0)
            base_dir = gp_Dir2d(du, dv)
            line2d = Geom2d_Line(base_pnt, base_dir)

            line_param_len = math.sqrt(du * du + dv * dv)

            helix_curve = Geom2d_TrimmedCurve(line2d, 0.0, line_param_len)

            ep_start = line2d.Value(0.0)
            ep_end = line2d.Value(line_param_len)
            segment = GCE2d_MakeSegment(ep_end, ep_start).Value()

            edge1_s1 = BRepBuilderAPI_MakeEdge(helix_curve, cyl1).Edge()
            edge2_s1 = BRepBuilderAPI_MakeEdge(segment, cyl1).Edge()
            edge1_s2 = BRepBuilderAPI_MakeEdge(helix_curve, cyl2).Edge()
            edge2_s2 = BRepBuilderAPI_MakeEdge(segment, cyl2).Edge()

            wire1 = BRepBuilderAPI_MakeWire(edge1_s1, edge2_s1).Wire()
            wire2 = BRepBuilderAPI_MakeWire(edge1_s2, edge2_s2).Wire()

            breplib_BuildCurves3d(wire1)
            breplib_BuildCurves3d(wire2)

            tool = BRepOffsetAPI_ThruSections(True)
            tool.AddWire(wire1)
            tool.AddWire(wire2)
            tool.CheckCompatibility(False)
            thread_solid = tool.Shape()

            thread_solid = create_thread_solid(self.thread_axis, self.r_major, depth)

            if thread_solid.IsNull():
                print("Error: stud thread_solid is Null")
                return shape, base_labels


            threaded_shape = BRepAlgoAPI_Fuse(shape, thread_solid).Shape()

            if threaded_shape.IsNull():
                print("Error: stud threaded_shape is Null")
                return shape, base_labels

            new_labels = self._merge_label_map(base_labels, shape, threaded_shape, self.feat_names.index(self.feat_type))
            return threaded_shape, new_labels
        except Exception as e:
            print(f"Stud thread generation failed: {e}")
            return shape, base_labels
