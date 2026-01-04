# Requirements Document

## Introduction

本文档定义了在MFCAD++数据集生成系统中添加直齿轮（Spur Gear）特征的需求。该特征将在正方体基体上先添加圆柱体，然后通过去除材料形成齿轮齿槽，生成完整的直齿轮几何形状。齿轮的齿数和模数将在合理的拓扑约束范围内随机生成。

## Glossary

- **Spur_Gear_Feature**: 直齿轮特征，由圆柱体基体和渐开线齿形组成的加工特征
- **Stock_Shape**: 基体形状，当前为正方体（Box）
- **Cylinder_Base**: 圆柱体基体，齿轮的主体部分，从基体表面凸出
- **Tooth_Profile**: 齿形轮廓，单个齿的横截面形状，采用渐开线或简化梯形
- **Module**: 模数(m)，齿轮的基本参数，等于分度圆直径除以齿数
- **Number_of_Teeth**: 齿数(z)，齿轮上齿的数量
- **Pitch_Circle**: 分度圆，直径 d = m × z
- **Addendum_Circle**: 齿顶圆，直径 da = d + 2m
- **Dedendum_Circle**: 齿根圆，直径 df = d - 2.5m
- **Pressure_Angle**: 压力角，标准值为20度
- **Face_Width**: 齿宽，齿轮沿轴向的宽度
- **Label_Map**: 标签映射，用于标识B-Rep面所属的特征类型
- **Bound**: 边界区域，用于确定特征可放置的位置
- **Clearance**: 间隙参数，特征与边界之间的最小距离

## Requirements

### Requirement 1: 齿轮参数随机生成

**User Story:** As a dataset generator, I want to randomly generate valid gear parameters, so that I can create diverse gear samples while maintaining geometric validity.

#### Acceptance Criteria

1. WHEN generating gear parameters, THE Spur_Gear_Feature SHALL randomly select the number of teeth (z) within the range [8, 30]
2. WHEN generating gear parameters, THE Spur_Gear_Feature SHALL randomly select the module (m) within the range [0.5, 2.0]
3. WHEN gear parameters are generated, THE Spur_Gear_Feature SHALL validate that the addendum circle diameter (da = m × z + 2m) does not exceed the available bound size minus clearance
4. IF the generated parameters would result in invalid geometry, THEN THE Spur_Gear_Feature SHALL regenerate parameters up to 10 attempts before failing gracefully
5. WHEN gear parameters are valid, THE Spur_Gear_Feature SHALL calculate the pitch circle diameter as d = m × z
6. WHEN gear parameters are valid, THE Spur_Gear_Feature SHALL calculate the dedendum circle diameter as df = m × z - 2.5m

### Requirement 2: 圆柱体基体创建

**User Story:** As a CAD modeler, I want to create a cylindrical base on the stock shape, so that the gear teeth can be machined on a proper circular foundation.

#### Acceptance Criteria

1. WHEN creating the gear feature, THE Spur_Gear_Feature SHALL first identify valid planar faces on the stock shape using the existing bound detection mechanism
2. WHEN a valid bound is found, THE Spur_Gear_Feature SHALL create a cylindrical base with diameter equal to the addendum circle diameter (da)
3. WHEN creating the cylindrical base, THE Spur_Gear_Feature SHALL set the cylinder height (face width) randomly between min_len and the maximum available depth
4. THE Spur_Gear_Feature SHALL ensure the cylindrical base center is positioned at the center of the selected bound
5. WHEN the cylindrical base is created, THE Spur_Gear_Feature SHALL fuse it with the stock shape using Boolean union operation

### Requirement 3: 齿槽几何生成

**User Story:** As a CAD modeler, I want to generate accurate tooth slot geometry, so that the gear teeth have proper involute or simplified profiles.

#### Acceptance Criteria

1. WHEN generating tooth slots, THE Spur_Gear_Feature SHALL create tooth profiles based on the calculated module and number of teeth
2. WHEN creating tooth profiles, THE Spur_Gear_Feature SHALL use simplified trapezoidal tooth profiles for computational efficiency
3. WHEN creating tooth slots, THE Spur_Gear_Feature SHALL generate exactly z (number of teeth) evenly spaced slots around the pitch circle
4. WHEN creating each tooth slot, THE Spur_Gear_Feature SHALL ensure the slot depth equals (addendum circle radius - dedendum circle radius)
5. WHEN creating each tooth slot, THE Spur_Gear_Feature SHALL ensure the slot width at the pitch circle equals approximately half the circular pitch (π × m / 2)

### Requirement 4: 布尔切削操作

**User Story:** As a CAD modeler, I want to cut the tooth slots from the cylindrical base, so that the final gear geometry is correctly formed.

#### Acceptance Criteria

1. WHEN cutting tooth slots, THE Spur_Gear_Feature SHALL create a solid representation of each tooth slot
2. WHEN cutting tooth slots, THE Spur_Gear_Feature SHALL use Boolean subtraction to remove material from the cylindrical base
3. WHEN all tooth slots are cut, THE Spur_Gear_Feature SHALL verify the resulting shape has exactly one solid
4. IF the Boolean operation results in multiple solids or fails, THEN THE Spur_Gear_Feature SHALL return the original shape unchanged
5. WHEN the gear is successfully created, THE Spur_Gear_Feature SHALL return the modified shape with updated label map

### Requirement 5: 标签映射更新

**User Story:** As a dataset generator, I want to correctly label all gear faces, so that the machine learning model can identify gear features in the dataset.

#### Acceptance Criteria

1. WHEN the gear feature is created, THE Spur_Gear_Feature SHALL assign the gear feature label to all newly created faces
2. WHEN updating labels, THE Spur_Gear_Feature SHALL preserve labels of faces from the original stock shape that remain unchanged
3. WHEN updating labels, THE Spur_Gear_Feature SHALL use the feature index from feat_names for the gear label
4. THE Spur_Gear_Feature SHALL be registered in the feat_names list in parameters.py with name "spur_gear"
5. THE Spur_Gear_Feature SHALL be registered in the feat_classes dictionary in feature_creation.py

### Requirement 6: 拓扑有效性验证

**User Story:** As a dataset generator, I want to ensure all generated gears have valid topology, so that the dataset contains only geometrically correct models.

#### Acceptance Criteria

1. WHEN a gear is generated, THE Spur_Gear_Feature SHALL verify the result is a single valid solid
2. WHEN a gear is generated, THE Spur_Gear_Feature SHALL verify all faces are properly connected
3. IF the gear geometry is invalid, THEN THE Spur_Gear_Feature SHALL return the original shape and label map unchanged
4. WHEN validating geometry, THE Spur_Gear_Feature SHALL use TopologyExplorer to check the number of solids
5. WHEN the gear passes validation, THE Spur_Gear_Feature SHALL return the gear shape, updated label map, and bounds

### Requirement 7: 与现有系统集成

**User Story:** As a developer, I want the gear feature to integrate seamlessly with the existing feature creation system, so that gears can be combined with other machining features.

#### Acceptance Criteria

1. THE Spur_Gear_Feature class SHALL inherit from AdditiveFeature class
2. THE Spur_Gear_Feature SHALL implement the _add_sketch method to create the gear profile
3. THE Spur_Gear_Feature SHALL override the _apply_feature method to handle gear-specific Boolean operations
4. WHEN integrated, THE Spur_Gear_Feature SHALL be usable in feature combinations via the shape_from_directive function
5. THE Spur_Gear_Feature SHALL follow the same initialization pattern as other features (shape, label_map, min_len, clearance, feat_names)
