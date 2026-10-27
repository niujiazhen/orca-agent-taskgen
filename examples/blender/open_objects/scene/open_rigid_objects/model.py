"""Synthetic open-catalog fixture: five rigid shapes, no object-template registry.

These are authored examples, not recognition results from a real photograph.
The same build(ctx) contract accepts a new modeling script for any rigid label.
"""
import math
import bpy


def box(ctx, oid, name, dimensions, position, rgba, bevel=.002):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj=bpy.context.object;obj.name=name;obj.dimensions=dimensions
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.location=position
    if bevel:
        modifier=obj.modifiers.new('Editable rounded edges','BEVEL')
        modifier.width,modifier.segments=bevel,3
    return ctx.add_part(oid,obj,rgba)


def cylinder(ctx,oid,name,radius,depth,position,rgba):
    bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=radius,depth=depth)
    obj=bpy.context.object;obj.name=name;obj.location=position
    return ctx.add_part(oid,obj,rgba)


def torus(ctx,oid,name,radius,tube,position,rgba,vertical=False):
    bpy.ops.mesh.primitive_torus_add(major_segments=40,minor_segments=10,major_radius=radius,minor_radius=tube)
    obj=bpy.context.object;obj.name=name;obj.location=position
    if vertical:obj.rotation_euler.x=math.pi/2
    return ctx.add_part(oid,obj,rgba)


def extruded_polygon(ctx,oid,name,profile,low,high,rgba):
    n=len(profile)
    vertices=[(x,y,z) for z in (low,high) for x,y in profile]
    faces=[tuple(reversed(range(n))),tuple(n+i for i in range(n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return ctx.add_mesh(oid,name,vertices,faces,rgba)


def cup(ctx):
    n=40; rings=[(.035,-.04),(.035,.04),(.030,.04),(.030,-.034)]
    vertices=[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n),z) for r,z in rings for i in range(n)]
    faces=[(k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i) for k in range(3) for i in range(n)]
    faces.extend([tuple(reversed(range(n))),tuple(3*n+i for i in range(n))])
    ctx.add_mesh('cup_1','Open cup walls and base',vertices,faces,[.16,.46,.74,1])
    torus(ctx,'cup_1','Loop handle',.024,.006,(.044,0,0),[.16,.46,.74,1],True)


def scissors(ctx):
    steel=[.68,.71,.74,1]; grip=[.12,.43,.24,1]
    blade=[(-.010,.003),(.085,.025),(.075,.012),(.005,-.004)]
    extruded_polygon(ctx,'scissors_1','Upper tapered blade',blade,-.001,.003,steel)
    extruded_polygon(ctx,'scissors_1','Lower tapered blade',[(x,-y) for x,y in reversed(blade)],-.003,.001,steel)
    for sign in (-1,1):
        torus(ctx,'scissors_1',f'Finger loop {sign}',.018,.004,(-.045,sign*.024,0),grip)
        obj=box(ctx,'scissors_1',f'Grip bridge {sign}',(.035,.009,.006),(-.020,sign*.012,0),grip)
        obj.rotation_euler.z=-sign*.35
    cylinder(ctx,'scissors_1','Central pivot',.008,.008,(0,0,0),[.35,.37,.39,1])


def remote(ctx):
    box(ctx,'remote_1','Rounded remote housing',(.056,.145,.020),(0,0,-.001),[.07,.075,.085,1],.008)
    box(ctx,'remote_1','Red power button',(.009,.009,.002),(-.016,.055,.010),[.75,.08,.06,1],.001)
    for row in range(5):
        for col in range(3):
            box(ctx,'remote_1',f'Key row {row+1} column {col+1}',(.009,.010,.002),((col-1)*.016,.030-row*.019,.010),[.62,.64,.68,1],.002)


def irregular_container(ctx):
    n=40
    levels=[(-.045,.026),(-.035,.037),(.020,.041),(.030,.025),(.037,.014)]
    vertices=[]
    for z,r in levels:
        for i in range(n):
            angle=i*2*math.pi/n
            # A gently asymmetric, noncircular body with a narrowed neck.
            vertices.append((r*1.15*math.cos(angle)+.005*(z+.045)/.082,
                             r*.80*math.sin(angle)*(1+.09*math.cos(angle)),z))
    faces=[(k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i) for k in range(len(levels)-1) for i in range(n)]
    faces.extend([tuple(reversed(range(n))),tuple((len(levels)-1)*n+i for i in range(n))])
    ctx.add_mesh('container_1','Asymmetric bottle shoulders and body',vertices,faces,[.86,.42,.12,1])
    cylinder(ctx,'container_1','Bottle cap',.016,.012,(.005,0,.043),[.19,.22,.23,1])


def nut(ctx):
    n=6;rings=[(.032,-.009),(.032,.009),(.014,.009),(.014,-.009)]
    vertices=[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n),z) for r,z in rings for i in range(n)]
    faces=[(k*n+i,k*n+(i+1)%n,((k+1)%4)*n+(i+1)%n,((k+1)%4)*n+i) for k in range(4) for i in range(n)]
    ctx.add_mesh('nut_1','Hexagonal outer body and central aperture',vertices,faces,[.60,.63,.67,1])


def build(ctx):
    cup(ctx)
    scissors(ctx)
    remote(ctx)
    irregular_container(ctx)
    nut(ctx)
