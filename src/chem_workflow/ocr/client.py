"""Small OpenAI-compatible HTTP client for a local vLLM vision model."""

from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OCRClientError(RuntimeError):
    """Raised when the local vLLM endpoint cannot be reached or parsed."""


@dataclass(frozen=True)
class OCRImage:
    """Image bytes sent to GLM-OCR."""

    name: str
    data: bytes
    mime_type: str = "image/jpeg"

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.data).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"


class GLMOCRClient:
    """Synchronous client for vLLM's local ``/v1/chat/completions`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8000",
        model: str = "zai-org/GLM-OCR",
        timeout_seconds: float = 180.0,
        max_output_tokens: int = 4096,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    def health(self) -> list[str]:
        """Return model IDs exposed by the local server."""
        payload = self._request("GET", "/v1/models")
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise OCRClientError("vLLM /v1/models 返回格式无效。")
        return [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]

    def recognize(self, images: list[OCRImage], prompt: str) -> dict[str, object]:
        """Send one or more images and return the raw JSON response."""
        if not images:
            raise OCRClientError("至少需要一张图片。")
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        for image in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": image.data_url},
                }
            )
        request_payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
        }
        return self._request("POST", "/v1/chat/completions", request_payload)

    def extract_content(self, response: dict[str, object]) -> str:
        """Extract assistant text from common vLLM/OpenAI response shapes."""
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OCRClientError("vLLM 响应缺少 choices。")
        first = choices[0]
        if not isinstance(first, dict):
            raise OCRClientError("vLLM 响应 choices 格式无效。")
        message = first.get("message")
        if not isinstance(message, dict):
            raise OCRClientError("vLLM 响应缺少 message。")
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
            return "".join(str(chunk) for chunk in chunks if chunk)
        raise OCRClientError("vLLM 响应 content 格式无效。")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            # vLLM normally does not require authentication; the placeholder keeps the request
            # compatible with installations that enable an API key.
            headers["Authorization"] = "Bearer local-dailychem"
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise OCRClientError(f"本地 OCR 服务返回 HTTP {error.code}: {detail[:500]}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise OCRClientError(f"无法连接本地 OCR 服务 {self.base_url}：{error}") from error
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as error:
            raise OCRClientError("本地 OCR 服务返回的不是 JSON。") from error
        if not isinstance(parsed, dict):
            raise OCRClientError("本地 OCR 服务返回 JSON 顶层不是 object。")
        return parsed


def infer_mime_type(name: str, fallback: str = "image/jpeg") -> str:
    """Infer a browser-safe image MIME type from a filename."""
    guessed, _ = mimetypes.guess_type(name)
    return guessed if guessed and guessed.startswith("image/") else fallback


__all__ = ["GLMOCRClient", "OCRClientError", "OCRImage", "infer_mime_type"]
