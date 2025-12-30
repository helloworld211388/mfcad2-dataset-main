#!/usr/bin/env python
"""
Verify the gear feature integration in the codebase.
This script checks that the gear feature is properly registered.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Check parameters
print("Checking Utils/parameters.py...")
import Utils.parameters as param

if 'gear' in param.feat_names:
    gear_idx = param.feat_names.index('gear')
    print(f"✓ Gear found in feat_names at index {gear_idx}")
    print(f"  Total features: {len(param.feat_names)}")
else:
    print("✗ ERROR: Gear not found in feat_names!")
    sys.exit(1)

# Check feature_creation
print("\nChecking feature_creation.py...")
import feature_creation

if 'gear' in feature_creation.feat_names:
    print(f"✓ Gear found in feature_creation.feat_names")
else:
    print("✗ ERROR: Gear not found in feature_creation.feat_names!")
    sys.exit(1)

if 'gear' in feature_creation.feat_classes:
    print(f"✓ Gear class registered in feat_classes")
    gear_class = feature_creation.feat_classes['gear']
    print(f"  Gear class: {gear_class}")
else:
    print("✗ ERROR: Gear class not found in feat_classes!")
    sys.exit(1)

# Try to import the Gear class directly
print("\nChecking Features/gear.py...")
try:
    from Features.gear import Gear
    print(f"✓ Gear class imported successfully")
    print(f"  Gear class attributes: {dir(Gear)}")
    
    # Check that key methods exist
    required_methods = ['_add_sketch', '_generate_gear_profile', '__init__']
    for method in required_methods:
        if hasattr(Gear, method):
            print(f"  ✓ Method '{method}' exists")
        else:
            print(f"  ✗ ERROR: Method '{method}' missing!")
            sys.exit(1)
            
except ImportError as e:
    print(f"✗ ERROR: Failed to import Gear class: {e}")
    sys.exit(1)

print("\n" + "="*50)
print("All checks passed! Gear feature is properly integrated.")
print("="*50)
