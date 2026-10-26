"""Synthetic hollow cup and handle: visible concavities vs one collision hull."""
import math
import bpy


def build(ctx):
    segments=48
    # A watertight cup shell, with an open top and a closed bottom.
    rings=[(.035,-.04),(.035,.04),(.030,.04),(.030,-.034)]
    vertices=[(r*math.cos(2*math.pi*i/segments),r*math.sin(2*math.pi*i/segments),z) for r,z in rings for i in range(segments)]
    faces=[]
    for ring in range(3):
        for i in range(segments):
            j=(i+1)%segments
            faces.append((ring*segments+i,ring*segments+j,(ring+1)*segments+j,(ring+1)*segments+i))
    faces.append(tuple(reversed(range(segments))))
    faces.append(tuple(3*segments+i for i in range(segments)))
    mesh=bpy.data.meshes.new('Cup shell mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    shell=bpy.data.objects.new('Open cup shell',mesh);bpy.context.scene.collection.objects.link(shell)
    ctx.add_part('cup_1',shell,[.25,.48,.72,1])
    bpy.ops.mesh.primitive_torus_add(major_segments=48,minor_segments=12,location=(.044,0,0),major_radius=.025,minor_radius=.006)
    handle=bpy.context.object;handle.name='Cup handle';handle.rotation_euler.x=math.pi/2
    ctx.add_part('cup_1',handle,[.25,.48,.72,1])
