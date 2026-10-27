"""Standalone worker executed by Blender 4.5's bundled Python, not package Python.

Model scripts implement build(ctx). Add every visible part with
ctx.add_part(object_id, mesh_object, rgba). Each root is one rigid object.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import runpy
import shutil
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path, root):
    return {"file":path.relative_to(root).as_posix(), "sha256":sha(path)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def color(material, fallback):
    if material is None:
        return list(fallback)
    rgba = list(material.diffuse_color)
    if material.use_nodes:
        nodes = [n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
        require(len(nodes) == 1, f"{material.name}: use one Principled BSDF with a constant Base Color")
        base = nodes[0].inputs['Base Color']
        require(not base.is_linked, f"{material.name}: photo textures/linked Base Color are not supported")
        rgba = list(base.default_value)
        require(not nodes[0].inputs['Alpha'].is_linked and abs(nodes[0].inputs['Alpha'].default_value-1) < 1e-6,
                f"{material.name}: transparent materials are not supported")
    require(len(rgba) == 4 and all(math.isfinite(x) and 0 <= x <= 1 for x in rgba) and abs(rgba[3]-1) < 1e-6,
            f"{material.name}: use finite opaque base colors")
    return rgba


def material(name, rgba):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = rgba
    return mat


class BuildContext:
    def __init__(self, plan):
        self.plan = plan
        self.objects = {}
        for item in plan['objects']:
            root = bpy.data.objects.new(item['id'], None)
            bpy.context.scene.collection.objects.link(root)
            root['orca_id'] = item['id']
            root.empty_display_size = .015
            root.location = item['position']
            root.rotation_mode = 'QUATERNION'
            root.rotation_quaternion = item.get('quaternion', [1,0,0,0])
            self.objects[item['id']] = root

    def add_part(self, object_id, mesh_object, rgba=None):
        require(mesh_object.type == 'MESH', 'add_part requires a mesh object')
        require(object_id in self.objects, f'Unregistered object ID: {object_id}')
        mesh_object.parent = self.objects[object_id]
        mesh_object.matrix_parent_inverse = Matrix.Identity(4)
        if rgba is not None:
            mesh_object.data.materials.clear()
            mesh_object.data.materials.append(material(mesh_object.name, rgba))
        return mesh_object

    def add_mesh(self, object_id, name, vertices, faces, rgba=None):
        """Create an agent-defined mesh; no object-class/template lookup occurs."""
        require(object_id in self.objects, f'Unregistered object ID: {object_id}')
        require(vertices and faces, f'{name}: vertices and faces are required')
        require(all(len(v) == 3 and all(math.isfinite(x) for x in v) for v in vertices),
                f'{name}: vertices must be finite XYZ coordinates')
        require(all(len(f) >= 3 and all(isinstance(i,int) and 0 <= i < len(vertices) for i in f) for f in faces),
                f'{name}: faces must contain valid vertex indices')
        mesh = bpy.data.meshes.new(name+' mesh')
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name,mesh)
        bpy.context.scene.collection.objects.link(obj)
        return self.add_part(object_id,obj,rgba)


def setup_display(plan, workspace):
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    table = plan['table']
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,table['top_z']-table['dimensions'][2]/2))
    obj = bpy.context.object
    obj.name = 'ORCA_TABLE'
    obj.dimensions = table['dimensions']
    obj['orca_role'] = 'table'
    obj.data.materials.append(material('Table', table.get('rgba',[.85,.83,.78,1])))
    image = bpy.data.images.load(str(workspace/'source.png'))
    image.pack()
    image.filepath = '//source.png'
    ref = bpy.data.objects.new('SOURCE_PHOTO_REFERENCE', None)
    scene.collection.objects.link(ref)
    ref.empty_display_type = 'IMAGE'
    ref.data = image
    ref.location = (-.55,0,table['top_z'])
    ref.empty_display_size = .45
    ref['orca_role'] = 'reference'
    ref.hide_render = True
    bpy.ops.object.camera_add(location=(.6,-.8,.9))
    camera = bpy.context.object
    camera.name = 'PREVIEW_CAMERA'
    camera.rotation_euler = (Vector((0,0,table['top_z']))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = max(table['dimensions'][:2])*1.5
    scene.camera = camera
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.show_shadows = True
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 640,480,100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = '//blender_preview.png'
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.clip_start = .001
                space.region_3d.view_location = (0,0,table['top_z'])
                space.region_3d.view_distance = .85
                space.shading.type = 'SOLID'
                space.shading.color_type = 'MATERIAL'
    return obj


def roots_and_parts(plan):
    expected = {o['id'] for o in plan['objects']}
    roots = {}
    for obj in bpy.context.scene.objects:
        if 'orca_id' in obj:
            oid = obj['orca_id']
            require(oid in expected, f'Unregistered object ID: {oid}')
            require(oid not in roots, f'Duplicate object ID: {oid}')
            roots[oid] = obj
    require(set(roots) == expected, f'Missing object IDs: {sorted(expected-set(roots))}')
    parts = defaultdict(list)
    tables = []
    for obj in bpy.context.scene.objects:
        if obj.type not in ('MESH','CURVE','SURFACE','FONT','META','VOLUME','POINTCLOUD'):
            continue
        if obj.get('orca_role') == 'table':
            tables.append(obj)
            continue
        ancestor = obj
        while ancestor is not None and 'orca_id' not in ancestor:
            ancestor = ancestor.parent
        require(ancestor is not None, f'Unregistered geometry: {obj.name}; parent it to a registered object root')
        require(obj.type == 'MESH', f'{obj.name}: convert this part to a mesh before export')
        require(not obj.hide_render, f'{obj.name}: hidden render parts must be removed or made visible before export')
        parts[ancestor['orca_id']].append(obj)
    require(len(tables) == 1, 'Exactly one ORCA tabletop is required')
    for oid in expected:
        require(parts[oid], f'{oid}: no mesh parts remain')
    return roots, parts, tables[0]


def mesh_data(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    require(mesh is not None and len(mesh.vertices), f'{obj.name}: empty evaluated mesh')
    mesh.calc_loop_triangles()
    return evaluated, mesh


def write_obj(path, vertices, faces):
    require(vertices and faces, f'{path.name}: empty mesh')
    require(all(all(math.isfinite(x) for x in v) for v in vertices), f'{path.name}: non-finite vertices')
    with path.open('w',encoding='utf-8') as f:
        f.write('# ORCA: metres, Z-up, triangulated object-local mesh\n')
        for v in vertices:
            f.write('v '+' '.join(f'{x:.12g}' for x in v)+'\n')
        for face in faces:
            f.write('f '+' '.join(str(i+1) for i in face)+'\n')


def collision_hull(vertices):
    bm = bmesh.new()
    try:
        for v in vertices:
            bm.verts.new(v)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-8)
        bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
        unused = [v for v in bm.verts if not v.link_faces]
        if unused:
            bmesh.ops.delete(bm, geom=unused, context='VERTS')
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        require(len(bm.verts) >= 4 and abs(bm.calc_volume()) > 1e-12, 'Collision hull has no solid volume')
        bm.verts.ensure_lookup_table()
        indices = {v:i for i,v in enumerate(bm.verts)}
        return [tuple(v.co) for v in bm.verts], [[indices[v] for v in f.verts] for f in bm.faces]
    finally:
        bm.free()


def export_project(workspace):
    bpy.ops.wm.open_mainfile(filepath=str(workspace/'project.blend'), load_ui=False, use_scripts=False)
    plan = json.loads((workspace/'object_plan.json').read_text())
    require(sha(workspace/'source.png') == plan['source_sha256'], 'Source image changed since build; create a new workspace')
    require(bpy.context.scene.unit_settings.scale_length == 1, 'Keep scene scale at one metre; scale the objects instead')
    roots, parts, table_obj = roots_and_parts(plan)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    # The tabletop remains a centered, horizontal slab; object transforms are unrestricted.
    tm = table_obj.matrix_world
    require(abs(tm.translation.x) < 1e-6 and abs(tm.translation.y) < 1e-6 and tm.to_quaternion().angle < 1e-6,
            'Keep the tabletop centered and horizontal')
    table_dims = list(table_obj.dimensions)
    table_eval, table_mesh = mesh_data(table_obj,depsgraph)
    try:
        points = [table_eval.matrix_world @ v.co for v in table_mesh.vertices]
        lower = [min(v[i] for v in points) for i in range(3)]
        upper = [max(v[i] for v in points) for i in range(3)]
        require(all(any(abs(v[i]-end) < 1e-6 for end in (lower[i],upper[i])) for v in points for i in range(3)),
                'Keep the tabletop an unmodified rectangular slab; custom shapes are supported for the registered objects')
    finally:
        table_eval.to_mesh_clear()
    table = dict(plan['table'], dimensions=table_dims, top_z=float(tm.translation.z+table_dims[2]/2),
                 rgba=color(table_obj.active_material, plan['table'].get('rgba',[.85,.83,.78,1])))
    table['provenance'] = {k:'blender_saved' for k in ('dimensions','top_z','rgba')}
    table['provenance']['friction'] = 'user_input'
    output = workspace/'export'
    output.mkdir(exist_ok=True)
    assets = output/'assets'
    assets.mkdir(exist_ok=True)
    objects, stats = [], []
    for item in plan['objects']:
        oid = item['id']
        root = roots[oid]
        position = root.matrix_world.translation
        quaternion = root.matrix_world.to_quaternion().normalized()
        rigid = Matrix.LocRotScale(position,quaternion,Vector((1,1,1)))
        inverse = rigid.inverted()
        all_vertices, visuals, triangle_count = [], [], 0
        visual_groups = defaultdict(lambda: {'vertices':[], 'faces':[]})
        for part_index,obj in enumerate(parts[oid]):
            evaluated, mesh = mesh_data(obj,depsgraph)
            try:
                transform = inverse @ evaluated.matrix_world
                vertices = [tuple(transform @ v.co) for v in mesh.vertices]
                all_vertices.extend(vertices)
                by_color = defaultdict(list)
                for triangle in mesh.loop_triangles:
                    mat = evaluated.material_slots[triangle.material_index].material if triangle.material_index < len(evaluated.material_slots) else None
                    rgba = color(mat,item.get('rgba',[.5,.5,.5,1]))
                    if mat is not None:
                        mat.diffuse_color = rgba  # Workbench preview uses viewport colors.
                    face = list(triangle.vertices)
                    a,b,c = (Vector(vertices[i]) for i in face)
                    if (b-a).cross(c-a).length < 1e-16:
                        continue  # Modifier tessellation can leave zero-area faces.
                    if transform.determinant() < 0:
                        face.reverse()  # Keep mirrored edits, with outward winding.
                    by_color[tuple(rgba)].append(face)
                triangle_count += sum(len(faces) for faces in by_color.values())
                for rgba,faces in by_color.items():
                    group = visual_groups[rgba]
                    used = sorted({i for f in faces for i in f})
                    offset = len(group['vertices'])
                    remap = {old:offset+new for new,old in enumerate(used)}
                    group['vertices'].extend(vertices[i] for i in used)
                    group['faces'].extend([remap[i] for i in face] for face in faces)
            finally:
                evaluated.to_mesh_clear()
        require(triangle_count <= 20_000, f'{oid}: {triangle_count} triangles exceeds 20,000; simplify in Blender and save')
        for color_index,(rgba,group) in enumerate(visual_groups.items()):
            path = assets/f'{oid}_visual_{color_index}.obj'
            write_obj(path,group['vertices'],group['faces'])
            visuals.append(record(path,output)|{'rgba':list(rgba)})
        require(len(visuals) <= 128, f'{oid}: too many visual/material parts (maximum 128)')
        hull_vertices,hull_faces = collision_hull(all_vertices)
        collision = assets/f'{oid}_collision.obj'
        write_obj(collision,hull_vertices,hull_faces)
        lo = [min(v[i] for v in hull_vertices) for i in range(3)]
        hi = [max(v[i] for v in hull_vertices) for i in range(3)]
        objects.append({'id':oid,'name':item['name'],'category':'mesh','dimensions':[hi[i]-lo[i] for i in range(3)],
            'position':list(position),'quaternion':list(quaternion),'rgba':visuals[0]['rgba'],
            'mass':item.get('mass',.04),'friction':item.get('friction',[1.2,.01,.001]),'support':'table','image_bbox':item['image_bbox'],
            'provenance':{'geometry':'blender_saved','position':'blender_saved','dimensions':'blender_saved','rgba':'blender_saved',
                          'mass':'user_input' if 'mass' in item else 'catalog_default','friction':'user_input' if 'friction' in item else 'catalog_default'},
            'geometry':{'visuals':visuals,'collision':record(collision,output),'bounds':[lo,hi],'collision_method':'convex_hull'}})
        stats.append({'id':oid,'name':item['name'],'geometry_source':'saved_blender_mesh',
                      'visual_parts':[p.name for p in parts[oid]],
                      'visual_triangles':triangle_count,'collision_vertices':len(hull_vertices),
                      'collision_warning':'One convex hull per rigid body: holes and concavities may be filled.'})
    for name in ('source.png','model.py','object_plan.json','project.blend'):
        shutil.copy2(workspace/name,output/name)
    # Re-render from the saved project, so the preview includes user edits.
    bpy.context.scene.render.filepath = str(output/'blender_preview.png')
    bpy.ops.render.render(write_still=True)
    report={'status':'exported','blender_version':bpy.app.version_string,'saved_project_sha256':sha(workspace/'project.blend'),
            'manual_review':'not inferred; exporter only reads saved disk state','objects':stats}
    report_text = json.dumps(report,indent=2)
    (workspace/'export_report.json').write_text(report_text,encoding='utf-8')
    (output/'export_report.json').write_text(report_text,encoding='utf-8')
    spec = {'schema_version':2,'scene_id':plan['scene_id'],'source':{'image':'source.png','sha256':sha(output/'source.png')},
            'table':table,'objects':objects,'scale_reference':None,'notes':plan.get('notes',[])+[
                'Approximate geometry authored by the agent and exported from the saved Blender project.',
                'One convex collision hull per object; mass and friction are explicit assumptions. No RL task is included.',
                'Final MuJoCo visual confirmation remains pending.'],
            'questions':[],'confirmed':False,'artifacts':[record(output/n,output) for n in ('model.py','object_plan.json','project.blend','blender_preview.png','export_report.json')]}
    # JSON is a valid YAML subset and needs no PyYAML in Blender's Python.
    (output/'scene_spec.yaml').write_text(json.dumps(spec,indent=2),encoding='utf-8')


def build_project(workspace):
    plan = json.loads((workspace/'object_plan.json').read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    context = BuildContext(plan)
    setup_display(plan,workspace)
    module = runpy.run_path(str(workspace/'model.py'))
    require(callable(module.get('build')), 'Model script must define build(ctx)')
    module['build'](context)
    bpy.context.view_layer.update()
    roots_and_parts(plan)
    bpy.context.scene['orca_scene_id'] = plan['scene_id']
    bpy.context.scene.render.filepath = '//blender_preview.png'
    bpy.ops.wm.save_as_mainfile(filepath=str(workspace/'project.blend'))
    bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    mode, directory = sys.argv[sys.argv.index('--')+1:]
    directory = Path(directory).resolve()
    if mode == 'build':
        build_project(directory)
    elif mode == 'export':
        export_project(directory)
    else:
        raise ValueError(f'Unknown worker mode: {mode}')
