"""Creates dataset from random combination of machining features

Used to generate dataset of stock cube with machining features applied to them.
The number of machining features is defined by the combination range.
To change the parameters of each machining feature, please see parameters.py
"""

from multiprocessing import Pool
from itertools import combinations_with_replacement
import Utils.shape as shape
import Utils.parameters as param
import random
import os
import json

from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.STEPConstruct import stepconstruct_FindEntity
from OCC.Core.TCollection import TCollection_HAsciiString
from OCC.Core.TopoDS import TopoDS_Solid, TopoDS_Compound, TopoDS_CompSolid
import Utils.occ_utils as occ_utils
import feature_creation

from OCC.Extend.DataExchange import STEPControl_Writer
from OCC.Core.Interface import Interface_Static_SetCVal
from OCC.Core.IFSelect import IFSelect_RetDone, IFSelect_ItemsByEntity


def shape_with_fid_to_step(filename, shape, id_map, save_face_label=False):
    """Save shape to a STEP file format.

    :param filename: Name to save shape as.
    :param shape: Shape to be saved.
    :param id_map: Variable mapping labels to faces in shape.
    :param save_face_label: Whether to save face labels in STEP file.
    :return: None
    """
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)

    if save_face_label:
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


def save_shape(shape, step_path, seg_map, save_face_label=False):
    """Save shape to STEP file.
    
    :param shape: TopoDS_Shape to save
    :param step_path: Path to save STEP file
    :param seg_map: Segmentation map {TopoDS_Face: int}
    :param save_face_label: Whether to embed face labels in STEP file
    """
    print(f"Saving: {step_path}")
    shape_with_fid_to_step(step_path, shape, seg_map, save_face_label)


def save_label(shape_name, pathname, seg_label, relation_matrix, bottom_label):
    """Export labels to a json file.
    
    :param shape_name: Name of the shape
    :param pathname: Path to save JSON file
    :param seg_label: Semantic segmentation labels {face_id: label}
    :param relation_matrix: Instance segmentation matrix (list of lists)
    :param bottom_label: Bottom face identification labels {face_id: 0/1}
    """
    data = [
        [shape_name, {'seg': seg_label, 'inst': relation_matrix, 'bottom': bottom_label}]
    ]
    with open(pathname, 'w', encoding='utf8') as fp:
        json.dump(data, fp, indent=4, ensure_ascii=False, sort_keys=False)


def generate_shape(shape_dir, combination, count):
    """Generate a shape with machining features and save with labels.
    
    :param shape_dir: Directory to save files
    :param combination: List of feature indices to apply
    :param count: Shape identifier (name)
    :return: True if successful, False otherwise
    """
    shape_name = str(count)
    
    try:
        generated_shape, labels = feature_creation.shape_from_directive(combination)
    except Exception as e:
        print(f'Failed to generate shape {shape_name}: {e}')
        return False
    
    if generated_shape is None:
        print(f'Generated shape {shape_name} is None')
        return False
    
    # Check shape type
    if not isinstance(generated_shape, (TopoDS_Solid, TopoDS_Compound, TopoDS_CompSolid)):
        print(f'Generated shape {shape_name} is {type(generated_shape)}, not supported')
        return False
    
    # Extract labels from the label tuple
    seg_map, inst_label, bottom_map = labels
    
    # Get face list
    faces_list = occ_utils.list_face(generated_shape)
    if len(faces_list) == 0:
        print(f'Empty shape {shape_name}')
        return False
    
    # Create semantic segmentation labels
    seg_label = feature_creation.get_segmentation_label(faces_list, seg_map)
    if len(seg_label) != len(faces_list):
        print(f'Shape {shape_name} has wrong number of seg labels {len(seg_label)} with faces {len(faces_list)}')
        return False
    
    # Create instance segmentation labels (relation matrix)
    relation_matrix = feature_creation.get_instance_label(faces_list, len(faces_list), inst_label)
    if len(relation_matrix) != len(faces_list):
        print(f'Shape {shape_name} has wrong number of instance labels {len(relation_matrix)} with faces {len(faces_list)}')
        return False
    
    # Create bottom face identification labels
    bottom_label = feature_creation.get_bottom_label(faces_list, bottom_map)
    if len(bottom_label) != len(faces_list):
        print(f'Shape {shape_name} has wrong number of bottom labels {len(bottom_label)} with faces {len(faces_list)}')
        return False
    
    # Create directories if needed
    step_dir = os.path.join(shape_dir, 'steps')
    label_dir = os.path.join(shape_dir, 'labels')
    if not os.path.exists(step_dir):
        os.makedirs(step_dir)
    if not os.path.exists(label_dir):
        os.makedirs(label_dir)
    
    # Save files
    step_path = os.path.join(step_dir, shape_name + '.step')
    label_path = os.path.join(label_dir, shape_name + '.json')
    
    try:
        save_shape(generated_shape, step_path, seg_map, save_face_label=True)
        save_label(shape_name, label_path, seg_label, relation_matrix, bottom_label)
        print(f'Successfully saved {shape_name}')
        return True
    except Exception as e:
        print(f'Failed to save {shape_name}: {e}')
        return False


if __name__ == '__main__':
    # Parameters to be set before use
    shape_dir = 'data'
    num_features = len(param.feat_names) - 1  # All available features (excluding 'stock')
    combo_range = [3, 4]  # Range of features per combination
    num_samples = 10  # Number of samples to generate

    if not os.path.exists(shape_dir):
        os.mkdir(shape_dir)

    # Option 1: Generate random combinations
    # combos = []
    # for num_combo in range(combo_range[0], combo_range[1]):
    #     combos += list(combinations_with_replacement(range(num_features), num_combo))
    # random.shuffle(combos)
    # test_combos = combos[:num_samples]
    # for count, combo in enumerate(test_combos):
    #     print(f"{count}: {combo}")
    #     generate_shape(shape_dir, combo, count)

    # Option 2: Generate one sample per feature type
    unique_combos = []
    for i in range(num_features - 2, num_features):  # Last two features
        unique_combos.append([i])

    for i in range(len(unique_combos)):
        feat_name = param.feat_names[unique_combos[i][0]]
        print(f"Generating feature: {feat_name}")
        generate_shape(shape_dir, unique_combos[i], feat_name)
