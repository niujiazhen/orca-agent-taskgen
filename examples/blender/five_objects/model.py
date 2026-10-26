"""Agent-authored five-object model. Blender 4.5, metres, object-local parts.

This example does not recognize a photograph. The agent interpreted the source
and selected these modeling operations and approximate dimensions.
"""
import math
import bpy


def box(ctx, oid, name, size, center, rgba, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.location = center
    if bevel:
        mod = obj.modifiers.new('Editable round edges', 'BEVEL')
        mod.width, mod.segments = bevel, 4
    return ctx.add_part(oid,obj,rgba)


def cylinder(ctx, oid, name, radius, depth, center, rgba, axis='Z'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth)
    obj = bpy.context.object
    obj.name = name
    obj.location = center
    if axis == 'X':
        obj.rotation_euler.y = math.pi/2
    mod = obj.modifiers.new('Rim bevel','BEVEL')
    mod.width,mod.segments = min(radius,depth)*.04,2
    return ctx.add_part(oid,obj,rgba)


def build(ctx):
    black=[.035,.035,.035,1]
    silver=[.65,.67,.69,1]
    white=[.94,.93,.88,1]
    green=[.08,.35,.19,1]
    cover=[.49,.49,.41,1]
    # Long axis along local X, matching the source's original pen convention.
    cylinder(ctx,'pen_1','Pen barrel',.0045,.116,(0,0,0),black,'X')
    cylinder(ctx,'pen_1','Silver writing tip',.003,.014,(.063,0,0),silver,'X')
    cylinder(ctx,'pen_1','Silver rear ring',.0044,.010,(-.063,0,0),silver,'X')
    cylinder(ctx,'pen_1','Dark rear cap',.004,.004,(-.068,0,0),black,'X')
    box(ctx,'pen_1','Pen clip',(.033,.0018,.0018),(-.037,0,.0034),silver,.0004)
    # Can shell plus inset lid, base rim and a visible pull tab.
    cylinder(ctx,'can_1','Can shell',.030,.111,(0,0,0),silver)
    cylinder(ctx,'can_1','Can base',.029,.004,(0,0,-.0555),silver)
    cylinder(ctx,'can_1','Can lid',.029,.004,(0,0,.0555),[.77,.78,.76,1])
    box(ctx,'can_1','Pull tab',(.018,.009,.001),(.002,0,.057),[.45,.46,.45,1],.002)
    # Separate rounded lid/body keep the editable charging-case seam visible.
    box(ctx,'case_1','Case body',(.055,.032,.017),(0,0,-.003),white,.007)
    box(ctx,'case_1','Case lid',(.055,.032,.0055),(0,0,.00875),white,.0025)
    box(ctx,'case_1','Lid seam',(.052,.030,.0005),(0,0,.00575),[.53,.53,.50,1],.0002)
    # Rigid tablet-cover approximation; grooves are visible raised/slim strips.
    box(ctx,'cover_1','Rounded tablet cover',(.290,.190,.011),(0,0,-.0005),cover,.004)
    for y in (-.031,.031):
        box(ctx,'cover_1','Cover fold line',(.278,.0012,.001),(0,y,.0055),[.38,.38,.32,1],.0003)
    # The gum container has a rounded body, separate cap and a simple colored panel.
    box(ctx,'gum_1','Gum container body',(.060,.050,.084),(0,0,-.003),green,.009)
    box(ctx,'gum_1','Gum container lid',(.060,.050,.006),(0,0,.042),[.08,.20,.11,1],.002)
    box(ctx,'gum_1','Light label panel',(.043,.0005,.041),(0,-.025,.002),[.75,.82,.67,1],.002)
