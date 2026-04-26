from __future__ import annotations

import difflib
import inspect
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import httpx

from visor_agentico.redaction import stable_hash, summarize_value


TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}


@dataclass
class ToolBinding:
    func: Callable[..., Any]
    name: str
    description: str
    redact_fields: list[str]
    input_schema: dict[str, Any]


@dataclass
class TurnResult:
    assistant_message: dict[str, Any]
    executed_tools: list[dict[str, Any]] = field(default_factory=list)


class CommandSession:
    def __init__(self, run: "RunSession") -> None:
        self.session = run

    def run(
        self,
        command: str | list[str],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        check: bool = False,
        shell: bool = False,
        encoding: str = "utf-8",
    ) -> subprocess.CompletedProcess[str]:
        started_at = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            shell=shell,
            capture_output=True,
            text=True,
            encoding=encoding,
            check=False,
        )
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        output_payload = {"stdout": completed.stdout, "stderr": completed.stderr}
        status = "succeeded" if completed.returncode == 0 else "failed"
        error_code = "CommandError" if completed.returncode != 0 else None
        error_summary = None
        if completed.returncode != 0:
            error_summary = summarize_value(
                {
                    "command": self.session._render_command(command),
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                }
            )

        self.session.record_command(
            command,
            status=status,
            cwd=cwd,
            output=output_payload,
            duration_ms=duration_ms,
            error_code=error_code,
            error_summary=error_summary,
            exit_code=completed.returncode,
            stdout_summary=summarize_value(completed.stdout) if completed.stdout else None,
            stderr_summary=summarize_value(completed.stderr) if completed.stderr else None,
        )
        if check and completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode,
                completed.args,
                output=completed.stdout,
                stderr=completed.stderr,
            )
        return completed


class FileSession:
    def __init__(self, run: "RunSession") -> None:
        self.session = run

    def read_text(self, path: str, *, encoding: str = "utf-8") -> str:
        path_obj = Path(path)
        content = path_obj.read_text(encoding=encoding)
        self.session.record_file_read(path, content=content)
        return content

    def write_text(self, path: str, content: str, *, encoding: str = "utf-8") -> None:
        path_obj = Path(path)
        before_content = path_obj.read_text(encoding=encoding) if path_obj.exists() else None
        change_type = "update" if before_content is not None else "create"
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(content, encoding=encoding)
        self.session.record_file_write(
            path,
            change_type=change_type,
            before_content=before_content,
            after_content=content,
        )

    def delete(self, path: str, *, encoding: str = "utf-8") -> None:
        path_obj = Path(path)
        if not path_obj.exists():
            return
        before_content = path_obj.read_text(encoding=encoding)
        path_obj.unlink()
        self.session.record_file_write(
            path,
            change_type="delete",
            before_content=before_content,
            after_content=None,
        )

    def patch_text(
        self,
        path: str,
        updated_content: str,
        *,
        encoding: str = "utf-8",
        diff_text: str | None = None,
    ) -> None:
        path_obj = Path(path)
        before_content = path_obj.read_text(encoding=encoding) if path_obj.exists() else None
        change_type = "update" if before_content is not None else "create"
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(updated_content, encoding=encoding)
        self.session.record_file_write(
            path,
            change_type=change_type,
            before_content=before_content,
            after_content=updated_content,
        )
        self.session.record_patch(
            path,
            diff_text=diff_text,
            before_content=before_content,
            after_content=updated_content,
        )


class ArtifactSession:
    def __init__(self, run: "RunSession") -> None:
        self.session = run

    def capture(
        self,
        kind: str,
        label: str,
        summary: str,
        *,
        metadata: dict[str, Any] | None = None,
        content: Any | None = None,
    ) -> dict[str, Any]:
        return self.session.record_artifact(
            kind,
            label,
            summary,
            metadata=metadata,
            content=content,
        )


