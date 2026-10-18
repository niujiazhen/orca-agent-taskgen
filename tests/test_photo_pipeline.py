from __future__ import annotations

from copy import deepcopy
import hashlib
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import subprocess
import shutil
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image
import pytest
import yaml

from orca_sim.taskgen import load_environment, load_scene
from orca_sim.taskgen.contracts import ContractError
from orca_sim.taskgen.photo_contracts import calibrate_scene, content_hash, validate_scene_spec
from orca_sim.taskgen.photo_scene import check_scene, draft_scene, generate_scene, preview_scene
from orca_sim.taskgen.photo_task import create_photo_task, check_photo_task, preview_photo_task
from orca_sim.taskgen.photo_upload import CaptureSession, normalize_image, wait_for_upload


def image_bytes(format="PNG"):
    stream = BytesIO()
    Image.new("RGB", (640, 480), "tan").save(stream, format=format)
    return stream.getvalue()


def make_scene(tmp_path, categories=("pen", "eraser"), *, confirmed=True):
    image = tmp_path/"input.png"
    image.write_bytes(image_bytes())
    path = draft_scene(image, output=tmp_path/"drafts", scene_id="desk_pen", categories=categories)
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec["questions"] = []
    spec["confirmed"] = confirmed
    # A synthetic fixture tests geometry, not image interpretation.
    spec["notes"] = ["Synthetic test fixture; not a real image-recognition benchmark"]
    for index, obj in enumerate(spec["objects"]):
        obj["xy"] = list([(-.18,-.1),(-.08,-.1),(.05,-.1),(-.1,.1),(.12,.1)][index]) if len(categories) > 2 else [0, -.10+index*.10]
        obj["image_bbox"] = [.05, .05+index*.15, .9, .18+index*.15]
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return generate_scene(path, output=tmp_path/"scenes")


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP", "HEIF"])
def test_supported_photo_formats(tmp_path, format):
    if format == "HEIF":
        import pillow_heif
        pillow_heif.register_heif_opener()
    receipt = normalize_image(image_bytes(format), tmp_path/"source.png")
    assert receipt["width"] == 640 and receipt["height"] == 480
    assert receipt["sha256"] == hashlib.sha256((tmp_path/"source.png").read_bytes()).hexdigest()
    with Image.open(tmp_path/"source.png") as im:
        assert im.mode == "RGB" and not im.getexif()


def test_exif_rotation_invalid_and_large_uploads(tmp_path, monkeypatch):
    im = Image.new("RGB", (60, 40))
    exif = im.getexif()
    exif[274] = 6
    stream = BytesIO()
    im.save(stream, format="JPEG", exif=exif)
    receipt = normalize_image(stream.getvalue(), tmp_path/"source.png")
    assert (receipt["width"], receipt["height"]) == (40, 60)
    with pytest.raises(ContractError):
        normalize_image(b"not a photo", tmp_path/"bad.png")
    import orca_sim.taskgen.photo_upload as upload
    monkeypatch.setattr(upload, "MAX_BYTES", 10)
    with pytest.raises(ContractError, match="20 MB"):
        normalize_image(image_bytes(), tmp_path/"bad.png")
    monkeypatch.setattr(upload, "MAX_BYTES", 20*1024*1024)
    monkeypatch.setattr(upload, "MAX_PIXELS", 100)
    with pytest.raises(ContractError, match="40 megapixels"):
        normalize_image(image_bytes(), tmp_path/"bad.png")


