"""Creates dataset from random combination of machining features

Used to generate dataset of stock cube with machining features applied to them.
The number of machining features is defined by the combination range.
To change the parameters of each machining feature, please see parameters.py
"""

from multiprocessing import Pool
from itertools import combinations_with_replacement
import Utils.shape as shape
import random
import os
import pickle

from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.STEPConstruct import stepconstruct_FindEntity
from OCC.Core.TCollection import TCollection_HAsciiString
import Utils.occ_utils as occ_utils
import feature_creation

from OCC.Extend.DataExchange import STEPControl_Writer
from OCC.Core.Interface import Interface_Static_SetCVal
from OCC.Core.IFSelect import IFSelect_RetDone, IFSelect_ItemsByEntity


def shape_with_fid_to_step(filename, shape, id_map):
    """Save shape to a STEP file format.

    :param filename: Name to save shape as.
    :param shape: Shape to be saved.
    :param id_map: Variable mapping labels to faces in shape.
    :return: None
    """
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)

    finderp = writer.WS().TransferWriter().FinderProcess()
    faces = occ_utils.list_face(shape)
    loc = TopLoc_Location()

    for face in faces:
        item = stepconstruct_FindEntity(finderp, face, loc)
        if item is None:
            print(face)
            continue
        item.SetName(TCollection_HAsciiString(str(id_map[face])))

    writer.Write(filename)


def directive(combo, count):
    shape_name = str(count)
    shapes, face_label_map = feature_creation.shape_from_directive(combo)

    return shapes, shape_name, face_label_map


def save_shape(shape, step_path, label_map):
    print(f"Saving: {step_path}")
    shape_with_fid_to_step(step_path, shape, label_map)


def generate_shape(shape_dir, combination, count):
    """Generate num_shapes random shapes in shape_dir
    :param arg: List of [shape directory path, machining feature combo]
    :return: None
    """
    shape_name = str(count)
    shape, label_map = feature_creation.shape_from_directive(combination)
    step_path = os.path.join(shape_dir, shape_name + '.step')
    save_shape(shape, step_path, label_map)


if __name__ == '__main__':
    # Parameters to be set before use
    shape_dir = 'data'
    num_features = 24
    combo_range = [3, 10]
    num_samples = 10

    if not os.path.exists(shape_dir):
        os.mkdir(shape_dir)

    combos = []
    for num_combo in range(combo_range[0], combo_range[1]):
        combos += list(combinations_with_replacement(range(num_features), num_combo))

    random.shuffle(combos)
    test_combos = combos[:num_samples]

    for count, combo in enumerate(test_combos):
        print(f"{count}: {combo}")
        generate_shape(shape_dir, combo, count)
