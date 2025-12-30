"""Generate a gear sample to demonstrate the gear feature works

This script generates a single STEP file containing a gear feature.
"""

import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import Utils.parameters as param
import feature_creation
from main import save_shape

if __name__ == '__main__':
    # Parameters
    shape_dir = 'data'
    
    if not os.path.exists(shape_dir):
        os.mkdir(shape_dir)
    
    # Get gear feature index
    gear_idx = param.feat_names.index('gear')
    print(f"Gear feature index: {gear_idx}")
    print(f"Generating gear sample...")
    
    # Create a combination with just the gear feature
    combo = [gear_idx]
    
    # Generate the shape
    try:
        shape, label_map = feature_creation.shape_from_directive(combo)
        
        if shape is None:
            print("ERROR: Failed to generate gear shape!")
            sys.exit(1)
        
        # Save to STEP file
        step_path = os.path.join(shape_dir, 'gear.step')
        save_shape(shape, step_path, label_map)
        
        print(f"✓ Successfully generated gear and saved to {step_path}")
        
    except Exception as e:
        print(f"ERROR during gear generation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
