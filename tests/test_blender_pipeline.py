"""Acceptance checks for saved Blender edits and portable mesh-only scenes."""
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image
import pytest
import yaml

from orca_sim.taskgen import ContractError, load_scene, load_environment
from orca_sim.taskgen.blender import build_blender, export_blender, find_blender
from orca_sim.taskgen.mesh_scene import read_obj
from orca_sim.taskgen.photo_contracts import load_scene_spec, rotation, calibrate_scene
from orca_sim.taskgen.photo_scene import check_scene, generate_scene
from orca_sim.taskgen.photo_task import create_photo_task

DEMO = Path(__file__).resolve().parents[1]/'examples/blender/five_objects/scene/blender_five_objects'


@pytest.fixture
def mesh_bundle(tmp_path):
    path = tmp_path/'relocated'
    shutil.copytree(DEMO,path)
    return path


def test_portable_scene_physics_visual_mass_and_collision_groups(mesh_bundle):
    spec = load_scene_spec(mesh_bundle/'scene_spec.yaml')
    scene = load_scene(mesh_bundle)
    try:
        scene.step(500)
        assert scene.render().shape == (480,640,3)
        assert not np.array_equal(scene.render(),scene.render(collision=True))
        for obj in spec['objects']:
            assert scene.model.body(f"scene_{obj['id']}").mass[0] == pytest.approx(obj['mass'])
        visual = np.flatnonzero(scene.model.geom_group == 2)
        collision = np.flatnonzero(scene.model.geom_group == 3)
        assert len(collision) == 5 and len(visual) > 5
        assert np.all(scene.model.geom_contype[visual] == 0)
        assert np.all(scene.model.geom_conaffinity[visual] == 0)
        assert np.all(scene.model.geom_contype[collision] != 0)
    finally:
        scene.close()
    report = check_scene(mesh_bundle)
    assert report['physics'] == 'pass' and report['confirmation'] == 'pending'
    assert len(report['objects']) == 5


@pytest.mark.parametrize('change',['missing_mesh','edited_mesh','edited_project','edited_xml','escaping_path','duplicate_id'])
def test_asset_integrity_and_identity_reject_invalid_bundles(mesh_bundle,change):
    path = mesh_bundle/'scene_spec.yaml'
    spec = load_scene_spec(path)
    mesh = mesh_bundle/spec['objects'][0]['geometry']['visuals'][0]['file']
    if change == 'missing_mesh':
        mesh.unlink()
    elif change == 'edited_mesh':
        mesh.write_text(mesh.read_text()+'\n# edited after review\n')
    elif change == 'edited_project':
        with (mesh_bundle/'project.blend').open('ab') as f:
            f.write(b'changed')
    elif change == 'edited_xml':
        with (mesh_bundle/'scene.xml').open('a') as f:
            f.write('\n<!-- changed -->')
    elif change == 'escaping_path':
        spec['objects'][0]['geometry']['collision']['file'] = '../outside.obj'
        path.write_text(yaml.safe_dump(spec))
    else:
        spec['objects'][1]['id'] = spec['objects'][0]['id']
        path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractError):
        scene = load_scene(mesh_bundle)
        scene.close()


def test_mesh_scene_refuses_rl_and_primitive_calibration(mesh_bundle):
    with pytest.raises(ContractError,match='use load_scene'):
        load_environment(mesh_bundle)
    with pytest.raises(ContractError,match='scene display only'):
        create_photo_task(mesh_bundle,output=mesh_bundle/'tasks',family='pick_up',object_id='pen_1')
    with pytest.raises(ContractError,match='edit dimensions in Blender'):
        calibrate_scene(load_scene_spec(mesh_bundle/'scene_spec.yaml'),'pen_1',0,.15)


