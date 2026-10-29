"""Meta SAM 3.1 processor for bounded, image-only annotation derivation."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import threading
import time
from collections.abc import Callable
from io import BytesIO
import socket

from krakadyl.core.acquisition import (
    AcquisitionPhase,
    AdapterAttempt,
    AdapterResponse,
    AttemptState,
    ProcessorRequest,
    ResourceUsage,
    canonical_record_digest,
)

API_URL = "https://api.meta.ai/v1/responses"
API_DESTINATION = "https://api.meta.ai/v1"
MODEL_ID = "sam-3.1"
IMAGE_PRICE_USD_MICROS = 2_500
MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_PROMPT_CHARS = 256
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 120

Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, dict[str, str], bytes]]


class SamAdapterError(RuntimeError):
    def __init__(self, message: str, *, provider_request_id: str | None = None):
        super().__init__(message)
        self.provider_request_id = provider_request_id


def _default_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float
) -> tuple[int, dict[str, str], bytes]:
    if url != API_URL:
        raise SamAdapterError("Meta SAM transport rejected a non-fixed endpoint")
    connection = http.client.HTTPSConnection("api.meta.ai", timeout=timeout)
    deadline = time.monotonic() + timeout
    response_headers: dict[str, str] = {}
    request_id: str | None = None
    try:
        connection.putrequest("POST", "/v1/responses")
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.putheader("Content-Length", str(len(body)))
        _call_with_absolute_deadline(
            connection.endheaders, lambda: _interrupt(connection),
            deadline=deadline, provider_request_id=None,
        )
        for offset in range(0, len(body), 64 * 1024):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SamAdapterError("Meta SAM request exceeded its absolute duration limit")
            if connection.sock is None:
                raise SamAdapterError("Meta SAM connection closed during request dispatch")
            connection.sock.settimeout(remaining)
            chunk = body[offset : offset + 64 * 1024]
            _call_with_absolute_deadline(
                lambda: connection.send(chunk), lambda: _interrupt(connection),
                deadline=deadline, provider_request_id=None,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SamAdapterError("Meta SAM request exceeded its absolute duration limit")
        if connection.sock is None:
            raise SamAdapterError("Meta SAM connection closed before its response")
        connection.sock.settimeout(remaining)
        response = _call_with_absolute_deadline(
            connection.getresponse, lambda: _interrupt(connection),
            deadline=deadline, provider_request_id=None,
        )
        response_headers = dict(response.getheaders())
        request_id = _bounded_request_id(
            response_headers.get("x-request-id") or response_headers.get("X-Request-Id")
        )
        if not 200 <= response.status < 300:
            return response.status, response_headers, b""
        def set_response_timeout(remaining_time: float) -> None:
            if connection.sock is None:
                raise SamAdapterError(
                    "Meta SAM connection closed during response reading",
                    provider_request_id=request_id,
                )
            connection.sock.settimeout(remaining_time)

        response_body = _read_bounded_body(
            response.read1, set_response_timeout, deadline=deadline,
            provider_request_id=request_id,
        )
        return response.status, response_headers, response_body
    except SamAdapterError:
        raise
    except (socket.timeout, TimeoutError) as exc:
        raise SamAdapterError(
            "Meta SAM request exceeded its absolute duration limit",
            provider_request_id=request_id,
        ) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise SamAdapterError(
            f"Meta SAM transport failed ({type(exc).__name__})",
            provider_request_id=request_id,
        ) from exc
    finally:
        connection.close()


def _bounded_request_id(value: object) -> str | None:
    if isinstance(value, str) and value and len(value) <= 256 and value.isprintable():
        return value
    return None


def _interrupt(connection: http.client.HTTPSConnection) -> None:
    if connection.sock is not None:
        try:
            connection.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _call_with_absolute_deadline(
    operation: Callable[[], object],
    interrupt: Callable[[], None],
    *,
    deadline: float,
    provider_request_id: str | None,
) -> object:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SamAdapterError(
            "Meta SAM operation exceeded its absolute duration limit",
            provider_request_id=provider_request_id,
        )
    watchdog = threading.Timer(remaining, interrupt)
    watchdog.daemon = True
    watchdog.start()
    try:
        result = operation()
    except Exception as exc:
        if time.monotonic() >= deadline:
            raise SamAdapterError(
                "Meta SAM operation exceeded its absolute duration limit",
                provider_request_id=provider_request_id,
            ) from exc
        raise
    finally:
        watchdog.cancel()
    if time.monotonic() > deadline:
        raise SamAdapterError(
            "Meta SAM operation exceeded its absolute duration limit",
            provider_request_id=provider_request_id,
        )
    return result


def _read_bounded_body(
    read_chunk: Callable[[int], bytes],
    set_timeout: Callable[[float], None],
    *,
    deadline: float,
    provider_request_id: str | None,
) -> bytes:
    body = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SamAdapterError(
                "Meta SAM response exceeded its absolute duration limit",
                provider_request_id=provider_request_id,
            )
        set_timeout(remaining)
        chunk = read_chunk(min(64 * 1024, MAX_RESPONSE_BYTES + 1 - len(body)))
        if time.monotonic() > deadline:
            raise SamAdapterError(
                "Meta SAM response exceeded its absolute duration limit",
                provider_request_id=provider_request_id,
            )
        if not isinstance(chunk, bytes):
            raise SamAdapterError(
                "Meta SAM transport returned a non-binary response chunk",
                provider_request_id=provider_request_id,
            )
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            return bytes(body)


class MetaSamProcessor:
    def __init__(
        self,
        *,
        api_key: str,
        transport: Transport = _default_transport,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("an explicit Meta API key is required")
        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError("SAM timeout must be positive and at most 120 seconds")
        self._api_key = api_key
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    def validate_request(self, request: ProcessorRequest, observation_bytes: bytes) -> None:
        if request.provider_id != "meta" or request.model_id != MODEL_ID or request.model_version != MODEL_ID:
            raise ValueError("SAM request must bind the Meta sam-3.1 provider and model")
        if request.destination != API_DESTINATION:
            raise ValueError("SAM request destination does not match the fixed Meta API")
        if request.parameters_json != "{}":
            raise ValueError("SAM parameters must be empty until an explicit bounded parameter contract exists")
        if request.usage_ceiling.usd_micros < IMAGE_PRICE_USD_MICROS:
            raise ValueError("SAM request price ceiling is below the public image price ceiling")
        if request.usage_ceiling.frames != 0:
            raise ValueError("image-only SAM requests must authorize zero video frames")
        if not isinstance(observation_bytes, bytes) or not observation_bytes:
            raise ValueError("SAM input must be a non-empty PNG or JPEG image")
        if len(observation_bytes) > MAX_INPUT_BYTES:
            raise ValueError("SAM input exceeds the 10 MiB image limit")
        if not _image_mime(observation_bytes):
            raise ValueError("SAM input must be a PNG or JPEG image")
        if hashlib.sha256(observation_bytes).hexdigest() != request.observation_digest:
            raise ValueError("SAM input digest does not match the authorized observation")
        if not request.prompt or len(request.prompt) > MAX_PROMPT_CHARS:
            raise ValueError("SAM prompt must contain between 1 and 256 characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in request.prompt):
            raise ValueError("SAM concept prompt must not contain control characters")

    def process(
        self, request: ProcessorRequest, observation_bytes: bytes, attempt: AdapterAttempt
    ) -> AdapterResponse:
        self.validate_request(request, observation_bytes)
        if (
            attempt.case_id != request.case_id
            or attempt.phase != AcquisitionPhase.PROCESSOR_DERIVATION
            or attempt.state != AttemptState.DISPATCH_INTENT
            or attempt.request_digest != canonical_record_digest(request)
        ):
            raise ValueError("SAM dispatch attempt does not match the authorized request")

        image_mime = _image_mime(observation_bytes)
        data_url = f"data:{image_mime};base64,{base64.b64encode(observation_bytes).decode('ascii')}"
        payload = {
            "model": MODEL_ID,
            "input": [{
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": request.prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }],
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        started = time.monotonic()
        try:
            effective_timeout = min(
                self._timeout_seconds, request.usage_ceiling.duration_ms / 1000
            )
            if effective_timeout <= 0:
                raise ValueError("SAM request duration ceiling must be positive")
            status, response_headers, response_body = self._transport(
                API_URL, headers, body, effective_timeout
            )
        except ValueError:
            raise
        except SamAdapterError:
            raise
        except Exception as exc:
            raise SamAdapterError(f"Meta SAM transport failed ({type(exc).__name__})") from exc
        if (
            not isinstance(status, int)
            or isinstance(status, bool)
            or not isinstance(response_headers, dict)
            or not isinstance(response_body, bytes)
        ):
            raise SamAdapterError("Meta SAM transport returned a malformed response")
        request_id = _bounded_request_id(
            response_headers.get("x-request-id") or response_headers.get("X-Request-Id")
        )
        if status < 200 or status >= 300:
            raise SamAdapterError(f"Meta SAM API returned HTTP {status}", provider_request_id=request_id)
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise SamAdapterError("Meta SAM response exceeded the 8 MiB response limit", provider_request_id=request_id)
        try:
            result = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SamAdapterError("Meta SAM returned malformed JSON", provider_request_id=request_id) from exc
        if not isinstance(result, dict) or result.get("status") != "completed":
            raise SamAdapterError("Meta SAM response was not completed", provider_request_id=request_id)
        response_id = _bounded_request_id(result.get("id"))
        request_id = request_id or response_id
        output = result.get("output")
        if not isinstance(output, list):
            raise SamAdapterError("Meta SAM response omitted its output list", provider_request_id=request_id)
        text_parts: list[str] = []
        found_output_text = False
        for item in output:
            if not isinstance(item, dict):
                raise SamAdapterError("Meta SAM response contained malformed output", provider_request_id=request_id)
            if item.get("type") == "refusal":
                raise SamAdapterError("Meta SAM refused the request", provider_request_id=request_id)
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                raise SamAdapterError("Meta SAM response contained malformed message content", provider_request_id=request_id)
            for part in content:
                if not isinstance(part, dict):
                    raise SamAdapterError("Meta SAM response contained malformed content", provider_request_id=request_id)
                if part.get("type") == "refusal":
                    raise SamAdapterError("Meta SAM refused the request", provider_request_id=request_id)
                if part.get("type") == "output_text":
                    text = part.get("text")
                    if not isinstance(text, str):
                        raise SamAdapterError("Meta SAM output text was malformed", provider_request_id=request_id)
                    found_output_text = True
                    text_parts.append(text)
        if not found_output_text:
            raise SamAdapterError("Meta SAM response omitted output_text", provider_request_id=request_id)
        annotation = "\n".join(text_parts).encode("utf-8")
        if len(annotation) > MAX_RESPONSE_BYTES:
            raise SamAdapterError("Meta SAM annotation exceeded the 8 MiB response limit", provider_request_id=request_id)
        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        usage = ResourceUsage(
            usd_micros=IMAGE_PRICE_USD_MICROS,
            bytes=len(annotation),
            frames=0,
            duration_ms=duration_ms,
        )
        return AdapterResponse(
            payload=BytesIO(annotation), usage=usage, provider_request_id=request_id
        )


def _image_mime(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None
