"""Windows-side lifecycle management for a WSL2 vLLM process."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from ipaddress import ip_address

from chem_workflow.core.config import OCRConfig
from chem_workflow.ocr.client import GLMOCRClient, OCRClientError
from chem_workflow.ocr.models import OCRServiceStatus


class OCRRuntimeError(RuntimeError):
    """Raised when WSL/vLLM cannot be started or inspected."""


@dataclass
class OCRRuntimeManager:
    """Start vLLM on demand without exposing it outside the local machine."""

    config: OCRConfig
    process: subprocess.Popen[str] | None = None
    active_host: str | None = None

    @property
    def endpoint(self) -> str:
        return f"http://{self.active_host or self.config.host}:{self.config.port}"

    def client(self) -> GLMOCRClient:
        return GLMOCRClient(
            base_url=self.endpoint,
            model=self.config.model_id,
            timeout_seconds=self.config.request_timeout_seconds,
            max_output_tokens=self.config.max_output_tokens,
        )

    def _health(self) -> list[str]:
        last_error: OCRClientError | None = None
        for host in self._candidate_hosts():
            client = GLMOCRClient(
                base_url=f"http://{host}:{self.config.port}",
                model=self.config.model_id,
                timeout_seconds=min(self.config.request_timeout_seconds, 5.0),
                max_output_tokens=self.config.max_output_tokens,
            )
            try:
                models = client.health()
            except OCRClientError as error:
                last_error = error
                continue
            self.active_host = host
            return models
        raise last_error or OCRClientError("本地 OCR 服务不可用。")

    def _candidate_hosts(self) -> list[str]:
        hosts = [self.config.host]
        if self.config.host in {"127.0.0.1", "localhost"} and shutil.which("wsl.exe"):
            result = subprocess.run(  # noqa: S603 - fixed WSL diagnostic command
                ["wsl.exe", "-d", self.config.wsl_distribution, "--", "hostname", "-I"],
                check=False,
                capture_output=True,
                text=False,
            )
            raw_output = result.stdout or b""
            decoded_outputs = [raw_output.decode("utf-8", errors="ignore")]
            if b"\x00" in raw_output:
                decoded_outputs.append(raw_output.decode("utf-16", errors="ignore"))
            for output in decoded_outputs:
                for value in output.split():
                    try:
                        normalized = str(ip_address(value))
                    except ValueError:
                        continue
                    if normalized not in hosts:
                        hosts.append(normalized)
        return hosts

    def status(self) -> OCRServiceStatus:
        try:
            models = self._health()
        except OCRClientError as error:
            if self.process is not None and self.process.poll() is None:
                return OCRServiceStatus(
                    state="starting",
                    message="本地 OCR 服务正在启动，模型加载可能需要几分钟。",
                    endpoint=self.endpoint,
                    model=self.config.model_id,
                    details=[str(error)],
                )
            return OCRServiceStatus(
                state="stopped",
                message="本地 OCR 服务未就绪。",
                endpoint=self.endpoint,
                model=self.config.model_id,
                details=[str(error)],
            )
        return OCRServiceStatus(
            state="ready",
            message="本地 OCR 服务已就绪。",
            endpoint=self.endpoint,
            model=models[0] if models else self.config.model_id,
        )

    def doctor(self) -> list[str]:
        """Return actionable checks; an empty list means the host prerequisites look usable."""
        problems: list[str] = []
        if os.name != "nt":
            problems.append("WSL 运行时管理器只能在 Windows 上使用。")
        if shutil.which("wsl.exe") is None:
            problems.append("找不到 wsl.exe，请先安装 WSL2。")
        else:
            result = subprocess.run(  # noqa: S603 - fixed WSL diagnostic command
                ["wsl.exe", "--status"],
                check=False,
                capture_output=True,
                text=False,
            )
            if result.returncode != 0:
                problems.append("wsl --status 无法执行；请启用 WSL2、虚拟化并重启 Windows。")
        if not self.config.enabled:
            problems.append("OCR 已在 .chemwf.toml 中禁用。")
        if not self.config.model_id.strip():
            problems.append("OCR model_id 不能为空。")
        if not 1 <= self.config.port <= 65535:
            problems.append("OCR port 必须在 1 到 65535 之间。")
        return problems

    def start(self) -> OCRServiceStatus:
        """Start vLLM if needed and wait for its health endpoint."""
        current = self.status()
        if current.state == "ready":
            return current
        problems = self.doctor()
        if problems:
            raise OCRRuntimeError("无法启动本地 OCR：" + "；".join(problems))

        command = self.build_start_command()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = subprocess.Popen(  # noqa: S603 - fixed command built from validated config
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=creationflags,
            )
        except OSError as error:
            raise OCRRuntimeError(f"无法启动 WSL OCR 服务：{error}") from error

        deadline = time.monotonic() + self.config.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise OCRRuntimeError(
                    "vLLM 进程提前退出。请运行 `chemwf ocr doctor` 并查看 WSL 日志。"
                )
            ready = self.status()
            if ready.state == "ready":
                return ready
            time.sleep(1.0)
        raise OCRRuntimeError(
            f"等待本地 OCR 服务超过 {self.config.startup_timeout_seconds:.0f} 秒；"
            "请检查显存、模型下载和 WSL 日志。"
        )

    def stop(self) -> None:
        """Ask the WSL distro to stop only the configured model server."""
        if shutil.which("wsl.exe") is None:
            return
        command = [
            "wsl.exe",
            "-d",
            self.config.wsl_distribution,
            "--",
            "bash",
            "-lc",
            self.build_stop_shell_command(),
        ]
        subprocess.run(command, check=False, capture_output=True, text=True)  # noqa: S603
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()

    def build_start_command(self) -> list[str]:
        """Build a deterministic command suitable for unit tests and logging."""
        model = _shell_path(self.config.model_dir)
        env_dir = _shell_path(self.config.vllm_env_dir)
        log_path = _shell_path(self.config.vllm_log_path)
        revision = (
            f" --revision {_shell_quote(self.config.model_revision)}"
            if self.config.model_revision
            else ""
        )
        shell = (
            f"source {env_dir}/bin/activate && "
            f"exec vllm serve {model} --host {_shell_quote(self.config.host)} "
            f"--port {self.config.port} "
            f"--served-model-name {_shell_quote(self.config.model_id)}"
            f" --trust-remote-code{revision} > {log_path} 2>&1"
        )
        return ["wsl.exe", "-d", self.config.wsl_distribution, "--", "bash", "-lc", shell]

    def build_stop_shell_command(self) -> str:
        """Return a narrowly scoped process stop command."""
        model_pattern = self.config.model_id.replace("'", "")
        return f"pkill -f 'vllm serve .*{model_pattern}' || true"


def _shell_quote(value: str) -> str:
    """Quote a fixed config value for bash without invoking a shell on Windows."""
    return "'" + value.replace("'", "'\\''") + "'"


def _shell_path(value: str) -> str:
    """Quote a Linux path while allowing the conventional ``~/`` form to expand."""
    if value.startswith("~/"):
        suffix = value[2:].replace('"', '\\"')
        return '"$HOME/' + suffix + '"'
    return _shell_quote(value)


__all__ = ["OCRRuntimeError", "OCRRuntimeManager"]