class RunSession:
    def __init__(self, client: "VisorClient", run_id: str, agent_name: str, goal: str, metadata: dict[str, Any] | None = None) -> None:
        self.client = client
        self.run_id = run_id
        self.agent_name = agent_name
        self.goal = goal
        self.metadata = metadata or {}
        self.tools: dict[str, ToolBinding] = {}
        self.messages: list[dict[str, Any]] = []
        self.commands = CommandSession(self)
        self.files = FileSession(self)
        self.artifacts = ArtifactSession(self)

    def record_command(
        self,
        command: str | list[str],
        *,
        status: str = "succeeded",
        cwd: str | None = None,
        output: Any | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
        error_summary: str | None = None,
        exit_code: int | None = None,
        stdout_summary: str | None = None,
        stderr_summary: str | None = None,
        step_id: str | None = None,
        parent_step_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        command_text = self._render_command(command)
        payload = {
            "observations": [
                {
                    "kind": "command",
                    "step_id": step_id or self._step_id("command"),
                    "parent_step_id": parent_step_id,
                    "status": status,
                    "command_id": str(uuid4()),
                    "command": command_text,
                    "cwd": cwd,
                    "output_summary": summarize_value(output) if output is not None else None,
                    "duration_ms": duration_ms,
                    "error_code": error_code,
                    "error_summary": error_summary,
                    "exit_code": exit_code,
                    "stdout_summary": stdout_summary,
                    "stderr_summary": stderr_summary,
                    "metadata": metadata or {},
                }
            ]
        }
        return self.client._request("POST", f"/api/runs/{self.run_id}/observations", payload)

    def record_file_read(
        self,
        path: str,
        *,
        content: Any | None = None,
        content_hash: str | None = None,
        size_bytes: int | None = None,
        step_id: str | None = None,
        parent_step_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "observations": [
                {
                    "kind": "file_read",
                    "step_id": step_id or self._step_id("file-read"),
                    "parent_step_id": parent_step_id,
                    "path": path,
                    "content_hash": content_hash or (stable_hash(content) if content is not None else None),
                    "size_bytes": size_bytes if size_bytes is not None else self._size_bytes(content),
                    "extension": os.path.splitext(path)[1] or None,
                }
            ]
        }
        return self.client._request("POST", f"/api/runs/{self.run_id}/observations", payload)

    def record_file_write(
        self,
        path: str,
        *,
        change_type: str = "update",
        before_content: Any | None = None,
        after_content: Any | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        step_id: str | None = None,
        parent_step_id: str | None = None,
    ) -> dict[str, Any]:
        diff_summary, line_additions, line_deletions = self._diff_details(before_content, after_content)
        payload = {
            "observations": [
                {
                    "kind": "file_write",
                    "step_id": step_id or self._step_id("file-write"),
                    "parent_step_id": parent_step_id,
                    "path": path,
                    "change_type": change_type,
                    "before_hash": before_hash or (stable_hash(before_content) if before_content is not None else None),
                    "after_hash": after_hash or (stable_hash(after_content) if after_content is not None else None),
                    "content_hash": stable_hash(after_content) if after_content is not None else after_hash,
                    "diff_summary": diff_summary,
                    "line_additions": line_additions,
                    "line_deletions": line_deletions,
                    "extension": os.path.splitext(path)[1] or None,
                    "size_bytes": self._size_bytes(after_content),
                }
            ]
        }
        return self.client._request("POST", f"/api/runs/{self.run_id}/observations", payload)

    def record_patch(
        self,
        path: str,
        *,
        diff_text: str | None = None,
        before_content: Any | None = None,
        after_content: Any | None = None,
        before_hash: str | None = None,
        after_hash: str | None = None,
        step_id: str | None = None,
        parent_step_id: str | None = None,
    ) -> dict[str, Any]:
        generated_summary, line_additions, line_deletions = self._diff_details(before_content, after_content)
        diff_summary = summarize_value(diff_text) if diff_text is not None else generated_summary
        payload = {
            "observations": [
                {
                    "kind": "patch",
                    "step_id": step_id or self._step_id("patch"),
                    "parent_step_id": parent_step_id,
                    "path": path,
                    "before_hash": before_hash or (stable_hash(before_content) if before_content is not None else None),
                    "after_hash": after_hash or (stable_hash(after_content) if after_content is not None else None),
                    "diff_summary": diff_summary,
                    "line_additions": line_additions,
                    "line_deletions": line_deletions,
                }
            ]
        }
        return self.client._request("POST", f"/api/runs/{self.run_id}/observations", payload)

    def record_artifact(
        self,
        kind: str,
        label: str,
        summary: str,
        *,
        metadata: dict[str, Any] | None = None,
        content: Any | None = None,
        content_hash: str | None = None,
        step_id: str | None = None,
        parent_step_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "observations": [
                {
                    "kind": "artifact",
                    "step_id": step_id or self._step_id("artifact"),
                    "parent_step_id": parent_step_id,
                    "artifact": {
                        "kind": kind,
                        "label": label,
                        "summary": summary,
                        "metadata": {
                            **(metadata or {}),
                            "content_hash": content_hash or (stable_hash(content) if content is not None else None),
                        },
                    },
                }
            ]
        }
        return self.client._request("POST", f"/api/runs/{self.run_id}/observations", payload)

    def tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        redact_fields: list[str] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            self.tools[tool_name] = ToolBinding(
                func=func,
                name=tool_name,
                description=description or (inspect.getdoc(func) or f"Tool {tool_name}"),
                redact_fields=redact_fields or [],
                input_schema=self._build_input_schema(func),
            )
            return func

        return decorator

    def create_model_turn(
        self,
        messages: list[dict[str, Any]] | None,
        *,
        model: str,
        provider: str = "openai",
        tool_choice: str | dict[str, Any] = "auto",
    ) -> TurnResult:
        if messages:
            self.messages.extend(messages)

        executed_tools: list[dict[str, Any]] = []
        while True:
            response = self.client._request(
                "POST",
                f"/api/runs/{self.run_id}/turns",
                {
                    "provider": provider,
                    "model": model,
                    "messages": self.messages,
                    "tools": [self._tool_payload(tool) for tool in self.tools.values()],
                    "tool_choice": tool_choice,
                },
            )
            if response["status"] == "message":
                assistant_message = response["assistant_message"] or {"role": "assistant", "content": ""}
                self.messages.append(assistant_message)
                return TurnResult(assistant_message=assistant_message, executed_tools=executed_tools)

            tool_calls = response["tool_calls"]
            assistant_message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])},
                    }
                    for call in tool_calls
                ],
            }
            self.messages.append(assistant_message)
            results_payload = []
            for call in tool_calls:
                result_payload, tool_message = self._execute_tool(call)
                executed_tools.append(result_payload)
                results_payload.append(result_payload)
                self.messages.append(tool_message)

            self.client._request("POST", f"/api/runs/{self.run_id}/tool-results", {"results": results_payload})

    def finish(self, final_output: Any | None = None, artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return self.client._request(
            "POST",
            f"/api/runs/{self.run_id}/finish",
            {"final_output": final_output, "artifacts": artifacts or []},
        )

    def fail(self, error_code: str, error_summary: str) -> dict[str, Any]:
        return self.client._request(
            "POST",
            f"/api/runs/{self.run_id}/fail",
            {"error_code": error_code, "error_summary": error_summary},
        )

    def _execute_tool(self, call: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        binding = self.tools.get(call["name"])
        if binding is None:
            raise KeyError(f"Tool '{call['name']}' is not registered in this run.")

        arguments = call.get("arguments") or {}
        started_at = time.perf_counter()
        try:
            output = binding.func(**arguments)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            result_payload = {
                "call_id": call["id"],
                "name": binding.name,
                "step_id": call["step_id"],
                "status": "succeeded",
                "args": arguments,
                "output_summary": summarize_value(output, binding.redact_fields),
                "output_hash": stable_hash(output),
                "duration_ms": duration_ms,
                "artifacts": [],
            }
            tool_message = {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(output, ensure_ascii=True, default=str),
            }
            return result_payload, tool_message
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            result_payload = {
                "call_id": call["id"],
                "name": binding.name,
                "step_id": call["step_id"],
                "status": "failed",
                "args": arguments,
                "output_summary": None,
                "output_hash": stable_hash({"error": str(exc)}),
                "error_code": type(exc).__name__,
                "error_summary": str(exc),
                "duration_ms": duration_ms,
                "artifacts": [],
            }
            tool_message = {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps({"error": str(exc)}, ensure_ascii=True),
            }
            return result_payload, tool_message

    def _build_input_schema(self, func: Callable[..., Any]) -> dict[str, Any]:
        signature = inspect.signature(func)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter_name, parameter in signature.parameters.items():
            annotation = parameter.annotation if parameter.annotation is not inspect._empty else str
            properties[parameter_name] = {"type": TYPE_MAP.get(annotation, "string")}
            if parameter.default is inspect._empty:
                required.append(parameter_name)
        return {"type": "object", "properties": properties, "required": required}

    @staticmethod
    def _tool_payload(tool: ToolBinding) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "redact_fields": tool.redact_fields,
        }

    @staticmethod
    def _render_command(command: str | list[str]) -> str:
        if isinstance(command, str):
            return command
        return " ".join(str(part) for part in command)

    @staticmethod
    def _step_id(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:8]}"

    @staticmethod
    def _size_bytes(value: Any | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return len(value)
        return len(str(value).encode("utf-8"))

    @staticmethod
    def _diff_details(before_content: Any | None, after_content: Any | None) -> tuple[str | None, int | None, int | None]:
        if before_content is None and after_content is None:
            return None, None, None

        before_lines = str(before_content or "").splitlines()
        after_lines = str(after_content or "").splitlines()
        diff_lines = list(difflib.unified_diff(before_lines, after_lines, lineterm="", n=1))
        if not diff_lines:
            return "No textual diff.", 0, 0

        line_additions = sum(
            1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
        )
        line_deletions = sum(
            1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
        )
        preview = "\n".join(diff_lines[:10])
        return summarize_value(preview), line_additions, line_deletions


class VisorClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        if http_client is not None:
            self.http = http_client
            return

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    def start_run(self, agent_name: str, goal: str, metadata: dict[str, Any] | None = None) -> RunSession:
        response = self._request("POST", "/api/runs", {"agent_name": agent_name, "goal": goal, "metadata": metadata or {}})
        return RunSession(self, response["run_id"], agent_name, goal, metadata)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.http.request(method, path, json=payload)
        if response.is_error:
            detail = response.text
            try:
                body = response.json()
                if isinstance(body, dict):
                    detail = body.get("detail", detail)
            except Exception:
                pass
            raise httpx.HTTPStatusError(
                f"{response.status_code} for {path}: {detail}",
                request=response.request,
                response=response,
            )
        return response.json()
