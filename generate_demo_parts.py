"""
生成包含新特征（counterbore, countersunk_hole, variable_round）和相交特征的演示零件。
零件面数较多，用于展示和验证。

运行方式: conda activate myoccwlenv && python generate_demo_parts.py
"""

import os
import sys
import json
import random
import time

from multiprocessing import Process

from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.STEPConstruct import stepconstruct_FindEntity
from OCC.Core.TCollection import TCollection_HAsciiString
from OCC.Core.TopoDS import TopoDS_Solid, TopoDS_Compound, TopoDS_CompSolid

import Utils.occ_utils as occ_utils
import Utils.parameters as param
import feature_creation


def save_step(filename, shape, seg_map):
    """保存STEP文件，带面标签"""
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    finderp = writer.WS().TransferWriter().FinderProcess()
    faces = occ_utils.list_face(shape)
    loc = TopLoc_Location()
    for face in faces:
        item = stepconstruct_FindEntity(finderp, face, loc)
        if item is not None:
            item.SetName(TCollection_HAsciiString(str(seg_map[face])))
    writer.Write(filename)


def save_label(pathname, cls_label, seg_label, bottom_label):
    """保存JSON标签文件"""
    data = {"cls": cls_label, "seg": seg_label, "bottom": bottom_label}
    with open(pathname, 'w', encoding='utf8') as fp:
        json.dump(data, fp, ensure_ascii=False)


def generate_one_part(output_dir, combo, name):
    """生成单个零件并保存"""
    try:
        shape, labels = feature_creation.shape_from_directive(combo)
    except Exception as e:
        print(f'[{name}] 生成失败: {e}')
        return False

    if shape is None:
        print(f'[{name}] shape为None，跳过')
        return False

    if not isinstance(shape, (TopoDS_Solid, TopoDS_Compound, TopoDS_CompSolid)):
        print(f'[{name}] shape类型不支持: {type(shape)}')
        return False

    seg_map, inst_label, bottom_map = labels
    faces_list = occ_utils.list_face(shape)
    num_faces = len(faces_list)

    if num_faces == 0:
        print(f'[{name}] 无面，跳过')
        return False

    cls_label = feature_creation.get_cls_label(faces_list, seg_map)
    seg_label = feature_creation.get_seg_label(faces_list, inst_label)
    bottom_label = feature_creation.get_bottom_label(faces_list, bottom_map)

    step_dir = os.path.join(output_dir, 'steps')
    label_dir = os.path.join(output_dir, 'labels')

    step_path = os.path.join(step_dir, name + '.step')
    label_path = os.path.join(label_dir, name + '.json')

    save_step(step_path, shape, seg_map)
    save_label(label_path, cls_label, seg_label, bottom_label)

    # 统计特征类型
    feat_types = set(cls_label.values())
    feat_names_used = [param.feat_names[i] for i in feat_types]
    print(f'[{name}] 成功! 面数={num_faces}, '
          f'特征类型={feat_names_used}')
    return True


# ============================================================
# 演示零件定义
# 每个零件包含多个特征，确保：
#   1. 包含新特征 (counterbore=24, countersunk_hole=25, variable_round=26)
#   2. 包含相交特征（多个特征叠加在同一stock上，自然产生相交）
#   3. 面数较多（通过增加特征数量实现）
# ============================================================

# 特征索引速查
CHAMFER = 0
THROUGH_HOLE = 1
TRI_PASSAGE = 2
RECT_PASSAGE = 3
SIX_PASSAGE = 4
TRI_THROUGH_SLOT = 5
RECT_THROUGH_SLOT = 6
CIRC_THROUGH_SLOT = 7
RECT_THROUGH_STEP = 8
TWO_SIDES_STEP = 9
SLANTED_STEP = 10
ORING = 11
BLIND_HOLE = 12
TRI_POCKET = 13
RECT_POCKET = 14
SIX_POCKET = 15
CIRC_END_POCKET = 16
RECT_BLIND_SLOT = 17
V_CIRC_BLIND_SLOT = 18
H_CIRC_BLIND_SLOT = 19
TRI_BLIND_STEP = 20
CIRC_BLIND_STEP = 21
RECT_BLIND_STEP = 22
ROUND = 23
COUNTERBORE = 24
COUNTERSUNK = 25
VAR_ROUND = 26

