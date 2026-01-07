import random

from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeEdge
from OCC.Core.gp import gp_Pnt
from OCC.Extend.TopologyUtils import TopologyExplorer

import Utils.shape_factory as shape_factory
import Utils.parameters as param
import Utils.occ_utils as occ_utils

from Features.o_ring import ORing
from Features.through_hole import ThroughHole
from Features.round import Round
from Features.chamfer import Chamfer
from Features.triangular_passage import TriangularPassage
from Features.rectangular_passage import RectangularPassage
from Features.six_sides_passage import SixSidesPassage
from Features.triangular_through_slot import TriangularThroughSlot
from Features.rectangular_through_slot import RectangularThroughSlot
from Features.circular_through_slot import CircularThroughSlot
from Features.rectangular_through_step import RectangularThroughStep
from Features.two_sides_through_step import TwoSidesThroughStep
from Features.slanted_through_step import SlantedThroughStep
from Features.blind_hole import BlindHole
from Features.triangular_pocket import TriangularPocket
from Features.rectangular_pocket import RectangularPocket
from Features.six_sides_pocket import SixSidesPocket
from Features.circular_end_pocket import CircularEndPocket
from Features.rectangular_blind_slot import RectangularBlindSlot
from Features.v_circular_end_blind_slot import VCircularEndBlindSlot
from Features.h_circular_end_blind_slot import HCircularEndBlindSlot
from Features.triangular_blind_step import TriangularBlindStep
from Features.circular_blind_step import CircularBlindStep
from Features.rectangular_blind_step import RectangularBlindStep
from Features.counterbore import Counterbore
from Features.countersunk_hole import CountersunkHole
from Features.variable_round import VariableRound

feat_names = ['chamfer', 'through_hole', 'triangular_passage', 'rectangular_passage', '6sides_passage',
              'triangular_through_slot', 'rectangular_through_slot', 'circular_through_slot',
              'rectangular_through_step', '2sides_through_step', 'slanted_through_step', 'Oring', 'blind_hole',
              'triangular_pocket', 'rectangular_pocket', '6sides_pocket', 'circular_end_pocket',
              'rectangular_blind_slot', 'v_circular_end_blind_slot', 'h_circular_end_blind_slot',
              'triangular_blind_step', 'circular_blind_step', 'rectangular_blind_step', 'round',
              'counterbore', 'countersunk_hole', 'variable_round',
              'stock']

feat_classes = {"chamfer": Chamfer, "through_hole": ThroughHole, "triangular_passage": TriangularPassage,
                "rectangular_passage": RectangularPassage, "6sides_passage": SixSidesPassage,
                "triangular_through_slot": TriangularThroughSlot, "rectangular_through_slot": RectangularThroughSlot,
                "circular_through_slot": CircularThroughSlot, "rectangular_through_step": RectangularThroughStep,
                "2sides_through_step": TwoSidesThroughStep, "slanted_through_step": SlantedThroughStep, "Oring": ORing,
                "blind_hole": BlindHole, "triangular_pocket": TriangularPocket, "rectangular_pocket": RectangularPocket,
                "6sides_pocket": SixSidesPocket, "circular_end_pocket": CircularEndPocket,
                "rectangular_blind_slot": RectangularBlindSlot, "v_circular_end_blind_slot": VCircularEndBlindSlot,
                "h_circular_end_blind_slot": HCircularEndBlindSlot, "triangular_blind_step": TriangularBlindStep,
                "circular_blind_step": CircularBlindStep, "rectangular_blind_step": RectangularBlindStep,
                "round": Round, "counterbore": Counterbore,
                "countersunk_hole": CountersunkHole,
                "variable_round": VariableRound}

through_blind_features = ["triangular_passage", "rectangular_passage", "6sides_passage", "triangular_pocket",
                          "rectangular_pocket", "6sides_pocket", "through_hole", "blind_hole", "circular_end_pocket",
                          "Oring", "counterbore", "countersunk_hole"]


def triangulate_shape(shape):
    linear_deflection = 0.1
    angular_deflection = 0.5
    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection, True)
    mesh.Perform()
    assert mesh.IsDone()


def generate_stock_dims():
    param.stock_dim_x = random.uniform(param.stock_min_x, param.stock_max_x)
    param.stock_dim_y = random.uniform(param.stock_min_y, param.stock_max_y)
    param.stock_dim_z = random.uniform(param.stock_min_z, param.stock_max_z)


