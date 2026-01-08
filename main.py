"""Creates dataset from random combination of machining features

Used to generate dataset of stock cube with machining features applied to them.
The number of machining features is defined by the combination range.
To change the parameters of each machining feature, please see parameters.py
"""

from multiprocessing import Process
import multiprocessing
import time
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


def save_label(pathname, cls_label, seg_label, bottom_label):
    """Export labels to a json file in the target format.
    
    Format:
    {
        "cls": {"0": label, "1": label, ...},      // semantic segmentation
        "seg": [[face_ids], [face_ids], ...],      // instance segmentation  
        "bottom": {"0": 0/1, "1": 0/1, ...}        // bottom face identification
    }
    
    :param pathname: Path to save JSON file
    :param cls_label: Semantic segmentation labels {str: int}
    :param seg_label: Instance segmentation labels [[int]]
    :param bottom_label: Bottom face identification labels {str: int}
    """
    data = {
        "cls": cls_label,
        "seg": seg_label,
        "bottom": bottom_label
    }
    with open(pathname, 'w', encoding='utf8') as fp:
        json.dump(data, fp, ensure_ascii=False)


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
    
    # Create semantic segmentation labels (cls)
    cls_label = feature_creation.get_cls_label(faces_list, seg_map)
    if len(cls_label) != len(faces_list):
        print(f'Shape {shape_name} has wrong number of cls labels {len(cls_label)} with faces {len(faces_list)}')
        return False
    
    # Create instance segmentation labels (seg)
    seg_label = feature_creation.get_seg_label(faces_list, inst_label)
    
    # Create bottom face identification labels
    bottom_label = feature_creation.get_bottom_label(faces_list, bottom_map)
    if len(bottom_label) != len(faces_list):
        print(f'Shape {shape_name} has wrong number of bottom labels {len(bottom_label)} with faces {len(faces_list)}')
        return False
    
    # Create directories if needed
    step_dir = os.path.join(shape_dir, 'steps')
    label_dir = os.path.join(shape_dir, 'labels')

    # Save files
    step_path = os.path.join(step_dir, shape_name + '.step')
    label_path = os.path.join(label_dir, shape_name + '.json')
    
    try:
        save_shape(generated_shape, step_path, seg_map, save_face_label=True)
        save_label(label_path, cls_label, seg_label, bottom_label)
        print(f'Successfully saved {shape_name}')
        return True
    except Exception as e:
        print(f'Failed to save {shape_name}: {e}')
        return False


if __name__ == '__main__':
    # 参数设置
    shape_dir = '../myDatasets'
    num_features = 27  # 27类加工特征（排除后3个基础几何体：plane, cylinder, cone）
    combo_range = [3, 10]  # 每个零件包含的特征数量范围：3-10个
    num_samples = 30000  # 生成零件总数：30000个

    if not os.path.exists(shape_dir):
        os.mkdir(shape_dir)
    os.makedirs(os.path.join(shape_dir, 'steps'), exist_ok=True)
    os.makedirs(os.path.join(shape_dir, 'labels'), exist_ok=True)

    # 特征池：使用前27个加工特征（索引0-26），排除后3个基础几何体
    # feat_names前27个: chamfer, through_hole, ..., round, counterbore, countersunk_hole, variable_round
    # 排除的后3个: plane, cylinder, cone
    feature_pool = list(range(num_features))  # [0, 1, 2, ..., 26]

    max_workers = max(1, multiprocessing.cpu_count() - 1)  # 保留一个核心给系统
    processes = []
    print(f"Starting generation with {max_workers} parallel workers...")

    for count in range(num_samples):
        # 随机选择特征数量（3-10之间）和特征组合
        num_combo = random.randint(combo_range[0], combo_range[1])
        combo = tuple([random.choice(feature_pool) for _ in range(num_combo)])

        # Manage the process pool
        while len(processes) >= max_workers:
            # Check for finished processes
            # Iterate over a copy of the list to allow modification
            for p in processes[:]:
                if not p.is_alive():
                    p.join()
                    if p.exitcode != 0:
                        print(f"Warning: A shape generation process crashed (exit code {p.exitcode}). Skipping.")
                    processes.remove(p)

            # If still full, wait a bit
            if len(processes) >= max_workers:
                time.sleep(0.01)

        print(f"Starting {count}: {combo}")
        # Run generation in a separate process
        p = Process(target=generate_shape, args=(shape_dir, combo, count))
        p.start()
        processes.append(p)

    # Wait for all remaining processes to finish
    for p in processes:
        p.join()
        if p.exitcode != 0:
            print(f"Warning: A shape generation process crashed (exit code {p.exitcode}). Skipping.")

    # Option 2: Generate one sample per feature type
    # unique_combos = []
    # for i in range(num_features - 4, num_features-1):  # 取我自己新生成的三个特征。去除齿轮
    #     unique_combos.append([i])
    #
    # for i in range(len(unique_combos)):
    #     feat_name = param.feat_names[unique_combos[i][0]]
    #     print(f"Generating feature: {feat_name}")
    #     generate_shape(shape_dir, unique_combos[i], feat_name)
