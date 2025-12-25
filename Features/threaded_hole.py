import random
import math
import numpy as np

from OCC.Core.BRepFeat import BRepFeat_MakePrism
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
from OCC.Core.TopoDS import TopoDS_Face
from OCC.Core.gp import gp_Circ, gp_Ax2, gp_Pnt, gp_Dir, gp_Vec, gp_Dir2d
from OCC.Core.Geom import Geom_CylindricalSurface
from OCC.Core.Geom2d import Geom2d_Line, Geom2d_TrimmedCurve, Geom2d_Ellipse
from OCC.Core.GCE2d import GCE2d_MakeSegment
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_MakePipe, BRepOffsetAPI_MakePipeShell, BRepOffsetAPI_ThruSections
from OCC.Core.gp import gp_Ax3, gp_Pnt2d, gp_Pln, gp_Ax2d
from OCC.Core.BRepLib import breplib_BuildCurves3d

import Utils.occ_utils as occ_utils
import Utils.parameters as param
import Utils.shape_factory as shape_factory
from Features.machining_features import MachiningFeature
from Utils.thread_utils import create_thread_solid


class ThreadedHole(MachiningFeature):
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = random.choice(["through", "blind"])
        self.feat_type = "threaded_hole"

        self.thread_axis = None
        self.r_major = None
        self.r_minor = None

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

        available_r = min(width, height) / 2.0
        if available_r <= 0:
            return None

        r_major = max(self.min_len / 2.0, available_r - self.clearance)
        if r_major <= 0:
            return None

        scale = random.uniform(param.thread_profile_scale_min, param.thread_profile_scale_max)
        r_minor = r_major * scale
        if r_minor <= 0:
            return None

        center = (bound[0] + bound[1] + bound[2] + bound[3]) / 4.0
        axis = gp_Ax2(gp_Pnt(center[0], center[1], center[2]), occ_utils.as_occ(normal, gp_Dir))

        self.thread_axis = axis
        self.r_major = r_major
        self.r_minor = r_minor

        circ = gp_Circ(axis, r_minor)
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
        feature_maker.Init(old_shape, feat_face, TopoDS_Face(), occ_utils.as_occ(depth_dir, gp_Dir), False, False)
        feature_maker.Build()

        depth = np.linalg.norm(depth_dir)
        feature_maker.Perform(depth)
        shape = feature_maker.Shape()

        fmap = shape_factory.map_face_before_and_after_feat(old_shape, feature_maker)
        base_labels = shape_factory.map_from_shape_and_name(fmap, old_labels, shape, self.feat_names.index(self.feat_type))

        if depth <= 0 or self.thread_axis is None or self.r_major is None or self.r_minor is None:
            return shape, base_labels

        try:
            # New logic
            thread_solid = create_thread_solid(self.thread_axis, self.r_minor, depth)

            if thread_solid.IsNull():
                print("Error: thread_solid is Null")
                return shape, base_labels

            threaded_shape = BRepAlgoAPI_Cut(shape, thread_solid).Shape()
            new_labels = self._merge_label_map(base_labels, shape, threaded_shape, self.feat_names.index(self.feat_type))
            return threaded_shape, new_labels
        except Exception as e:
            print(f"Thread generation failed: {e}")
            return shape, base_labels