def rearrange_combo(combination):
    transition_feats = []
    step_feats = []
    slot_feats = []
    through_feats = []
    blind_feats = []
    o_ring_feats = []

    for cnt, val in enumerate(combination):
        if val == param.feat_names.index("chamfer") or val == param.feat_names.index("round") \
                or val == param.feat_names.index("variable_round"):
            transition_feats.append(val)
        elif val == param.feat_names.index("rectangular_through_step") \
                or val == param.feat_names.index("2sides_through_step") \
                or val == param.feat_names.index("slanted_through_step") \
                or val == param.feat_names.index("triangular_blind_step") \
                or val == param.feat_names.index("circular_blind_step") \
                or val == param.feat_names.index("rectangular_blind_step"):
            step_feats.append(val)

        elif val == param.feat_names.index("triangular_through_slot") \
                or val == param.feat_names.index("rectangular_through_slot") \
                or val == param.feat_names.index("circular_through_slot") \
                or val == param.feat_names.index("rectangular_blind_slot") \
                or val == param.feat_names.index("v_circular_end_blind_slot") \
                or val == param.feat_names.index("h_circular_end_blind_slot"):
            slot_feats.append(val)

        elif val == param.feat_names.index("through_hole") \
                or val == param.feat_names.index("triangular_passage") \
                or val == param.feat_names.index("rectangular_passage") \
                or val == param.feat_names.index("6sides_passage"):
            through_feats.append(val)

        elif val == param.feat_names.index("blind_hole") \
                or val == param.feat_names.index("triangular_pocket") \
                or val == param.feat_names.index("rectangular_pocket") \
                or val == param.feat_names.index("6sides_pocket") \
                or val == param.feat_names.index("circular_end_pocket") \
                or val == param.feat_names.index("counterbore") \
                or val == param.feat_names.index("countersunk_hole"):
            blind_feats.append(val)

        elif val == param.feat_names.index("Oring"):
            o_ring_feats.append(val)

    new_combination = step_feats + slot_feats + through_feats + blind_feats + o_ring_feats + transition_feats

    return new_combination


def rearrange_combo_planar(combination):
    transition_feats = []
    step_feats = []
    slot_feats = []
    through_feats = []
    blind_feats = []

    for cnt, val in enumerate(combination):
        if val == param.feat_names.index("chamfer"):
            transition_feats.append(val)
        elif val == param.feat_names.index("rectangular_through_step") \
                or val == param.feat_names.index("2sides_through_step") \
                or val == param.feat_names.index("slanted_through_step") \
                or val == param.feat_names.index("triangular_blind_step") \
                or val == param.feat_names.index("rectangular_blind_step"):
            step_feats.append(val)

        elif val == param.feat_names.index("triangular_through_slot") \
                or val == param.feat_names.index("rectangular_through_slot") \
                or val == param.feat_names.index("rectangular_blind_slot"):
            slot_feats.append(val)

        elif val == param.feat_names.index("triangular_passage") \
                or val == param.feat_names.index("rectangular_passage") \
                or val == param.feat_names.index("6sides_passage"):
            through_feats.append(val)
        elif val == param.feat_names.index("triangular_pocket") \
                or val == param.feat_names.index("rectangular_pocket") \
                or val == param.feat_names.index("6sides_pocket"):
            blind_feats.append(val)

    new_combination = step_feats + slot_feats + through_feats + blind_feats + transition_feats

    return new_combination


def shape_from_directive(combo):
    try_cnt = 0
    find_edges = True
    combo = rearrange_combo(combo)
    count = 0
    bounds = []

    while True:
        generate_stock_dims()
        shape = BRepPrimAPI_MakeBox(param.stock_dim_x, param.stock_dim_y, param.stock_dim_z).Shape()
        label_map = shape_factory.map_from_name(shape, param.feat_names.index('stock'))

        for fid in combo:
            feat_name = param.feat_names[fid]
            if fid == param.feat_names.index("chamfer"):
                edges = occ_utils.list_edge(shape)
                new_feat = feat_classes[feat_name](shape, label_map, param.min_len,
                                                   param.clearance, param.feat_names, edges)
                shape, label_map, edges = new_feat.add_feature()

                if len(edges) == 0:
                    break

            elif fid == param.feat_names.index("round") or fid == param.feat_names.index("variable_round"):
                if find_edges:
                    edges = occ_utils.list_edge(shape)
                    find_edges = False

                new_feat = feat_classes[feat_name](shape, label_map, param.min_len,
                                                   param.clearance, param.feat_names, edges)
                shape, label_map, edges = new_feat.add_feature()

                if len(edges) == 0:
                    break

            else:
                # Need to find bounds after each machining feature besides from inner bounds
                triangulate_shape(shape)
                new_feat = feat_classes[feat_name](shape, label_map, param.min_len, param.clearance, param.feat_names)
                if count == 0:
                    shape, label_map, bounds = new_feat.add_feature(bounds, find_bounds=True)

                    if feat_name in through_blind_features:
                        count += 1

                else:
                    shape, label_map, bounds = new_feat.add_feature(bounds, find_bounds=False)

                    count += 1

        if shape is not None:
            break

        try_cnt += 1
        if try_cnt > len(combo):
            shape = None
            label_map = None
            break

    return shape, label_map


