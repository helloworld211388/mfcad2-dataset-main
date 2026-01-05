"""
Test script for label generation functionality.
Tests that STEP files are generated with proper semantic segmentation,
instance segmentation, and bottom face identification labels.
"""

import os
import json
import Utils.parameters as param
import Utils.occ_utils as occ_utils
import feature_creation


def test_single_feature(feat_idx, output_dir='test_output'):
    """Test label generation for a single feature type."""
    feat_name = param.feat_names[feat_idx]
    print(f"\n{'='*60}")
    print(f"Testing feature: {feat_name} (index {feat_idx})")
    print('='*60)
    
    # Generate shape with the feature
    combo = [feat_idx]
    try:
        shape, labels = feature_creation.shape_from_directive(combo)
    except Exception as e:
        print(f"Error generating shape: {e}")
        return False
    
    if shape is None:
        print("Shape generation returned None")
        return False
    
    # Check label format
    if not isinstance(labels, tuple) or len(labels) != 3:
        print(f"Error: labels should be a tuple of 3 elements, got {type(labels)}")
        return False
    
    seg_map, inst_label, bottom_map = labels
    
    # Get face list
    faces_list = occ_utils.list_face(shape)
    num_faces = len(faces_list)
    print(f"Number of faces: {num_faces}")
    
    # Validate semantic segmentation labels
    seg_label = feature_creation.get_segmentation_label(faces_list, seg_map)
    print(f"Semantic segmentation labels: {len(seg_label)} entries")
    if len(seg_label) != num_faces:
        print(f"Error: seg_label count mismatch ({len(seg_label)} vs {num_faces})")
        return False
    
    # Count labels by type
    label_counts = {}
    for face_idx, label in seg_label.items():
        label_name = param.feat_names[label] if label < len(param.feat_names) else f"unknown_{label}"
        label_counts[label_name] = label_counts.get(label_name, 0) + 1
    print(f"Label distribution: {label_counts}")
    
    # Validate instance segmentation labels
    relation_matrix = feature_creation.get_instance_label(faces_list, num_faces, inst_label)
    print(f"Instance segmentation matrix: {len(relation_matrix)}x{len(relation_matrix[0]) if relation_matrix else 0}")
    if len(relation_matrix) != num_faces:
        print(f"Error: relation_matrix row count mismatch ({len(relation_matrix)} vs {num_faces})")
        return False
    
    # Count instances
    num_instances = len(inst_label)
    print(f"Number of instances: {num_instances}")
    
    # Validate bottom face labels
    bottom_label = feature_creation.get_bottom_label(faces_list, bottom_map)
    print(f"Bottom face labels: {len(bottom_label)} entries")
    if len(bottom_label) != num_faces:
        print(f"Error: bottom_label count mismatch ({len(bottom_label)} vs {num_faces})")
        return False
    
    # Count bottom faces
    bottom_count = sum(1 for v in bottom_label.values() if v == 1)
    print(f"Bottom faces: {bottom_count} / {num_faces}")
    
    print(f"SUCCESS: Feature {feat_name} passed all validation checks")
    return True


def test_multiple_features(feat_indices, output_dir='test_output'):
    """Test label generation for multiple features combined."""
    feat_names_str = [param.feat_names[i] for i in feat_indices]
    print(f"\n{'='*60}")
    print(f"Testing combined features: {feat_names_str}")
    print('='*60)
    
    try:
        shape, labels = feature_creation.shape_from_directive(feat_indices)
    except Exception as e:
        print(f"Error generating shape: {e}")
        return False
    
    if shape is None:
        print("Shape generation returned None")
        return False
    
    if not isinstance(labels, tuple) or len(labels) != 3:
        print(f"Error: labels should be a tuple of 3 elements, got {type(labels)}")
        return False
    
    seg_map, inst_label, bottom_map = labels
    faces_list = occ_utils.list_face(shape)
    num_faces = len(faces_list)
    
    print(f"Number of faces: {num_faces}")
    print(f"Number of instances: {len(inst_label)}")
    
    # Validate all labels
    seg_label = feature_creation.get_segmentation_label(faces_list, seg_map)
    relation_matrix = feature_creation.get_instance_label(faces_list, num_faces, inst_label)
    bottom_label = feature_creation.get_bottom_label(faces_list, bottom_map)
    
    if len(seg_label) != num_faces or len(relation_matrix) != num_faces or len(bottom_label) != num_faces:
        print("Error: Label count mismatch")
        return False
    
    print(f"SUCCESS: Combined features passed all validation checks")
    return True


if __name__ == '__main__':
    print("Testing Label Generation Functionality")
    print("="*60)
    
    # Test a few individual features
    test_features = [
        1,   # through_hole
        12,  # blind_hole
        14,  # rectangular_pocket
        6,   # rectangular_through_slot
        0,   # chamfer
        23,  # round
    ]
    
    results = []
    for feat_idx in test_features:
        if feat_idx < len(param.feat_names) - 1:  # Exclude 'stock'
            result = test_single_feature(feat_idx)
            results.append((param.feat_names[feat_idx], result))
    
    # Test combined features
    combined_result = test_multiple_features([1, 14, 0])  # through_hole + rectangular_pocket + chamfer
    results.append(("combined", combined_result))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
    
    total_pass = sum(1 for _, r in results if r)
    total_tests = len(results)
    print(f"\nTotal: {total_pass}/{total_tests} tests passed")
