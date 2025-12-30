import random
import math
import numpy as np

from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCC.Core.gp import gp_Pnt, gp_Dir, gp_Ax2
from OCC.Core.TopoDS import TopoDS_Face

import Utils.occ_utils as occ_utils
import Utils.shape_factory as shape_factory
from Features.machining_features import AdditiveFeature


class Gear(AdditiveFeature):
    """
    Spur gear feature class.
    Generates an involute spur gear as an additive feature.
    """
    def __init__(self, shape, label_map, min_len, clearance, feat_names):
        super().__init__(shape, label_map, min_len, clearance, feat_names)
        self.shifter_type = 4
        self.bound_type = 4
        self.depth_type = "blind"
        self.feat_type = "gear"
    
    def _generate_gear_profile(self, center, normal, module, num_teeth, pressure_angle=20.0):
        """
        Generate a simplified gear profile using a combination of circles.
        This creates a simplified spur gear approximation.
        
        :param center: Center point of the gear (numpy array)
        :param normal: Normal direction of the gear face (numpy array)
        :param module: Gear module (pitch diameter / number of teeth)
        :param num_teeth: Number of teeth
        :param pressure_angle: Pressure angle in degrees (default 20°)
        :return: TopoDS_Face representing the gear profile
        """
        # Calculate gear parameters
        pressure_angle_rad = math.radians(pressure_angle)
        
        # Standard gear formulas
        pitch_radius = (module * num_teeth) / 2.0
        addendum = module  # Height of tooth above pitch circle
        dedendum = 1.25 * module  # Depth of tooth below pitch circle
        outer_radius = pitch_radius + addendum
        root_radius = pitch_radius - dedendum
        
        # Create coordinate transformation
        normal_normalized = normal / np.linalg.norm(normal)
        
        # Create arbitrary perpendicular vector
        if abs(normal_normalized[0]) < 0.9:
            temp = np.array([1.0, 0.0, 0.0])
        else:
            temp = np.array([0.0, 1.0, 0.0])
        
        v1 = np.cross(normal_normalized, temp)
        v1 = v1 / np.linalg.norm(v1)
        v2 = np.cross(normal_normalized, v1)
        
        # Create a simplified gear profile by creating teeth as triangular notches
        # on a circular base
        angular_pitch = 2.0 * math.pi / num_teeth
        
        # Create points around the circle with teeth approximation
        points_3d = []
        num_points_per_tooth = 8
        
        for tooth in range(num_teeth):
            base_angle = tooth * angular_pitch
            
            # For each tooth, create a simplified profile:
            # 1. Root (dedendum)
            # 2. Rising edge
            # 3. Top (addendum)  
            # 4. Falling edge
            
            for i in range(num_points_per_tooth):
                t = i / num_points_per_tooth
                angle = base_angle + t * angular_pitch
                
                # Create a simple tooth profile variation
                # At tooth center (t=0.5), radius is maximum (outer_radius)
                # At tooth edges (t=0, t=1), radius is minimum (root_radius)
                tooth_factor = math.sin(t * math.pi)  # 0 at edges, 1 at center
                radius = root_radius + tooth_factor * (outer_radius - root_radius)
                
                x_2d = radius * math.cos(angle)
                y_2d = radius * math.sin(angle)
                
                # Transform to 3D
                p3d = center + x_2d * v1 + y_2d * v2
                points_3d.append(gp_Pnt(p3d[0], p3d[1], p3d[2]))
        
        # Create edges and wire
        wire_builder = BRepBuilderAPI_MakeWire()
        for i in range(len(points_3d)):
            next_i = (i + 1) % len(points_3d)
            try:
                edge = BRepBuilderAPI_MakeEdge(points_3d[i], points_3d[next_i]).Edge()
                wire_builder.Add(edge)
            except:
                continue
        
        if not wire_builder.IsDone():
            return None
            
        gear_wire = wire_builder.Wire()
        
        try:
            face_maker = BRepBuilderAPI_MakeFace(gear_wire)
            if face_maker.IsDone():
                return face_maker.Face()
        except:
            pass
        
        return None

    def _add_sketch(self, bound):
        """
        Create a gear profile sketch.
        
        :param bound: Boundary rectangle for placing the gear
        :return: TopoDS_Face representing the gear profile
        """
        dir_w = bound[2] - bound[1]
        dir_h = bound[0] - bound[1]
        width = np.linalg.norm(dir_w)
        height = np.linalg.norm(dir_h)
        
        if width <= 0 or height <= 0:
            return None
        
        dir_w = dir_w / width
        dir_h = dir_h / height
        normal = np.cross(dir_w, dir_h)
        
        # Calculate maximum gear size that fits in the bound
        max_radius = min(width / 2.0, height / 2.0)
        if max_radius <= self.min_len:
            return None
        
        # Leave clearance
        max_radius = max_radius - self.clearance
        
        # Determine gear parameters
        # Module: size of teeth (typically 1-10mm for small gears)
        module = max(1.0, self.min_len / 2.0)
        
        # Number of teeth based on maximum radius
        # pitch_radius = module * num_teeth / 2
        # So: num_teeth = 2 * pitch_radius / module
        num_teeth = int(2.0 * max_radius / module)
        
        # Ensure at least 8 teeth for a reasonable gear
        if num_teeth < 8:
            num_teeth = 8
            # Adjust module to fit
            module = 2.0 * max_radius / num_teeth
        
        # Limit to reasonable number of teeth
        if num_teeth > 100:
            num_teeth = 100
            module = 2.0 * max_radius / num_teeth
        
        center = (bound[0] + bound[1] + bound[2] + bound[3]) / 4.0
        
        # Create simplified gear profile
        gear_face = self._generate_gear_profile(center, normal, module, num_teeth)
        
        if gear_face is not None:
            return gear_face
        
        # Fallback to simple circular gear representation
        # This creates a cylinder as a placeholder
        axis = gp_Ax2(gp_Pnt(center[0], center[1], center[2]), 
                     occ_utils.as_occ(normal, gp_Dir))
        
        # Use 70% of max radius for the gear body
        gear_radius = max_radius * 0.7
        
        try:
            from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
            from OCC.Core.gp import gp_Circ
            
            circ = gp_Circ(axis, gear_radius)
            edge = BRepBuilderAPI_MakeEdge(circ, 0.0, 2.0 * math.pi).Edge()
            outer_wire = BRepBuilderAPI_MakeWire(edge).Wire()
            
            face_maker = BRepBuilderAPI_MakeFace(outer_wire)
            return face_maker.Face()
        except:
            return None
