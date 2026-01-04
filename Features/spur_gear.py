"""
Spur Gear Feature Module

This module implements the SpurGear class for generating spur gear features
on stock shapes in the MFCAD++ dataset generation system.
"""

import random
import math
import numpy as np
import os
import sys

from OCC.Core.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeWire,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_Transform,
)
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCC.Core.BRepFeat import BRepFeat_MakePrism
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCC.Core.gp import gp_Circ, gp_Ax2, gp_Ax3, gp_Pnt, gp_Dir, gp_Vec, gp_Trsf
from OCC.Core.TopoDS import TopoDS_Face
from OCC.Extend.TopologyUtils import TopologyExplorer

import Utils.occ_utils as occ_utils
import Utils.parameters as param
import Utils.shape_factory as shape_factory
from Features.machining_features import AdditiveFeature


# Make pygear (pygear-0.24/pygear.py) importable and detect availability
PYGEAR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pygear-0.24")
if os.path.isdir(PYGEAR_DIR) and PYGEAR_DIR not in sys.path:
    # Ensure our vendored pygear takes precedence over any installed package
    sys.path.insert(0, PYGEAR_DIR)

try:
    from pygear import CylindricalGearWheel  # type: ignore

    HAS_PYGEAR = True
    print("SpurGear: pygear imported successfully.")
except Exception as e:
    HAS_PYGEAR = False
    print("SpurGear: pygear import failed:", e)