@pytest.mark.parametrize('kind',['floating','intersecting'])
def test_saved_bad_positions_are_rejected_without_snapping(mesh_bundle,tmp_path,kind):
    path = mesh_bundle/'scene_spec.yaml'
    spec = load_scene_spec(path)
    if kind == 'floating':
        spec['objects'][0]['position'][2] += .02
    else:
        spec['objects'][1]['position'] = spec['objects'][4]['position'].copy()
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(ContractError,match='supported|intersecting'):
        generate_scene(path,output=tmp_path/'invalid')
    assert not (tmp_path/'invalid'/spec['scene_id']).exists()


def edit_saved_project(executable,workspace,code):
    script = workspace/'test_edit.py'
    script.write_text('import bpy, math\n'+code+'\nbpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n',encoding='utf-8')
    result = subprocess.run([str(executable),'--background',str(workspace/'project.blend'),'--python-exit-code','1','--python',str(script)],
                            capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr


def test_blender_roundtrip_edits_and_export_failure_invalidate_snapshot(tmp_path,monkeypatch):
    try:
        blender = find_blender()
    except ContractError:
        pytest.skip('Install Blender 4.5 LTS to run real authoring integration')
    source = tmp_path/'source.png'
    Image.new('RGB',(64,64),'gray').save(source)
    plan = {'schema_version':1,'scene_id':'edited_mesh','source':'source.png',
            'table':{'dimensions':[.6,.5,.02],'top_z':.2,'rgba':[.8,.8,.8,1],'friction':[1.2,.01,.001]},
            'objects':[{'id':'item_1','name':'Editable rigid object','dimensions':[.04,.06,.03],
                        'position':[0,0,.2155],'rgba':[.2,.4,.8,1],'image_bbox':[.1,.1,.9,.9]}]}
    plan_path=tmp_path/'plan.yaml'; plan_path.write_text(yaml.safe_dump(plan))
    script=tmp_path/'model.py'
    script.write_text('import bpy\ndef build(ctx):\n bpy.ops.mesh.primitive_cube_add(size=1)\n o=bpy.context.object\n o.dimensions=(.04,.06,.03)\n bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)\n ctx.add_part("item_1",o,(.2,.4,.8,1))\n')
    workspace=tmp_path/'workspace'
    opened=[]
    monkeypatch.setattr('orca_sim.taskgen.blender.open_blender',lambda *a,**kw: opened.append(a[0]))
    result=build_blender(plan_path,script=script,output=workspace,executable=blender)
    assert opened == [workspace] and result['status']=='needs_blender_review'
    export_blender(workspace,executable=blender)
    original = (workspace/'project.blend').read_bytes()
    edit_saved_project(blender,workspace,
        "r=bpy.data.objects['item_1']\nr.location=(.035,-.025,.22)\nr.scale=(1.5,.8,1.3)\n"
        "r.rotation_quaternion=(math.cos(.3),0,0,math.sin(.3))\n"
        "o=r.children[0]\no.data.vertices[0].co.x += .004\n"
        "o.active_material.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.9,.15,.05,1)\n"
        "bpy.context.view_layer.update()\n"
        "import json\nfrom pathlib import Path\n"
        "Path(bpy.data.filepath).with_name('expected_vertices.json').write_text(json.dumps([list(o.matrix_world@v.co) for v in o.data.vertices]))")
    export_blender(workspace,executable=blender)
    path=workspace/'export/scene_spec.yaml'; spec=load_scene_spec(path); obj=spec['objects'][0]
    np.testing.assert_allclose(obj['position'],[.035,-.025,.22],atol=1e-7)
    np.testing.assert_allclose(obj['dimensions'],[.06,.048,.039],atol=1e-7)
    np.testing.assert_allclose(obj['geometry']['visuals'][0]['rgba'],[.9,.15,.05,1],atol=1e-6)
    vertices,_=read_obj(workspace/'export'/obj['geometry']['visuals'][0]['file'])
    world=vertices@rotation(obj['quaternion']).T+obj['position']
    expected=np.array(json.loads((workspace/'expected_vertices.json').read_text()))
    assert np.max(np.min(np.linalg.norm(world[:,None,:]-expected[None,:,:],axis=-1),axis=1)) < 1e-7
    bundle=generate_scene(path,output=tmp_path/'generated')
    assert check_scene(bundle)['physics']=='pass'
    scene=load_scene(bundle)
    try:
        data,model=scene.data,scene.model
        gid=model.geom('item_1_visual_0').id
        mid=model.geom_dataid[gid]; start=model.mesh_vertadr[mid]; count=model.mesh_vertnum[mid]
        actual=model.mesh_vert[start:start+count]@data.geom_xmat[gid].reshape(3,3).T+data.geom_xpos[gid]
        assert np.max(np.min(np.linalg.norm(actual[:,None,:]-expected[None,:,:],axis=-1),axis=1)) < 1e-6
    finally:
        scene.close()
    # A duplicated root must fail and remove the previously consumable export.
    edit_saved_project(blender,workspace,"r=bpy.data.objects['item_1']\nc=r.copy()\nbpy.context.scene.collection.objects.link(c)")
    with pytest.raises(ContractError,match='Duplicate object ID'):
        export_blender(workspace,executable=blender)
    assert not path.exists()
    assert json.loads((workspace/'export_report.json').read_text())['status']=='failed'
    (workspace/'project.blend').write_bytes(original)
    export_blender(workspace,executable=blender)
    assert path.exists() and load_scene_spec(path)['objects'][0]['position'][0] == 0
    for edit, message in [
        ("del bpy.data.objects['item_1']['orca_id']", 'Missing object IDs'),
        ("bpy.ops.mesh.primitive_cube_add(size=.01)", 'Unregistered geometry'),
        ("r=bpy.data.objects['item_1']\nbpy.data.objects.remove(r.children[0],do_unlink=True)\n"
         "bpy.ops.mesh.primitive_uv_sphere_add(segments=128,ring_count=128,radius=.02)\n"
         "bpy.context.object.parent=r", 'exceeds 20,000'),
    ]:
        (workspace/'project.blend').write_bytes(original)
        edit_saved_project(blender,workspace,edit)
        with pytest.raises(ContractError,match=message):
            export_blender(workspace,executable=blender)
        assert not path.exists()


def test_three_failed_model_attempts_stop_and_preserve_logs(tmp_path,monkeypatch):
    plan = {'schema_version':1,'scene_id':'failed_model','source':'source.png',
            'table':{'dimensions':[.6,.5,.02],'top_z':.2,'rgba':[.8,.8,.8,1],'friction':[1.2,.01,.001]},
            'objects':[{'id':'item_1','name':'Test object','dimensions':[.04,.04,.04],
                        'position':[0,0,.2205],'rgba':[.5,.5,.5,1],'image_bbox':[.1,.1,.9,.9]}]}
    Image.new('RGB',(8,8)).save(tmp_path/'source.png')
    plan_path=tmp_path/'plan.yaml';plan_path.write_text(yaml.safe_dump(plan))
    script=tmp_path/'model.py';script.write_text('raise ValueError("model error")')
    monkeypatch.setattr('orca_sim.taskgen.blender.find_blender',lambda *a:Path('blender'))
    def fail(executable,mode,workspace):
        (workspace/'build.log').write_text('Model script error')
        raise ContractError('Model script error')
    monkeypatch.setattr('orca_sim.taskgen.blender._run',fail)
    workspace=tmp_path/'workspace'
    for _ in range(3):
        with pytest.raises(ContractError,match='Model script error'):
            build_blender(plan_path,script=script,output=workspace,open_ui=False)
    with pytest.raises(ContractError,match='Three modeling attempts'):
        build_blender(plan_path,script=script,output=workspace,open_ui=False)
    assert all((workspace/f'build_attempt_{n}.log').is_file() for n in (1,2,3))


def test_missing_blender_has_actionable_error(tmp_path):
    with pytest.raises(ContractError,match='ORCA_BLENDER_PATH'):
        find_blender(tmp_path/'no-blender.exe')