def display_bounds(bounds, display, color):
    for bound in bounds:
        rect = [gp_Pnt(bound[0][0], bound[0][1], bound[0][2]),
                gp_Pnt(bound[1][0], bound[1][1], bound[1][2]),
                gp_Pnt(bound[2][0], bound[2][1], bound[2][2]),
                gp_Pnt(bound[3][0], bound[3][1], bound[3][2]),
                gp_Pnt(bound[0][0], bound[0][1], bound[0][2])]

        wire_sect = BRepBuilderAPI_MakeWire()

        for i in range(len(rect) - 1):
            edge_sect = BRepBuilderAPI_MakeEdge(rect[i], rect[i+1]).Edge()
            wire_sect.Add(edge_sect)

        sect = wire_sect.Wire()

        display.DisplayShape(sect, update=True, color=color)

    return display


def get_cls_label(faces_list, seg_map):
    '''
    Create semantic segmentation labels (cls).
    Format: {"face_id": label, ...} where keys are strings
    
    Args:
        faces_list: list of TopoDS_Face
        seg_map: {TopoDS_Face: int} semantic segmentation map
    
    Returns:
        cls_label: {str: int} mapping from face index (as string) to label
    '''
    cls_label = {}
    for face in faces_list:
        face_idx = faces_list.index(face)    
        cls_label[str(face_idx)] = seg_map[face]

    return cls_label


def get_seg_label(faces_list, inst_map):
    '''
    Create instance segmentation labels (seg).
    Format: [[face_ids], [face_ids], ...] where each sublist contains face IDs of one instance
    
    Args:
        faces_list: list of TopoDS_Face
        inst_map: [[TopoDS_Face]] list of face lists per instance
    
    Returns:
        seg_label: list of lists, each sublist contains face indices belonging to one instance
    '''
    seg_label = []
    
    for inst in inst_map:
        inst_face_ids = []
        for inst_face in inst:
            if inst_face not in faces_list:
                print('WARNING! missing face', inst_face.__hash__()) 
                continue
            face_idx = faces_list.index(inst_face)
            inst_face_ids.append(face_idx)
        seg_label.append(inst_face_ids)

    return seg_label


def get_bottom_label(faces_list, bottom_map):
    '''
    Create bottom face identification labels.
    Format: {"face_id": 0/1, ...} where keys are strings
    
    Args:
        faces_list: list of TopoDS_Face
        bottom_map: {TopoDS_Face: int} bottom face map (1=bottom, 0=not bottom)
    
    Returns:
        bottom_label: {str: int} mapping from face index (as string) to bottom label
    '''
    bottom_label = {}
    for face in faces_list:
        face_idx = faces_list.index(face)    
        bottom_label[str(face_idx)] = bottom_map[face]

    return bottom_label


# Keep old function names as aliases for backward compatibility
def get_segmentation_label(faces_list, seg_map):
    '''Alias for get_cls_label for backward compatibility'''
    return get_cls_label(faces_list, seg_map)


def get_instance_label(faces_list, num_faces, inst_map):
    '''Alias for get_seg_label for backward compatibility'''
    return get_seg_label(faces_list, inst_map)


def save_json_data(pathname, data):
    import json
    """Export a data to a json file"""
    with open(pathname, 'w', encoding='utf8') as fp:
        json.dump(data, fp, indent=4, ensure_ascii=False, sort_keys=False)


if __name__ == '__main__':
    from OCC.Display import SimpleGui

    combo = [22]

    shape, label_map = shape_from_directive(combo)

    OCC_DISPLAY, START_OCC_DISPLAY, ADD_MENU, _ = SimpleGui.init_display()
    OCC_DISPLAY.EraseAll()

    OCC_DISPLAY.DisplayShape(shape)
    #OCC_DISPLAY = display_bounds(bounds, OCC_DISPLAY, color="blue")

    OCC_DISPLAY.View_Iso()
    OCC_DISPLAY.FitAll()

    START_OCC_DISPLAY()