def test_lan_upload_receipt_auth_and_path_isolation(tmp_path):
    session = CaptureSession(tmp_path/"capture")
    server = ThreadingHTTPServer(("127.0.0.1", 0), session.handler())
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    suffix = f"?token={session.token}"
    try:
        with pytest.raises(HTTPError) as exc:
            urlopen(base+"/status", timeout=5)
        assert exc.value.code == 403
        page = urlopen(base+"/"+suffix, timeout=5).read()
        assert b'capture="environment"' in page
        request = Request(base+"/upload"+suffix, data=image_bytes(), method="POST")
        receipt = json.load(urlopen(request, timeout=5))
        assert receipt["sha256"]
        assert wait_for_upload(session.directory, timeout=0)["state"] == "uploaded"
        assert urlopen(base+"/artifacts/source.png"+suffix, timeout=5).read().startswith(b"\x89PNG")
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(base+"/upload"+suffix, data=image_bytes(), method="POST"), timeout=5)
        assert exc.value.code == 409
        with pytest.raises(HTTPError) as exc:
            urlopen(base+"/artifacts/../capture-session.json"+suffix, timeout=5)
        assert exc.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


def test_scene_geometry_review_calibration_and_determinism(tmp_path):
    bundle = make_scene(tmp_path, confirmed=False)
    assert check_scene(bundle)["status"] == "needs_confirmation"
    spec = yaml.safe_load((bundle/"scene_spec.yaml").read_text(encoding="utf-8"))
    from orca_sim.taskgen.photo_scene import compile_scene
    assert compile_scene(spec) == compile_scene(deepcopy(spec))
    calibrated = calibrate_scene(spec, "pen_1", 0, .28)
    assert calibrated["objects"][0]["dimensions"][0] == .28
    np.testing.assert_allclose(calibrated["objects"][1]["dimensions"], np.array(spec["objects"][1]["dimensions"])*2)
    assert calibrated["confirmed"] is False
    with pytest.raises(ContractError, match="confirmed"):
        create_photo_task(bundle, output=tmp_path/"tasks", family="pick_up", object_id="pen_1")
    with load_scene_context(bundle) as scene:
        assert not hasattr(scene, "action_space")
        pen = scene.model.body("scene_pen_1").id
        extent = scene.model.geom_size[scene.model.body_geomadr[pen]]
        assert extent[0] < .01  # capsule radius, not a vertical cylinder


class load_scene_context:
    def __init__(self, bundle): self.scene = load_scene(bundle)
    def __enter__(self): return self.scene
    def __exit__(self, *args): self.scene.close()


@pytest.mark.parametrize("bad", ["unknown", "too_many", "nan", "path", "overlap", "off_table"])
def test_reject_unsafe_or_ambiguous_scene(tmp_path, bad):
    bundle = make_scene(tmp_path)
    path = bundle/"scene_spec.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if bad == "unknown": spec["objects"][0]["category"] = "mug"
    elif bad == "too_many": spec["objects"] *= 3
    elif bad == "nan": spec["objects"][0]["mass"] = float("nan")
    elif bad == "path": spec["source"]["image"] = "../outside.png"
    elif bad == "overlap": spec["objects"][1]["xy"] = spec["objects"][0]["xy"]
    elif bad == "off_table": spec["objects"][0]["xy"] = [.3, .3]
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    with pytest.raises(ContractError):
        generate_scene(path, output=tmp_path/"invalid")


@pytest.mark.parametrize("category", ["box", "cylinder", "sphere", "pen", "eraser", "book"])
def test_all_photo_assets_stable_and_rl_interfaces(tmp_path, category):
    bundle = make_scene(tmp_path, categories=(category,))
    assert check_scene(bundle)["physics"] == "pass"
    task = create_photo_task(bundle, output=tmp_path/"tasks", family="pick_up", object_id=f"{category}_1")
    env = load_environment(task)
    try:
        first, info = env.reset(seed=123)
        second, _ = env.reset(seed=123)
        np.testing.assert_array_equal(first, second)
        assert first.shape == (135,)
        assert env.observation_space.contains(first)
        assert env.action_space.shape == (23,)
        assert info["hand_table_penetration_m"] == 0
        env.action_space.seed(0)
        for t in range(200):
            obs, reward, done, truncated, info = env.step(env.action_space.sample())
            assert np.isfinite(obs).all() and np.isfinite(reward)
            if done or truncated: env.reset(seed=t)
        if category == "book":
            manifest = json.loads((task/"manifest.json").read_text())
            assert manifest["warnings"]
    finally:
        env.close()


