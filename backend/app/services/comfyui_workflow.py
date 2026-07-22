"""Strict operator-owned ComfyUI API-workflow descriptor and compiler."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_WORKFLOW_BYTES = 2 * 1024 * 1024


class WorkflowBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[0-9]+$")
    input_name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ComfyUIWorkflowDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["sprite-comfyui-workflow"] = "sprite-comfyui-workflow"
    format_version: Literal[1] = 1
    workflow_file: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.json$")
    prompt: WorkflowBinding
    output_node_id: str = Field(pattern=r"^[0-9]+$")
    identity_image: WorkflowBinding | None = None
    pose_image: WorkflowBinding | None = None
    seed: WorkflowBinding | None = None


class WorkflowCompiler:
    def __init__(self, descriptor_path: str | Path):
        path = Path(descriptor_path).resolve()
        if path.is_symlink() or not path.is_file():
            raise ValueError("ComfyUI workflow descriptor must be a regular file")
        self.descriptor = ComfyUIWorkflowDescriptor.model_validate_json(
            _bounded_read(path)
        )
        workflow_path = path.parent / self.descriptor.workflow_file
        if workflow_path.is_symlink() or not workflow_path.is_file():
            raise ValueError("ComfyUI API workflow must be a regular sibling file")
        if workflow_path.resolve().parent != path.parent:
            raise ValueError("ComfyUI workflow must remain beside its descriptor")
        self.template = json.loads(_bounded_read(workflow_path))
        if not isinstance(self.template, dict):
            raise ValueError("ComfyUI API workflow must be a JSON object")
        self._validate_binding(self.descriptor.prompt)
        for binding in (
            self.descriptor.identity_image,
            self.descriptor.pose_image,
            self.descriptor.seed,
        ):
            if binding:
                self._validate_binding(binding)
        if self.descriptor.output_node_id not in self.template:
            raise ValueError("output node is absent from workflow")

    @property
    def capabilities(self) -> set[str]:
        values = {"generate"}
        if self.descriptor.identity_image:
            values.update({"edit", "identity_reference"})
        if self.descriptor.pose_image:
            values.add("pose_reference")
        if self.descriptor.seed:
            values.add("seed")
        return values

    def compile(
        self,
        *,
        prompt: str,
        identity_image: str | None = None,
        pose_image: str | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        if identity_image is not None and self.descriptor.identity_image is None:
            raise ValueError("workflow does not bind an identity image")
        if pose_image is not None and self.descriptor.pose_image is None:
            raise ValueError("workflow does not bind a pose image")
        if seed is not None and self.descriptor.seed is None:
            raise ValueError("workflow does not bind a seed")
        workflow = copy.deepcopy(self.template)
        self._set(workflow, self.descriptor.prompt, prompt)
        if identity_image is not None:
            self._set(workflow, self.descriptor.identity_image, identity_image)
        if pose_image is not None:
            self._set(workflow, self.descriptor.pose_image, pose_image)
        if seed is not None:
            self._set(workflow, self.descriptor.seed, seed)
        return workflow

    def _validate_binding(self, binding: WorkflowBinding) -> None:
        node = self.template.get(binding.node_id)
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            raise ValueError(f"workflow node {binding.node_id} has no inputs")
        if binding.input_name not in node["inputs"]:
            raise ValueError(
                f"workflow node {binding.node_id} has no input {binding.input_name!r}"
            )

    @staticmethod
    def _set(workflow: dict, binding: WorkflowBinding | None, value: object) -> None:
        assert binding is not None
        workflow[binding.node_id]["inputs"][binding.input_name] = value


def _bounded_read(path: Path) -> str:
    if path.stat().st_size > MAX_WORKFLOW_BYTES:
        raise ValueError(f"workflow file exceeds {MAX_WORKFLOW_BYTES} bytes")
    return path.read_text(encoding="utf-8")
