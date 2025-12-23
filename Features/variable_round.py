import random

from OCC.Core.BRepFilletAPI import BRepFilletAPI_MakeFillet

import Utils.shape_factory as shape_factory
import Utils.parameters as param
from Features.machining_features import MachiningFeature

import OCCUtils.edge


def _edge_radius_range(edge_length):
    max_radius = edge_length / 5.0
    if max_radius > param.variable_round_radius_max:
        max_radius = param.variable_round_radius_max
    return param.variable_round_radius_min, max_radius


class VariableRound(MachiningFeature):
    def __init__(self, shape, label_map, min_len, clearance, feat_names, edges):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = None
        self.bound_type = None
        self.depth_type = None
        self.feat_type = "variable_round"
        self.edges = edges

    def add_feature(self):
        fillet_maker = BRepFilletAPI_MakeFillet(self.shape)
        usable_edges = []

        for edge in self.edges:
            e_util = OCCUtils.edge.Edge(edge)
            if e_util.length() >= self.min_len:
                usable_edges.append(edge)

        self.edges = usable_edges

        while len(self.edges) > 0:
            edge = random.choice(self.edges)
            e_util = OCCUtils.edge.Edge(edge)
            rmin, rmax = _edge_radius_range(e_util.length())
            if rmax <= rmin:
                self.edges.remove(edge)
                continue

            r1 = random.uniform(rmin, rmax)
            r2 = random.uniform(rmin, rmax)
            if abs(r1 - r2) < 1e-6:
                r2 = min(rmax, r1 + rmin)

            try:
                fillet_maker.Add(edge)
                fillet_maker.SetRadius(r1, r2, edge)
                shape = fillet_maker.Shape()
                self.edges.remove(edge)
                break
            except Exception:
                self.edges.remove(edge)
                continue

        try:
            fmap = shape_factory.map_face_before_and_after_feat(self.shape, fillet_maker)
            label_map = shape_factory.map_from_shape_and_name(
                fmap, self.label_map, shape, self.feat_names.index(self.feat_type)
            )
            return shape, label_map, self.edges
        except Exception:
            return self.shape, self.label_map, self.edges
