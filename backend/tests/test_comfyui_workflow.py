import json

import pytest

from app.services.comfyui_workflow import WorkflowCompiler


def _files(tmp_path, *, pose=True, seed=True):
    workflow = {
        "1": {"inputs": {"text": ""}},
        "2": {"inputs": {"image": ""}},
        "3": {"inputs": {"image": ""}},
        "4": {"inputs": {"seed": 0}},
        "9": {"inputs": {}},
    }
    (tmp_path / "workflow.json").write_text(json.dumps(workflow), encoding="utf-8")
    descriptor = {
        "format": "sprite-comfyui-workflow",
        "format_version": 1,
        "workflow_file": "workflow.json",
        "prompt": {"node_id": "1", "input_name": "text"},
        "identity_image": {"node_id": "2", "input_name": "image"},
        "output_node_id": "9",
    }
    if pose:
        descriptor["pose_image"] = {"node_id": "3", "input_name": "image"}
    if seed:
        descriptor["seed"] = {"node_id": "4", "input_name": "seed"}
    path = tmp_path / "workflow.sprite.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    return path


def test_compiler_binds_only_declared_operator_fields(tmp_path):
    compiler = WorkflowCompiler(_files(tmp_path))

    result = compiler.compile(
        prompt="walk", identity_image="identity.png", pose_image="pose.png", seed=42
    )

    assert result["1"]["inputs"]["text"] == "walk"
    assert result["2"]["inputs"]["image"] == "identity.png"
    assert result["3"]["inputs"]["image"] == "pose.png"
    assert result["4"]["inputs"]["seed"] == 42


def test_compiler_rejects_unbound_seed_before_transport(tmp_path):
    compiler = WorkflowCompiler(_files(tmp_path, seed=False))

    with pytest.raises(ValueError, match="seed"):
        compiler.compile(prompt="idle", seed=1)


def test_descriptor_rejects_unknown_fields(tmp_path):
    path = _files(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["endpoint"] = "http://example.com"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        WorkflowCompiler(path)