def test_multibody_target_masks_and_no_script_state_writes(tmp_path):
    bundle = make_scene(tmp_path)
    task = create_photo_task(bundle, output=tmp_path/"tasks", family="pick_place", object_id="eraser_2", target_xy=[.13,.10])
    env = load_environment(task)
    try:
        obs, _ = env.reset(seed=0)
        slots = obs[53:128].reshape(5, 15)
        np.testing.assert_array_equal(slots[:, 13], [1, 1, 0, 0, 0])
        np.testing.assert_array_equal(slots[:, 14], [0, 1, 0, 0, 0])
        before = env.data.qpos.copy()
        env.scripted_action()
        np.testing.assert_array_equal(before, env.data.qpos)
        for _ in range(30):
            action = np.r_[np.zeros(6), env._hand_action(np.asarray(env._hand_qpos()))].astype(np.float32)
            env.step(action)
        assert not env._success
    finally:
        env.close()


def test_render_video_and_split_acceptance(tmp_path):
    bundle = make_scene(tmp_path, categories=("pen",))
    assert preview_scene(bundle)["status"] == "generated"
    with imageio.get_reader(bundle/"scene_preview.mp4") as video:
        assert video.get_data(0).shape == (480, 640, 3)
    task = create_photo_task(bundle, output=tmp_path/"tasks", family="pick_up", object_id="pen_1")
    report = check_photo_task(task, episodes=1, stress_steps=200, reset_count=5)
    assert report["scene"]["status"] == "pass"
    assert report["rl_interface"]["status"] == "pass"
    assert report["status"] == "pass"  # script gate is independent
    preview = preview_photo_task(task, max_steps=20)
    assert preview["scripted_success"] is False
    assert "task_preview.mp4" in json.loads((task/"manifest.json").read_text())["files"]
    with imageio.get_reader(task/"task_preview.mp4") as video:
        assert video.get_data(0).shape == (480, 640, 3)


def test_cli_confirmation_rejects_stale_review(tmp_path):
    bundle = make_scene(tmp_path, confirmed=False)
    command = [sys.executable, "-m", "orca_sim.taskgen.cli", "scene", "confirm", str(bundle), "--spec-sha256"]
    result = subprocess.run(command+["0"*64], capture_output=True, text=True)
    assert result.returncode != 0
    spec = yaml.safe_load((bundle/"scene_spec.yaml").read_text(encoding="utf-8"))
    result = subprocess.run(command+[content_hash(spec)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "confirmed"


def test_five_object_slots_and_portable_photo_bundle(tmp_path):
    bundle = make_scene(tmp_path, categories=("box", "sphere", "cylinder", "pen", "eraser"))
    path = bundle/"scene_spec.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    for obj, xy in zip(spec["objects"], [(-.18,-.1),(-.08,-.1),(.05,-.1),(-.1,.1),(.12,.1)]):
        obj["xy"] = list(xy)
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    bundle = generate_scene(path, output=tmp_path/"scenes")
    task = create_photo_task(bundle, output=tmp_path/"tasks", family="pick_up", object_id="pen_4")
    moved = tmp_path/"relocated"/"task"
    shutil.copytree(task, moved)
    model = mujoco.MjModel.from_xml_path(str(moved/"scene.xml"))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert data.xpos[model.body("right_tower").id][2] > spec["table"]["top_z"]+.3
    env = load_environment(moved)
    try:
        obs, _ = env.reset(seed=0)
        slots = obs[53:128].reshape(5,15)
        np.testing.assert_array_equal(slots[:,13], [1]*5)
        np.testing.assert_array_equal(slots[:,14], [0,0,0,1,0])
    finally:
        env.close()
