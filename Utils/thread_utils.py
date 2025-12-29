import math
from OCC.Core.gp import gp_Pnt2d, gp_Dir2d, gp_Ax2d, gp_Ax3, gp_Vec2d
from OCC.Core.Geom import Geom_CylindricalSurface
from OCC.Core.Geom2d import Geom2d_Ellipse, Geom2d_TrimmedCurve
from OCC.Core.GCE2d import GCE2d_MakeSegment
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCC.Core.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCC.Core.BRepLib import breplib_BuildCurves3d

def create_thread_solid(axis, radius, height):
    """
    Creates a thread solid based on CreteThreadWire logic.
    """
    # Surfaces
    r_inner = radius * 0.99
    r_outer = radius * 1.05

    ax3 = gp_Ax3(axis.Location(), axis.Direction())

    cyl1 = Geom_CylindricalSurface(ax3, r_inner)
    cyl2 = Geom_CylindricalSurface(ax3, r_outer)

    # 2D Curves
    # Center at (2*PI, height/2)
    aPnt = gp_Pnt2d(2.0 * math.pi, height / 2.0)
    aDir = gp_Dir2d(2.0 * math.pi, height / 4.0)
    anAx2d = gp_Ax2d(aPnt, aDir)

    aMajor = 2.0 * math.pi
    aMinor = height / 10.0

    anEllipse1 = Geom2d_Ellipse(anAx2d, aMajor, aMinor)
    anEllipse2 = Geom2d_Ellipse(anAx2d, aMajor, aMinor / 4.0)

    anArc1 = Geom2d_TrimmedCurve(anEllipse1, 0, math.pi)
    anArc2 = Geom2d_TrimmedCurve(anEllipse2, 0, math.pi)

    # Segment closing the loop
    anEllipsePnt1 = anEllipse1.Value(0.0)
    anEllipsePnt2 = anEllipse1.Value(math.pi)
    aSegment = GCE2d_MakeSegment(anEllipsePnt1, anEllipsePnt2).Value()

    # Edges and Wires
    anEdge1OnSurf1 = BRepBuilderAPI_MakeEdge(anArc1, cyl1).Edge()
    anEdge2OnSurf1 = BRepBuilderAPI_MakeEdge(aSegment, cyl1).Edge()

    anEdge1OnSurf2 = BRepBuilderAPI_MakeEdge(anArc2, cyl2).Edge()
    anEdge2OnSurf2 = BRepBuilderAPI_MakeEdge(aSegment, cyl2).Edge()

    threadingWire1 = BRepBuilderAPI_MakeWire(anEdge1OnSurf1, anEdge2OnSurf1).Wire()
    threadingWire2 = BRepBuilderAPI_MakeWire(anEdge1OnSurf2, anEdge2OnSurf2).Wire()

    breplib_BuildCurves3d(threadingWire1)
    breplib_BuildCurves3d(threadingWire2)

    # ThruSections
    aTool = BRepOffsetAPI_ThruSections(True)
    aTool.AddWire(threadingWire1)
    aTool.AddWire(threadingWire2)
    aTool.CheckCompatibility(False)

    return aTool.Shape()

