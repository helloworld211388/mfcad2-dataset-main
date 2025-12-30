#!/usr/bin/env python
"""
Test script to generate a gear feature and save it as a STEP file.
"""

import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import Utils.parameters as param
import feature_creation

# Test generating a gear
if __name__ == '__main__':
    print("Testing gear generation...")
    
    # Get the index of the gear feature
    gear_idx = param.feat_names.index('gear')
    print(f"Gear feature index: {gear_idx}")
    
    # Create a combination with just the gear feature
    combo = [gear_idx]
    
    print("Generating shape with gear feature...")
    shape, label_map = feature_creation.shape_from_directive(combo)
    
    if shape is None:
        print("ERROR: Failed to generate gear shape!")
        sys.exit(1)
    
    print("Successfully generated gear shape!")
    
    # Save the shape to a STEP file
    output_dir = 'data'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_file = os.path.join(output_dir, 'test_gear.step')
    print(f"Saving gear to {output_file}...")
    
    from main import save_shape
    save_shape(shape, output_file, label_map)
    
    print(f"Gear saved successfully to {output_file}")
    print("Test completed!")