class SpurGear(AdditiveFeature):
    """
    Spur Gear feature class that creates a gear on a stock shape.
    
    The gear is created by first adding a cylindrical base, then cutting
    tooth slots to form the gear teeth.
    """
    
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        """
        Initialize the SpurGear feature.
        
        Args:
            shape: Current B-Rep shape
            label_map: Face label mapping dictionary
            min_len: Minimum feature length
            clearance: Clearance parameter
            feat_names: Feature names list
        """
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = "blind"
        self.feat_type = "spur_gear"
        
        # Gear parameters (will be set during generation)
        self.num_teeth = None
        self.module = None
        self.pitch_diameter = None
        self.addendum_diameter = None
        self.dedendum_diameter = None
        self.face_width = None

    def _generate_gear_parameters(self, max_diameter):
        """
        Randomly generate valid gear parameters with retry logic.
        
        Implements retry logic as per Requirement 1.4:
        - Attempts to generate valid parameters up to 10 times
        - Returns None if all attempts fail, allowing graceful fallback
        
        Args:
            max_diameter: Maximum available diameter for the gear
            
        Returns:
            tuple: (num_teeth, module, pitch_diameter, addendum_diameter, dedendum_diameter)
                   or None if valid parameters cannot be generated after 10 attempts
        """
        # Get parameter ranges from parameters.py
        teeth_min = param.spur_gear_teeth_min
        teeth_max = param.spur_gear_teeth_max
        module_min = param.spur_gear_module_min
        module_max = param.spur_gear_module_max
        
        # Calculate available diameter
        d_avail = max_diameter - self.clearance

        # Check if any gear is possible
        # Min diameter = module_min * (teeth_min + 2)
        min_possible_diameter = module_min * (teeth_min + 2)
        if d_avail < min_possible_diameter:
            print(f"Warning: Available diameter {d_avail:.2f} too small for min gear {min_possible_diameter:.2f}")
            return None

        # Smart generation: constrain ranges to fit
        # m * (z + 2) <= d_avail  =>  m <= d_avail / (z + 2)
        # Max possible module (assuming min teeth)
        m_limit = d_avail / (teeth_min + 2)
        m_max_local = min(module_max, m_limit)

        if m_max_local < module_min:
            return None

        # Try to generate valid parameters
        # We can now safely pick a module in [module_min, m_max_local]
        # And then pick teeth count that fits

        max_attempts = 10
        for attempt in range(max_attempts):
            # Pick module
            module = random.uniform(module_min, m_max_local)

            # Calculate max teeth for this module
            # z <= d_avail / m - 2
            z_limit = int(d_avail / module - 2)
            z_max_local = min(teeth_max, z_limit)

            if z_max_local < teeth_min:
                continue

            # Pick teeth
            num_teeth = random.randint(teeth_min, z_max_local)

            # Calculate gear diameters
            pitch_diameter = module * num_teeth
            addendum_diameter = pitch_diameter + 2 * module
            dedendum_diameter = pitch_diameter - 2.5 * module
            
            # Double check validation (should pass by construction)
            if addendum_diameter <= d_avail + 1e-9:
                self.num_teeth = num_teeth
                self.module = module
                self.pitch_diameter = pitch_diameter
                self.addendum_diameter = addendum_diameter
                self.dedendum_diameter = dedendum_diameter
                
                return (num_teeth, module, pitch_diameter, 
                        addendum_diameter, dedendum_diameter)
        
        # Fallback to original random logic if smart logic somehow fails (unlikely)
        # or just return None
        print(f"Warning: Failed to generate valid gear parameters after {max_attempts} attempts. "
              f"Max diameter available: {max_diameter}, clearance: {self.clearance}")
        return None

    def _validate_parameters(self, num_teeth, module, max_diameter):
        """
        Validate gear parameters.
        
        Args:
            num_teeth: Number of teeth
            module: Module value
            max_diameter: Maximum available diameter
            
        Returns:
            bool: True if parameters are valid, False otherwise
        """
        # Check teeth range
        if num_teeth < param.spur_gear_teeth_min or num_teeth > param.spur_gear_teeth_max:
            return False
        
        # Check module range
        if module < param.spur_gear_module_min or module > param.spur_gear_module_max:
            return False
        
        # Calculate addendum diameter and check against max
        addendum_diameter = module * num_teeth + 2 * module
        if addendum_diameter > max_diameter - self.clearance:
            return False
        
        return True

    def _add_sketch(self, bound):
        """
        Create the circular sketch for the gear's cylindrical base.
        
        The sketch is a circle with diameter equal to the addendum diameter (da).
        The center is positioned at the center of the selected bound.
        
        Implements graceful failure handling as per Requirement 1.4:
        - Returns None if parameter generation fails after all retry attempts
        - This causes add_feature to return the original shape unchanged
        
        Args:
            bound: Boundary array with 5 elements:
                   bound[0-3]: Four corner points of the rectangular bound
                   bound[4]: Normal vector (depth direction)
            
        Returns:
            TopoDS_Face: Circular sketch face, or None if creation fails
        """
        # Calculate direction vectors and dimensions from bound
        dir_w = bound[2] - bound[1]
        dir_h = bound[0] - bound[1]
        width = np.linalg.norm(dir_w)
        height = np.linalg.norm(dir_h)
        
        # Validate bound dimensions
        if width <= 0 or height <= 0:
            print("Warning: Invalid bound dimensions (width or height <= 0)")
            return None
        
        # Normalize direction vectors
        dir_w = dir_w / width
        dir_h = dir_h / height
        
        # Calculate normal vector from cross product
        normal = np.cross(dir_w, dir_h)
        
        # Calculate maximum available diameter
        # The gear must fit within the bound, so max diameter is limited by the smaller dimension
        max_diameter = min(width, height)
        
        if max_diameter <= 0:
            print("Warning: Maximum diameter is <= 0")
            return None
        
        # Generate gear parameters based on available space
        # This includes retry logic (up to 10 attempts) as per Requirement 1.4
        params = self._generate_gear_parameters(max_diameter)
        
        if params is None:
            # Failed to generate valid parameters after all retry attempts
            # Return None to signal failure - add_feature will return original shape
            print("Warning: Gear parameter generation failed - returning original shape")
            return None
        
        # Parameters are now stored in self (num_teeth, module, pitch_diameter, 
        # addendum_diameter, dedendum_diameter)
        
        # Calculate center point of the bound (average of four corners)
        center = (bound[0] + bound[1] + bound[2] + bound[3]) / 4.0
        
        # Create the circular sketch with diameter = addendum_diameter
        # Radius is half of addendum_diameter
        radius = self.addendum_diameter / 2.0
        
        # Validate radius
        if radius <= 0:
            print("Warning: Calculated radius is <= 0")
            return None
        
        # Create OCC axis for the circle
        axis = gp_Ax2(
            gp_Pnt(center[0], center[1], center[2]),
            occ_utils.as_occ(normal, gp_Dir)
        )
        
        # Create the circle
        circ = gp_Circ(axis, radius)
        
        # Create edge from circle
        edge = BRepBuilderAPI_MakeEdge(circ, 0.0, 2.0 * math.pi).Edge()
        
        # Create wire from edge
        outer_wire = BRepBuilderAPI_MakeWire(edge).Wire()
        
        # Create face from wire
        face_maker = BRepBuilderAPI_MakeFace(outer_wire)
        
        return face_maker.Face()

    def _create_tooth_slot(self, center, normal, tooth_index, face_width):
        """
        Create a single tooth slot solid for cutting from the gear cylinder.
        
        The tooth slot is a simplified trapezoidal profile extruded along the gear axis.
        
        Args:
            center: numpy array, center point of the gear (3D coordinates)
            normal: numpy array, normal vector (axis direction of the gear)
            tooth_index: int, index of the tooth (0 to num_teeth-1)
            face_width: float, the height/depth of the gear (extrusion length)
            
        Returns:
            TopoDS_Shape: The tooth slot solid, or None if creation fails
        """
        if self.num_teeth is None or self.module is None:
            return None
        
        # Calculate tooth slot dimensions based on gear parameters
        # Slot depth = 1.25 × m (from addendum to dedendum)
        slot_depth = 1.25 * self.module
        
        # Slot width at pitch circle ≈ π × m / 2
        slot_width = math.pi * self.module / 2.0
        
        # Calculate angular position for this tooth slot
        # Angular position = 2π × i / z
        angular_position = 2.0 * math.pi * tooth_index / self.num_teeth
        
        # Calculate radii
        pitch_radius = self.pitch_diameter / 2.0
        addendum_radius = self.addendum_diameter / 2.0
        dedendum_radius = self.dedendum_diameter / 2.0
        
        # Normalize the normal vector
        normal = np.array(normal, dtype=np.float64)
        normal_len = np.linalg.norm(normal)
        if normal_len < 1e-10:
            return None
        normal = normal / normal_len
        
        # Create local coordinate system for the gear
        # Find two perpendicular vectors in the plane of the gear
        # Choose an arbitrary vector not parallel to normal
        if abs(normal[2]) < 0.9:
            arbitrary = np.array([0.0, 0.0, 1.0])
        else:
            arbitrary = np.array([1.0, 0.0, 0.0])
        
        # Create orthonormal basis
        u_vec = np.cross(normal, arbitrary)
        u_vec = u_vec / np.linalg.norm(u_vec)
        v_vec = np.cross(normal, u_vec)
        v_vec = v_vec / np.linalg.norm(v_vec)
        
        # Calculate the direction to the center of this tooth slot
        cos_angle = math.cos(angular_position)
        sin_angle = math.sin(angular_position)
        radial_dir = cos_angle * u_vec + sin_angle * v_vec
        
        # Calculate tangential direction (perpendicular to radial in the gear plane)
        tangent_dir = -sin_angle * u_vec + cos_angle * v_vec
        
        # Create simplified trapezoidal tooth slot profile
        # The slot is wider at the dedendum (root) and narrower at the addendum (tip)
        # We create 4 points forming a trapezoid
        
        # Half-width at different radii
        # At pitch circle: slot_width / 2
        # At addendum (outer): slightly wider (to make tooth narrower at tip)
        # At dedendum (inner): slightly narrower (to make tooth wider at root)
        half_width_pitch = slot_width / 2.0
        half_width_outer = half_width_pitch * 1.2  # Wider at top
        half_width_inner = half_width_pitch * 0.8  # Narrower at root

        # Calculate the 4 corner points of the trapezoidal slot profile
        # Points are in the plane perpendicular to the gear axis
        
        # Outer points (at addendum radius)
        outer_left = center + addendum_radius * radial_dir - half_width_outer * tangent_dir
        outer_right = center + addendum_radius * radial_dir + half_width_outer * tangent_dir
        
        # Inner points (at dedendum radius)
        inner_left = center + dedendum_radius * radial_dir - half_width_inner * tangent_dir
        inner_right = center + dedendum_radius * radial_dir + half_width_inner * tangent_dir
        
        # Create the trapezoidal face profile
        # Order: outer_left -> outer_right -> inner_right -> inner_left -> outer_left
        try:
            # Create vertices
            pnt_outer_left = gp_Pnt(outer_left[0], outer_left[1], outer_left[2])
            pnt_outer_right = gp_Pnt(outer_right[0], outer_right[1], outer_right[2])
            pnt_inner_right = gp_Pnt(inner_right[0], inner_right[1], inner_right[2])
            pnt_inner_left = gp_Pnt(inner_left[0], inner_left[1], inner_left[2])
            
            # Create edges
            edge1 = BRepBuilderAPI_MakeEdge(pnt_outer_left, pnt_outer_right).Edge()
            edge2 = BRepBuilderAPI_MakeEdge(pnt_outer_right, pnt_inner_right).Edge()
            edge3 = BRepBuilderAPI_MakeEdge(pnt_inner_right, pnt_inner_left).Edge()
            edge4 = BRepBuilderAPI_MakeEdge(pnt_inner_left, pnt_outer_left).Edge()
            
            # Create wire from edges
            wire_maker = BRepBuilderAPI_MakeWire()
            wire_maker.Add(edge1)
            wire_maker.Add(edge2)
            wire_maker.Add(edge3)
            wire_maker.Add(edge4)
            
            if not wire_maker.IsDone():
                return None
            
            wire = wire_maker.Wire()
            
            # Create face from wire
            face_maker = BRepBuilderAPI_MakeFace(wire)
            if not face_maker.IsDone():
                return None
            
            slot_face = face_maker.Face()
            
            # Extrude the face along the gear axis to create the slot solid
            # The extrusion should cover the full face width of the gear
            # We extrude in both directions to ensure full coverage
            extrusion_vec = gp_Vec(
                normal[0] * face_width * 1.1,  # Slightly longer to ensure full cut
                normal[1] * face_width * 1.1,
                normal[2] * face_width * 1.1
            )
            
            prism_maker = BRepPrimAPI_MakePrism(slot_face, extrusion_vec)
            if not prism_maker.IsDone():
                return None
            
            return prism_maker.Shape()
            
        except Exception as e:
            print(f"Error creating tooth slot {tooth_index}: {e}")
            return None

    @staticmethod
    def _merge_label_map(old_map, old_shape, new_shape, feat_idx):
        """
        Merge label maps after Boolean operations.
        
        Preserves labels for faces that remain unchanged from the original shape,
        and assigns the gear feature label to newly created faces.
        
        Args:
            old_map: Original label map {TopoDS_Face: int}
            old_shape: Original shape before Boolean operation
            new_shape: New shape after Boolean operation
            feat_idx: Feature index for new faces
            
        Returns:
            dict: New label map {TopoDS_Face: int}
        """
        new_labels = {}
        old_faces = occ_utils.list_face(old_shape)
        new_faces = occ_utils.list_face(new_shape)
        
        # Map old faces to new faces that are the same
        for of in old_faces:
            same = shape_factory.same_shape_in_list(of, new_faces)
            if same is not None:
                new_labels[same] = old_map.get(of, feat_idx)
                new_faces.remove(same)
        
        # Assign gear label to all new faces
        for nf in new_faces:
            new_labels[nf] = feat_idx
        
        return new_labels

    @staticmethod
    def _validate_topology(shape):
        """
        Validate that the shape has valid topology.
        
        Checks:
        1. Shape is not null
        2. Shape contains exactly one solid
        3. All faces are properly connected (valid B-Rep topology)
        
        Args:
            shape: TopoDS_Shape to validate
            
        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        # Check if shape is null
        if shape is None or shape.IsNull():
            return False, "Shape is null"
        
        # Use TopologyExplorer to check the number of solids
        topo = TopologyExplorer(shape)
        num_solids = topo.number_of_solids()
        
        # Validate: must have exactly one solid
        if num_solids == 0:
            return False, "Shape contains no solids"
        
        if num_solids > 1:
            return False, f"Shape contains {num_solids} solids instead of 1"
        
        # Check that faces exist and are properly connected
        num_faces = topo.number_of_faces()
        if num_faces == 0:
            return False, "Shape contains no faces"
        
        # Additional validation: check that all faces are valid
        try:
            for face in topo.faces():
                if face.IsNull():
                    return False, "Shape contains null faces"
        except Exception as e:
            return False, f"Error iterating faces: {e}"
        
        return True, None

    def _apply_feature(self, old_shape, old_labels, feat_type, feat_face, depth_dir):
        """
        Apply the gear feature by creating a cylindrical base and cutting tooth slots.
        
        This method implements robust error handling as per Requirements 4.4 and 6.3:
        1. Creates a cylindrical base using BRepFeat_MakePrism (fused with original shape)
        2. Cuts all tooth slots from the cylinder using BRepAlgoAPI_Cut
        3. Skips individual tooth slots that fail without stopping the entire process
        4. Validates the resulting topology
        5. Returns original shape if final result is invalid
        
        Args:
            old_shape: Original B-Rep shape
            old_labels: Original label map
            feat_type: Feature type string ("spur_gear")
            feat_face: The circular sketch face for the gear base
            depth_dir: Depth direction vector (normal * depth)
            
        Returns:
            tuple: (new_shape, new_labels) or (old_shape, old_labels) on failure
        """
        try:
            # Step 1: Create cylindrical base using BRepFeat_MakePrism
            # Use True for fuse mode (additive feature)
            feature_maker = BRepFeat_MakePrism()
            feature_maker.Init(old_shape, feat_face, TopoDS_Face(), 
                             occ_utils.as_occ(-depth_dir, gp_Dir), True, False)
            feature_maker.Build()
            
            depth = np.linalg.norm(depth_dir)
            feature_maker.Perform(depth)
            cylinder_shape = feature_maker.Shape()
            
            # Error handling: Check if cylinder creation resulted in null shape
            if cylinder_shape is None or cylinder_shape.IsNull():
                print("Error: Cylinder base creation failed - shape is null")
                return old_shape, old_labels
            
            # Get face mapping for label update
            fmap = shape_factory.map_face_before_and_after_feat(old_shape, feature_maker)
            base_labels = shape_factory.map_from_shape_and_name(
                fmap, old_labels, cylinder_shape, self.feat_names.index(feat_type))
            
            # Store the face width for tooth slot creation
            self.face_width = depth
            
            # Check if gear parameters are set
            if self.num_teeth is None or self.module is None:
                print("Error: Gear parameters not set")
                return cylinder_shape, base_labels
            
            # Step 2: Calculate center and normal for tooth slot creation
            # Get center from the bound (stored during _add_sketch)
            # We need to recalculate from the feat_face
            from OCC.Core.BRepGProp import brepgprop_SurfaceProperties
            from OCC.Core.GProp import GProp_GProps
            
            props = GProp_GProps()
            brepgprop_SurfaceProperties(feat_face, props)
            center_pnt = props.CentreOfMass()
            center = np.array([center_pnt.X(), center_pnt.Y(), center_pnt.Z()])
            
            # Normal is the depth direction normalized
            normal = depth_dir / depth if depth > 0 else np.array([0, 0, 1])
            
            # Step 3: Create and cut all tooth slots with error handling
            current_shape = cylinder_shape
            current_labels = base_labels
            successful_cuts = 0
            failed_cuts = 0
            
            for i in range(self.num_teeth):
                # Create tooth slot geometry
                tooth_slot = self._create_tooth_slot(center, normal, i, self.face_width)
                
                # Error handling: Skip if tooth slot creation failed
                if tooth_slot is None:
                    print(f"Warning: Tooth slot {i} creation returned None, skipping")
                    failed_cuts += 1
                    continue
                
                # Error handling: Check if tooth slot shape is null
                if tooth_slot.IsNull():
                    print(f"Warning: Tooth slot {i} creation resulted in null shape, skipping")
                    failed_cuts += 1
                    continue
                
                # Perform Boolean cut operation with error handling
                try:
                    cut_operation = BRepAlgoAPI_Cut(current_shape, tooth_slot)
                    cut_operation.Build()
                    
                    # Error handling: Check if Boolean operation completed
                    if not cut_operation.IsDone():
                        print(f"Warning: Boolean cut for tooth slot {i} did not complete, skipping")
                        failed_cuts += 1
                        continue
                    
                    new_shape = cut_operation.Shape()
                    
                    # Error handling: Check if result shape is null
                    if new_shape is None or new_shape.IsNull():
                        print(f"Warning: Boolean cut for tooth slot {i} resulted in null shape, skipping")
                        failed_cuts += 1
                        continue
                    
                    # Verify the cut didn't create multiple solids (intermediate check)
                    topo_check = TopologyExplorer(new_shape)
                    if topo_check.number_of_solids() > 1:
                        print(f"Warning: Boolean cut for tooth slot {i} created multiple solids, skipping")
                        failed_cuts += 1
                        continue
                    
                    # Update labels using merge function
                    current_labels = self._merge_label_map(
                        current_labels, current_shape, new_shape, 
                        self.feat_names.index(feat_type))
                    current_shape = new_shape
                    successful_cuts += 1
                    
                except Exception as e:
                    print(f"Warning: Exception during tooth slot {i} cut: {e}, skipping")
                    failed_cuts += 1
                    continue
            
            # Log summary of tooth slot operations
            if failed_cuts > 0:
                print(f"Tooth slot summary: {successful_cuts} successful, {failed_cuts} failed out of {self.num_teeth}")
            
            # Step 4: Final topology validation - ensure single solid
            is_valid, error_msg = self._validate_topology(current_shape)
            
            if not is_valid:
                print(f"Error: Final gear topology invalid - {error_msg}")
                # Return original shape as per Requirement 6.3
                return old_shape, old_labels
            
            # Check if we have at least some successful tooth cuts
            # If all cuts failed, the gear is just a cylinder which may not be desired
            if successful_cuts == 0 and self.num_teeth > 0:
                print("Warning: All tooth slot cuts failed - returning cylinder without teeth")
                # Still return the cylinder as it's a valid shape
            
            return current_shape, current_labels
        except Exception as e:
            print(f"Error in _apply_feature: {e}")
            # Return original shape on any unexpected error as per Requirement 6.3
            return old_shape, old_labels


    def _apply_pygear_feature(self, old_shape, old_labels, feat_type, bound, depth):
        """Create a full involute gear using pygear and fuse it with the stock."""

        try:
            if self.num_teeth is None or self.module is None:
                print("Error: Gear parameters not set for pygear.")
                return old_shape, old_labels

            # Build basic geardata for CylindricalGearWheel (normal module, width, teeth)
            geardata = {
                "z": int(self.num_teeth),
                "m_n": float(self.module),
                "b": float(depth),
            }

            self.face_width = float(depth)

            gear = CylindricalGearWheel(geardata)
            gear_solid = gear.makeOCCSolid()

            # Build placement frame from bound rectangle
            p0 = np.asarray(bound[0], dtype=np.float64)
            p1 = np.asarray(bound[1], dtype=np.float64)
            p2 = np.asarray(bound[2], dtype=np.float64)
            p3 = np.asarray(bound[3], dtype=np.float64)
            normal_vec = -np.asarray(bound[4], dtype=np.float64)  # face outward normal

            center = (p0 + p1 + p2 + p3) / 4.0

            dir_w = p2 - p1
            dir_h = p0 - p1
            w_len = np.linalg.norm(dir_w)
            h_len = np.linalg.norm(dir_h)
            n_len = np.linalg.norm(normal_vec)

            if w_len < 1e-9 or h_len < 1e-9 or n_len < 1e-9:
                print("Error: Invalid bound geometry for pygear placement.")
                return old_shape, old_labels

            dir_w /= w_len
            normal_vec /= n_len

            # Reconstruct orthogonal in-plane direction
            dir_h = np.cross(normal_vec, dir_w)
            h_len = np.linalg.norm(dir_h)
            if h_len < 1e-9:
                print("Error: Failed to construct orthonormal frame for pygear.")
                return old_shape, old_labels
            dir_h /= h_len

            origin = gp_Pnt(float(center[0]), float(center[1]), float(center[2]))
            z_dir = gp_Dir(float(normal_vec[0]), float(normal_vec[1]), float(normal_vec[2]))
            x_dir = gp_Dir(float(dir_w[0]), float(dir_w[1]), float(dir_w[2]))

            # Build 3D coordinate systems for transformation. pythonocc-core's
            # gp_Trsf.SetTransformation expects gp_Ax3, not gp_Ax2.
            target_ax3 = gp_Ax3(origin, z_dir, x_dir)
            source_ax3 = gp_Ax3(
                gp_Pnt(0.0, 0.0, 0.0),
                gp_Dir(0.0, 0.0, 1.0),
                gp_Dir(1.0, 0.0, 0.0),
            )

            trsf = gp_Trsf()
            trsf.SetTransformation(target_ax3, source_ax3)

            gear_trsf = BRepBuilderAPI_Transform(gear_solid, trsf, True)
            gear_world = gear_trsf.Shape()

            # Fuse gear with existing stock shape
            fuse_op = BRepAlgoAPI_Fuse(old_shape, gear_world)
            fuse_op.Build()
            if not fuse_op.IsDone():
                print("Error: BRepAlgoAPI_Fuse for pygear not completed.")
                return old_shape, old_labels

            fused_shape = fuse_op.Shape()
            if fused_shape is None or fused_shape.IsNull():
                print("Error: Fused shape is null after pygear fuse.")
                return old_shape, old_labels

            topo = TopologyExplorer(fused_shape)
            if topo.number_of_solids() != 1:
                print("Error: Fused shape has multiple solids after pygear fuse.")
                return old_shape, old_labels

            new_labels = self._merge_label_map(
                old_labels,
                old_shape,
                fused_shape,
                self.feat_names.index(feat_type),
            )

            print("SpurGear: pygear gear fused successfully.")
            return fused_shape, new_labels

        except Exception as e:
            print(f"Error in _apply_pygear_feature: {e}")
            return old_shape, old_labels


    def add_feature(self, bounds, find_bounds=True):
        """Create a spur gear on top of the stock using pygear.

        This implementation ignores the generic MachiningFeature bound/depth
        logic and instead:
        1) Reads the stock bounding box.
        2) Chooses gear parameters that fit within the top face.
        3) Calls pygear.CylindricalGearWheel.makeOCCSolid to create a full
           involute spur gear.
        4) Places the gear at the center of the top face and fuses it with
           the stock.

        If pygear is not available, it falls back to the base AdditiveFeature
        implementation (simple cylindrical pad).
        """

        # Fallback: no pygear installed or import failed
        if not HAS_PYGEAR:
            return super().add_feature(bounds, find_bounds)

        try:
            # Get bounding box of the current shape (typically the stock cube)
            xmin, ymin, zmin, xmax, ymax, zmax, dx, dy, dz = occ_utils.get_boundingbox(self.shape)

            # Available diameter on the top face, leave clearance from edges
            d_avail = min(dx, dy) - 2.0 * self.clearance
            if d_avail <= 0:
                print("Warning: Available diameter for spur gear <= 0")
                return self.shape, self.label_map, bounds

            # Generate gear parameters purely from available diameter
            params = self._generate_gear_parameters(d_avail)
            if params is None:
                return self.shape, self.label_map, bounds

            # Choose a reasonable face width: fraction of stock height but not
            # smaller than min_len
            depth = dz / 4.0 if dz > 0 else self.min_len
            depth = max(self.min_len, min(depth, dz))

            # Construct a synthetic rectangular bound on the top face. The
            # last element is -normal, following the convention used in
            # MachiningFeature._bound_inner (so that -bound[4] is the outward
            # normal).
            margin = self.clearance
            if dx <= 2.0 * margin or dy <= 2.0 * margin:
                margin = 0.0

            p0 = np.array([xmin + margin, ymin + margin, zmax], dtype=np.float64)
            p1 = np.array([xmin + margin, ymax - margin, zmax], dtype=np.float64)
            p2 = np.array([xmax - margin, ymax - margin, zmax], dtype=np.float64)
            p3 = np.array([xmax - margin, ymin + margin, zmax], dtype=np.float64)
            normal = np.array([0.0, 0.0, -1.0], dtype=np.float64)  # top face, outward normal +Z

            bound = np.array([p0, p1, p2, p3, normal])

            # Use pygear to create the actual involute gear and fuse it with stock
            shape, label_map = self._apply_pygear_feature(
                self.shape,
                self.label_map,
                self.feat_type,
                bound,
                depth,
            )

            topo = TopologyExplorer(shape)
            if topo.number_of_solids() > 1:
                return self.shape, self.label_map, bounds

            # Return the new shape and keep the synthetic bound for potential
            # visualization/debugging
            return shape, label_map, [bound]

        except Exception as e:
            print(e)
            return self.shape, self.label_map, bounds
