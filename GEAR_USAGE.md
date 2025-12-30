# How to Generate Gear Features

## Quick Start

### Generate a Gear Sample
```bash
python generate_gear_sample.py
```

This will create a `data/gear.step` file containing a stock cube with a gear feature added to it.

## Understanding the Gear Implementation

### What Changed
Previously, attempting to generate a gear would result in just a cube (stock) being saved. Now, the gear feature properly generates gear tooth geometry.

### Gear Feature Characteristics
- **Type**: Additive feature (adds material to the stock)
- **Geometry**: Simplified spur gear with involute-like tooth profiles
- **Parametric**: Automatically sizes to fit available space

### How It Works

1. **Stock Creation**: A base cube is created as the stock
2. **Gear Profile**: The gear class generates a 2D tooth profile
   - Calculates optimal number of teeth (8-100)
   - Creates teeth using sinusoidal radius variation
   - Each tooth has proper addendum (top) and dedendum (root)
3. **Extrusion**: The profile is extruded to create a 3D gear
4. **Integration**: The gear is fused with the stock

### Manual Usage in Code

```python
import Utils.parameters as param
import feature_creation
from main import save_shape

# Get gear feature index
gear_idx = param.feat_names.index('gear')

# Generate with gear only
combo = [gear_idx]
shape, label_map = feature_creation.shape_from_directive(combo)

# Save to STEP file
save_shape(shape, 'output.step', label_map)
```

### Combining with Other Features

You can also combine the gear with other features:

```python
# Gear + chamfer
chamfer_idx = param.feat_names.index('chamfer')
gear_idx = param.feat_names.index('gear')
combo = [gear_idx, chamfer_idx]

# Generate and save
shape, label_map = feature_creation.shape_from_directive(combo)
save_shape(shape, 'gear_with_chamfer.step', label_map)
```

## Gear Parameters

The gear dimensions are automatically calculated based on:
- **Available space**: The gear fits within the bound rectangle
- **Clearance**: Standard clearance is maintained
- **Module**: Tooth size (automatically determined)
- **Number of teeth**: Calculated from available radius and module

### Standard Formulas Used
- Pitch radius = (module × number of teeth) / 2
- Outer radius = pitch radius + module (addendum)
- Root radius = pitch radius - 1.25 × module (dedendum)

## Troubleshooting

### If gear generation fails
The implementation includes a fallback mechanism:
1. First tries to generate detailed tooth profile
2. If that fails, creates a simple circular profile
3. Returns None only if all attempts fail

### Environment Setup
The code requires:
- Python 3.9
- pythonocc-core 7.5.1
- numpy
- numba

To set up the environment:
```bash
conda env create -f environment.yml
conda activate mfcadpp
```

## Verification

To verify the gear feature is properly integrated:
```bash
python verify_gear.py
```

This checks:
- Gear is in the feature names list
- Gear class is imported correctly  
- All required methods exist

## Files Modified

1. **Features/gear.py** - New gear feature implementation
2. **Utils/parameters.py** - Added 'gear' to feat_names list
3. **feature_creation.py** - Imported and registered Gear class

## Technical Details

See `GEAR_IMPLEMENTATION.md` for detailed technical documentation.