# 5个演示零件的特征组合
DEMO_PARTS = {
    # 零件1: 沉头孔 + 多个通孔/盲孔 + 台阶 + 倒角 → 大量相交
    "demo_counterbore_complex": [
        RECT_THROUGH_STEP, TWO_SIDES_STEP,
        THROUGH_HOLE, THROUGH_HOLE, BLIND_HOLE,
        COUNTERBORE, COUNTERBORE,
        RECT_POCKET,
        CHAMFER, CHAMFER,
    ],
    # 零件2: 埋头孔 + 通槽 + 盲槽 + 口袋 → 相交丰富
    "demo_countersunk_complex": [
        RECT_THROUGH_STEP, SLANTED_STEP,
        RECT_THROUGH_SLOT, CIRC_THROUGH_SLOT,
        COUNTERSUNK, COUNTERSUNK,
        CIRC_END_POCKET, RECT_BLIND_SLOT,
        ROUND, ROUND,
    ],
    # 零件3: 变半径圆角 + 多种口袋/通道 + 台阶 → 面数多
    "demo_variable_round_complex": [
        RECT_THROUGH_STEP, TRI_BLIND_STEP, CIRC_BLIND_STEP,
        TRI_PASSAGE, RECT_PASSAGE,
        BLIND_HOLE, RECT_POCKET,
        VAR_ROUND, VAR_ROUND, VAR_ROUND,
    ],
    # 零件4: 三种新特征全包含 + 大量传统特征 → 最复杂
    "demo_all_new_features": [
        RECT_THROUGH_STEP, TWO_SIDES_STEP, SLANTED_STEP,
        THROUGH_HOLE, BLIND_HOLE,
        RECT_THROUGH_SLOT,
        COUNTERBORE, COUNTERSUNK,
        RECT_POCKET, SIX_POCKET,
        VAR_ROUND, VAR_ROUND,
        CHAMFER,
    ],
    # 零件5: 三种新特征 + O型圈 + 六边形 → 高面数
    "demo_mixed_high_faces": [
        RECT_THROUGH_STEP, RECT_BLIND_STEP,
        SIX_PASSAGE, TRI_POCKET, CIRC_END_POCKET,
        ORING,
        COUNTERBORE, COUNTERSUNK,
        H_CIRC_BLIND_SLOT, V_CIRC_BLIND_SLOT,
        VAR_ROUND, ROUND,
    ],
}


if __name__ == '__main__':
    output_dir = './demo_output'
    os.makedirs(os.path.join(output_dir, 'steps'), exist_ok=True)
    os.makedirs(os.path.join(output_dir, 'labels'), exist_ok=True)

    print("=" * 60)
    print("开始生成演示零件")
    print(f"输出目录: {os.path.abspath(output_dir)}")
    print(f"零件数量: {len(DEMO_PARTS)}")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for name, combo in DEMO_PARTS.items():
        feat_desc = [param.feat_names[i] for i in combo]
        print(f"\n--- 生成 {name} ---")
        print(f"  特征组合({len(combo)}个): {feat_desc}")

        # 每个零件最多尝试5次（因为随机参数可能导致失败）
        ok = False
        for attempt in range(5):
            p = Process(target=generate_one_part,
                        args=(output_dir, combo, name))
            p.start()
            p.join(timeout=120)

            if p.is_alive():
                p.terminate()
                p.join()
                print(f"  第{attempt+1}次尝试超时，重试...")
                continue

            if p.exitcode == 0:
                ok = True
                break
            else:
                print(f"  第{attempt+1}次尝试失败(exit={p.exitcode})，重试...")

        if ok:
            success_count += 1
        else:
            fail_count += 1
            print(f"  {name} 最终失败!")

    print("\n" + "=" * 60)
    print(f"生成完成! 成功={success_count}, 失败={fail_count}")
    print(f"STEP文件: {os.path.abspath(os.path.join(output_dir, 'steps'))}")
    print(f"标签文件: {os.path.abspath(os.path.join(output_dir, 'labels'))}")
    print("=" * 60)
