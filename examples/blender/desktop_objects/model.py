"""Synthetic desktop geometry requested during user feedback, not a photo reconstruction.

The agent authors shapes directly. There is no class whitelist or template loader.
"""
import math
import bpy


def box(ctx,oid,name,size,center,rgba,bevel=.002):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj=bpy.context.object;obj.name=name;obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.location=center
    if bevel:
        mod=obj.modifiers.new('Rounded corners','BEVEL');mod.width,mod.segments=bevel,2
    return ctx.add_part(oid,obj,rgba)


def cylinder(ctx,oid,name,radius,depth,center,rgba,axis='Z'):
    bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=radius,depth=depth)
    obj=bpy.context.object;obj.name=name;obj.location=center
    if axis=='X':obj.rotation_euler.y=math.pi/2
    if axis=='Y':obj.rotation_euler.x=math.pi/2
    return ctx.add_part(oid,obj,rgba)


def ring_body(ctx,oid,name,levels,rgba,segments=40):
    vertices=[]
    for z,rx,ry in levels:
        vertices.extend((rx*math.cos(i*2*math.pi/segments),ry*math.sin(i*2*math.pi/segments),z) for i in range(segments))
    n=segments
    faces=[(k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i) for k in range(len(levels)-1) for i in range(n)]
    faces.extend([tuple(reversed(range(n))),tuple((len(levels)-1)*n+i for i in range(n))])
    return ctx.add_mesh(oid,name,vertices,faces,rgba)


def keyboard(ctx):
    box(ctx,'keyboard_1','Keyboard housing',(.40,.14,.014),(0,0,-.002),[.07,.075,.085,1],.005)
    for row in range(6):
        for col in range(14):
            box(ctx,'keyboard_1',f'Main key {row+1}-{col+1}',(.017,.015,.004),(-.183+col*.021,-.05+row*.020,.007),[.55,.57,.60,1],.001)
    for row in range(5):
        for col in range(4):
            box(ctx,'keyboard_1',f'Numeric key {row+1}-{col+1}',(.015,.015,.004),(.117+col*.021,-.05+row*.021,.007),[.64,.66,.69,1],.001)


def shaker(ctx):
    black=[.035,.04,.045,1]
    ring_body(ctx,'shaker_1','Tapered black shaker cup',[
        (-.09,.030,.030),(-.083,.033,.033),(.045,.043,.043),(.065,.043,.043)],black)
    cylinder(ctx,'shaker_1','Screw lid',.045,.015,(0,0,.0725),[.07,.075,.08,1])
    box(ctx,'shaker_1','Drinking spout',(.028,.023,.014),(.012,0,.087),[.045,.05,.055,1],.004)
    bpy.ops.mesh.primitive_torus_add(major_segments=32,minor_segments=10,major_radius=.017,minor_radius=.004)
    handle=bpy.context.object;handle.name='Shaker carry loop';handle.location=(-.044,0,.055);handle.rotation_euler.x=math.pi/2
    ctx.add_part('shaker_1',handle,black)


def mouse(ctx):
    ring_body(ctx,'mouse_1','Curved mouse shell',[
        (-.015,.030,.048),(-.006,.032,.050),(.008,.027,.044),(.018,.016,.029),(.021,.003,.006)],
        [.17,.19,.22,1])
    for sign in (-1,1):
        box(ctx,'mouse_1',f'Mouse button {sign}',(.018,.027,.004),(sign*.014,.021,.015),[.21,.23,.26,1],.002)
    cylinder(ctx,'mouse_1','Scroll wheel',.006,.009,(0,.024,.019),[.05,.055,.06,1],'X')


def speaker(ctx):
    box(ctx,'speaker_1','Speaker enclosure',(.072,.065,.14),(0,0,0),[.075,.08,.09,1],.004)
    cylinder(ctx,'speaker_1','Woofer surround',.025,.004,(0,-.034,-.025),[.20,.21,.23,1],'Y')
    cylinder(ctx,'speaker_1','Woofer cone',.020,.005,(0,-.036,-.025),[.11,.12,.13,1],'Y')
    cylinder(ctx,'speaker_1','Tweeter surround',.014,.004,(0,-.034,.039),[.28,.29,.31,1],'Y')
    cylinder(ctx,'speaker_1','Tweeter dome',.010,.005,(0,-.036,.039),[.12,.13,.14,1],'Y')


def pen(ctx):
    cylinder(ctx,'pen_1','Pen barrel',.0045,.12,(0,0,0),[.025,.025,.025,1],'X')
    cylinder(ctx,'pen_1','Metal writing tip',.0028,.012,(.066,0,0),[.65,.67,.69,1],'X')
    cylinder(ctx,'pen_1','Rear ring',.0044,.008,(-.064,0,0),[.65,.67,.69,1],'X')
    box(ctx,'pen_1','Pen clip',(.032,.0015,.0015),(-.038,0,.0035),[.40,.42,.44,1],.0004)


def build(ctx):
    keyboard(ctx)
    shaker(ctx)
    mouse(ctx)
    speaker(ctx)
    pen(ctx)
