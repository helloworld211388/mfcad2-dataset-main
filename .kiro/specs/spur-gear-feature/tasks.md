# Implementation Plan: Spur Gear Feature

## Overview

本实现计划将直齿轮特征分解为可执行的编码任务。实现将遵循现有的特征创建架构，继承`AdditiveFeature`类，并与现有的数据集生成系统无缝集成。

## Tasks

- [x] 1. 注册齿轮特征到系统
  - [x] 1.1 在 Utils/parameters.py 中添加 "spur_gear" 到 feat_names 列表
    - 在 feat_names 列表末尾（stock 之前）添加 "spur_gear"
    - 添加齿轮相关参数常量（齿数范围、模数范围）
    - _Requirements: 5.4_

  - [x] 1.2 在 feature_creation.py 中注册 SpurGear 类
    - 导入 SpurGear 类
    - 添加到 feat_names 列表
    - 添加到 feat_classes 字典
    - _Requirements: 5.5, 7.4_

- [x] 2. 实现 SpurGear 核心类
  - [x] 2.1 创建 Features/spur_gear.py 文件并实现基础类结构
    - 创建 SpurGear 类继承 AdditiveFeature
    - 实现 __init__ 方法，设置 shifter_type=4, bound_type=4, depth_type="blind", feat_type="spur_gear"
    - 添加齿轮参数属性（num_teeth, module, pitch_diameter, addendum_diameter, dedendum_diameter）
    - _Requirements: 7.1, 7.5_

  - [x] 2.2 实现 _generate_gear_parameters 方法
    - 随机生成齿数 z ∈ [8, 30]
    - 随机生成模数 m ∈ [0.5, 2.0]
    - 计算分度圆直径 d = m × z
    - 计算齿顶圆直径 da = m × z + 2m
    - 计算齿根圆直径 df = m × z - 2.5m
    - 验证 da <= max_diameter - clearance
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [ ]* 2.3 编写属性测试：参数边界和几何一致性
    - **Property 1: Parameter Bounds**
    - **Property 2: Gear Geometry Consistency**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6, 3.4, 3.5**

- [x] 3. 实现圆柱体基体创建
  - [x] 3.1 实现 _add_sketch 方法
    - 从 bound 计算中心点和法向量
    - 计算可用的最大直径
    - 调用 _generate_gear_parameters 生成参数
    - 创建直径为 addendum_diameter 的圆形草图
    - _Requirements: 2.1, 2.2, 2.4_

  - [ ]* 3.2 编写属性测试：圆柱体几何
    - **Property 3: Cylinder Geometry**
    - **Validates: Requirements 2.2, 2.3, 2.4**

- [x] 4. 实现齿槽几何生成
  - [x] 4.1 实现 _create_tooth_slot 方法
    - 计算齿槽深度 = 1.25 × m
    - 计算齿槽宽度 ≈ π × m / 2
    - 计算齿槽角度位置 = 2π × i / z
    - 创建简化梯形齿槽轮廓
    - 拉伸齿槽为实体
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 4.2 编写属性测试：齿槽数量
    - **Property 4: Tooth Slot Count**
    - **Validates: Requirements 3.3**

- [x] 5. 实现布尔运算和特征应用
  - [x] 5.1 实现 _apply_feature 方法
    - 使用 BRepFeat_MakePrism 创建圆柱体基体
    - 融合圆柱体与原始形状
    - 循环创建并切削所有齿槽
    - 使用 BRepAlgoAPI_Cut 进行布尔减法
    - _Requirements: 4.1, 4.2_

  - [x] 5.2 实现拓扑验证逻辑
    - 使用 TopologyExplorer 检查实体数量
    - 验证结果为单一实体
    - 失败时返回原始形状
    - _Requirements: 4.3, 4.4, 6.1, 6.2, 6.3, 6.4_

  - [ ]* 5.3 编写属性测试：拓扑有效性
    - **Property 5: Topological Validity**
    - **Validates: Requirements 4.3, 6.1, 6.2**

- [x] 6. 实现标签映射更新
  - [x] 6.1 实现 _merge_label_map 方法
    - 保留原始面的标签
    - 为新创建的面分配齿轮标签
    - 使用 feat_names.index("spur_gear") 获取标签索引
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 6.2 编写属性测试：标签映射完整性
    - **Property 6: Label Map Integrity**
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [ ] 7. Checkpoint - 核心功能验证
  - 确保所有测试通过，如有问题请询问用户

- [x] 8. 实现错误处理
  - [x] 8.1 添加参数生成重试逻辑
    - 参数无效时重试最多10次
    - 所有重试失败后返回原始形状
    - _Requirements: 1.4_

  - [x] 8.2 添加布尔运算错误处理
    - 检查 BRepAlgoAPI_Fuse/Cut 结果是否为空
    - 单个齿槽失败时跳过继续处理
    - 最终结果无效时返回原始形状
    - _Requirements: 4.4, 6.3_

- [ ] 9. 集成测试
  - [ ]* 9.1 编写集成测试
    - 测试齿轮特征在 shape_from_directive 中的使用
    - 测试齿轮与其他特征的组合
    - _Requirements: 7.4_

  - [ ]* 9.2 编写属性测试：返回值完整性
    - **Property 7: Return Value Completeness**
    - **Validates: Requirements 4.5, 6.5**

- [ ] 10. Final Checkpoint - 完整功能验证
  - 确保所有测试通过，如有问题请询问用户
  - 验证齿轮特征可以正常生成并显示

## Notes

- 标记 `*` 的任务为可选测试任务，可跳过以加快MVP开发
- 每个任务都引用了具体的需求以确保可追溯性
- 检查点任务用于增量验证
- 属性测试验证普遍正确性属性
- 单元测试验证特定示例和边界情况
