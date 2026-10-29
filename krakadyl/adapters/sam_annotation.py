"""Keep SAM wire parsing separate from acquisition outcomes and inference."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Literal

from krakadyl.adapters.sam import MAX_RESPONSE_BYTES
from krakadyl.core.receipt import canonical_bytes

SAM_ANNOTATION_PROFILE = "sam3-image-v1-cdf2e8b5625a3471e6dab3be7127b80fa83beb0d"
MAX_RECORDS = 4096
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_CONFIDENCE_CHARS = 64
MAX_CONFIDENCE_EXPONENT = 18
_ASCII_WHITESPACE = b" \t\r\n"
_UINT = re.compile(rb"[0-9]+\Z")
_SINT = re.compile(rb"-?[0-9]+\Z")
_FRAME = re.compile(rb"<([0-9]+)f(?:;[^>]*)?>")
_TOKEN_NAME = re.compile(rb"[A-Za-z][A-Za-z0-9_.-]*\Z")
_CONFIDENCE = re.compile(
    rb"-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z"
)
_MASK_ALPHABET = frozenset(
    b"!#$%&'()*+-./0123456789:=?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`abcdefghijklmnopqrstuvwxyz{"
)


class SamAnnotationInputError(ValueError):
    """Raised when an annotation candidate exceeds the parser input contract."""


@dataclass(frozen=True, slots=True)
class SamAnnotationDiagnostic:
    code: str
    byte_offset: int | None


@dataclass(frozen=True, slots=True)
class SamImageRecord:
    object_id: str
    frame_index: int
    frame_width: int
    frame_height: int
    x1: int
    y1: int
    x2_inclusive: int
    y2_inclusive: int
    box_confidence: str | None
    mask_height: int
    mask_width: int
    mask_encoding: Literal["lossless", "one_bit"]
    mask_confidence: str | None
    mask_payload_start: int
    mask_payload_end: int


@dataclass(frozen=True, slots=True)
class SamAnnotationSidecar:
    schema_version: int
    profile_version: str
    candidate_digest: str
    status: Literal["empty", "parsed", "unsupported", "malformed"]
    records: tuple[SamImageRecord, ...]
    diagnostics: tuple[SamAnnotationDiagnostic, ...]
    sidecar_digest: str


class _ProfileStop(Exception):
    def __init__(self, status: Literal["unsupported", "malformed"], code: str, offset: int | None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.offset = offset


def parse_sam_annotation(candidate: bytes) -> SamAnnotationSidecar:
    """Keep mask decoding and acquisition decisions outside this structural view."""
    if not isinstance(candidate, bytes):
        raise SamAnnotationInputError("SAM annotation candidate must be bytes")
    if len(candidate) > MAX_RESPONSE_BYTES:
        raise SamAnnotationInputError("SAM annotation candidate exceeds the 8 MiB input limit")
    candidate_digest = hashlib.sha256(candidate).hexdigest()
    try:
        return _parse_candidate(candidate, candidate_digest)
    except _ProfileStop as exc:
        return _stopped(candidate_digest, exc.status, exc.code, exc.offset)


def _parse_candidate(candidate: bytes, candidate_digest: str) -> SamAnnotationSidecar:
    if candidate == b"":
        return _make_sidecar(candidate_digest, "empty", (), ())

    try:
        candidate.decode("ascii")
    except UnicodeDecodeError as exc:
        return _make_sidecar(
            candidate_digest,
            "malformed",
            (),
            (SamAnnotationDiagnostic("non_ascii_input", exc.start),),
        )

    line = candidate
    if line.endswith(b"\r\n"):
        line = line[:-2]
    elif line.endswith(b"\n"):
        line = line[:-1]
    if b"\n" in line or b"\r" in line:
        return _stopped(candidate_digest, "unsupported", "multiple_lines", None)
    if not line.strip(_ASCII_WHITESPACE):
        return _stopped(candidate_digest, "unsupported", "whitespace_only", None)
    if not line.startswith(b"<"):
        return _stopped(candidate_digest, "unsupported", "unstructured_output", 0)

    frame = _FRAME.match(line)
    if frame is None:
        return _stopped(candidate_digest, "malformed", "invalid_frame_header", 0)
    if b";" in frame.group(0):
        return _stopped(candidate_digest, "unsupported", "frame_header_fields", 0)
    frame_index = _parse_uint(frame.group(1), frame.start(1))
    if frame_index != 0:
        return _stopped(candidate_digest, "unsupported", "unsupported_frame", frame.start(1))

    cursor = frame.end()
    records: list[SamImageRecord] = []
    object_ids: set[int] = set()
    frame_dimensions: tuple[int, int] | None = None
    if cursor == len(line):
        return _stopped(candidate_digest, "malformed", "frame_without_records", cursor)

    while cursor < len(line):
        if line[cursor : cursor + 1] == b",":
            cursor += 1
            if cursor == len(line):
                return _stopped(candidate_digest, "malformed", "trailing_record_separator", cursor - 1)

        if len(records) >= MAX_RECORDS:
            return _stopped(candidate_digest, "unsupported", "record_limit_exceeded", cursor)

        id_start = cursor
        while cursor < len(line) and 48 <= line[cursor] <= 57:
            cursor += 1
        if cursor == id_start:
            return _stopped(candidate_digest, "malformed", "invalid_object_id", cursor)
        object_value = _parse_uint(line[id_start:cursor], id_start)
        object_id = line[id_start:cursor].decode("ascii")
        if object_value in object_ids:
            return _stopped(candidate_digest, "malformed", "duplicate_object_id", id_start)

        tokens: dict[str, dict[str, tuple[bytes, int]]] = {}
        while (
            cursor < len(line)
            and line[cursor : cursor + 1] != b","
            and not 48 <= line[cursor] <= 57
        ):
            if not line.startswith(b"<|", cursor):
                return _stopped(candidate_digest, "malformed", "expected_annotation_token", cursor)
            token_start = cursor
            name, fields, cursor = _read_token(line, cursor)
            if name not in {"box", "mask"}:
                return _stopped(candidate_digest, "unsupported", "unsupported_token", token_start)
            if name in tokens:
                return _stopped(candidate_digest, "malformed", f"duplicate_{name}_token", token_start)
            tokens[name] = fields

        if set(tokens) != {"box", "mask"}:
            return _stopped(candidate_digest, "malformed", "record_requires_box_and_mask", id_start)
        box = _parse_box(tokens["box"])
        mask = _parse_mask(tokens["mask"])
        if not (0 <= box["x1"] <= box["x2"] < box["width"]):
            return _stopped(candidate_digest, "malformed", "box_x_out_of_bounds", id_start)
        if not (0 <= box["y1"] <= box["y2"] < box["height"]):
            return _stopped(candidate_digest, "malformed", "box_y_out_of_bounds", id_start)
        if mask["height"] <= 0 or mask["width"] <= 0:
            return _stopped(candidate_digest, "malformed", "nonpositive_mask_dimensions", id_start)
        if mask["height"] * mask["width"] > MAX_SAFE_INTEGER:
            return _stopped(candidate_digest, "unsupported", "mask_dimensions_out_of_profile", id_start)
        current_dimensions = (box["width"], box["height"])
        if frame_dimensions is None:
            frame_dimensions = current_dimensions
        elif frame_dimensions != current_dimensions:
            return _stopped(candidate_digest, "malformed", "inconsistent_frame_dimensions", id_start)
        if mask["height"] >= box["height"] or mask["width"] >= box["width"]:
            return _stopped(candidate_digest, "unsupported", "mask_dimensions_out_of_profile", id_start)

        records.append(
            SamImageRecord(
                object_id=object_id,
                frame_index=0,
                frame_width=box["width"],
                frame_height=box["height"],
                x1=box["x1"],
                y1=box["y1"],
                x2_inclusive=box["x2"],
                y2_inclusive=box["y2"],
                box_confidence=box["confidence"],
                mask_height=mask["height"],
                mask_width=mask["width"],
                mask_encoding=mask["encoding"],
                mask_confidence=mask["confidence"],
                mask_payload_start=mask["payload_start"],
                mask_payload_end=mask["payload_end"],
            )
        )
        object_ids.add(object_value)

    return _make_sidecar(candidate_digest, "parsed", tuple(records), ())


def extract_mask_payload(
    candidate: bytes, sidecar: SamAnnotationSidecar, record: SamImageRecord
) -> bytes:
    """Verify digest links before exposing opaque payload bytes to a caller."""
    if not isinstance(candidate, bytes) or len(candidate) > MAX_RESPONSE_BYTES:
        raise SamAnnotationInputError("SAM annotation candidate must be bounded bytes")
    if not isinstance(sidecar, SamAnnotationSidecar) or not isinstance(record, SamImageRecord):
        raise ValueError("SAM mask reference has an invalid sidecar type")
    if (
        sidecar.schema_version != 1
        or sidecar.profile_version != SAM_ANNOTATION_PROFILE
        or sidecar.status != "parsed"
        or not isinstance(sidecar.records, tuple)
        or len(sidecar.records) > MAX_RECORDS
        or not all(isinstance(item, SamImageRecord) for item in sidecar.records)
        or not isinstance(sidecar.diagnostics, tuple)
        or len(sidecar.diagnostics) != 0
    ):
        raise ValueError("SAM annotation sidecar exceeds its structural limits")
    if record not in sidecar.records:
        raise ValueError("SAM mask reference is not part of a parsed sidecar")
    if hashlib.sha256(candidate).hexdigest() != sidecar.candidate_digest:
        raise ValueError("SAM annotation candidate digest does not match the sidecar")
    if _digest_sidecar(sidecar) != sidecar.sidecar_digest:
        raise ValueError("SAM annotation sidecar digest does not match its contents")
    start, end = record.mask_payload_start, record.mask_payload_end
    if not (0 <= start < end <= len(candidate)):
        raise ValueError("SAM mask payload range is outside its bound candidate")
    return candidate[start:end]


def _read_token(
    line: bytes, start: int
) -> tuple[str, dict[str, tuple[bytes, int]], int]:
    end = line.find(b"|>", start + 2)
    if end < 0:
        raise _ProfileStop("malformed", "unterminated_token", start)
    body = line[start + 2 : end]
    name, separator, remainder = body.partition(b";")
    if not _TOKEN_NAME.fullmatch(name):
        raise _ProfileStop("malformed", "invalid_token_name", start)
    if not separator:
        return name.decode("ascii"), {}, end + 2

    fields: dict[str, tuple[bytes, int]] = {}
    relative = len(name) + 1
    for segment in remainder.split(b";"):
        segment_start = start + 2 + relative
        relative += len(segment) + 1
        leading_whitespace = len(segment) - len(segment.lstrip(_ASCII_WHITESPACE))
        segment_start += leading_whitespace
        segment = segment.strip(_ASCII_WHITESPACE)
        if not segment:
            continue
        key_raw, equals, value_raw = segment.partition(b"=")
        key = key_raw.strip(_ASCII_WHITESPACE)
        if not key or not re.fullmatch(rb"[A-Za-z][A-Za-z0-9_.-]*", key):
            raise _ProfileStop("malformed", "invalid_field_name", segment_start)
        field_name = key.decode("ascii")
        if not equals:
            if field_name == "c":
                raise _ProfileStop("unsupported", "invalid_confidence", segment_start)
            if field_name in {"x1", "y1", "x2", "y2", "w", "h", "x", "y", "data"}:
                raise _ProfileStop("malformed", "field_missing_value", segment_start)
            raise _ProfileStop("unsupported", "unsupported_field", segment_start)
        if field_name in fields:
            if field_name == "c":
                raise _ProfileStop("unsupported", "duplicate_confidence", segment_start)
            raise _ProfileStop("malformed", "duplicate_field", segment_start)
        left_trim = len(value_raw) - len(value_raw.lstrip(_ASCII_WHITESPACE))
        value = value_raw.strip(_ASCII_WHITESPACE)
        value_start = segment_start + len(key_raw) + 1 + left_trim
        fields[field_name] = (value, value_start)
    return name.decode("ascii"), fields, end + 2


def _parse_box(fields: dict[str, tuple[bytes, int]]) -> dict[str, int | str | None]:
    supported = {"x1", "y1", "x2", "y2", "w", "h", "c"}
    if fields.keys() - supported:
        raise _ProfileStop("unsupported", "unsupported_box_field", None)
    required = {"x1", "y1", "x2", "y2", "w", "h"}
    if required - fields.keys():
        raise _ProfileStop("malformed", "box_missing_required_field", None)
    values = {
        key: _parse_sint(fields[key][0], fields[key][1])
        for key in ("x1", "y1", "x2", "y2")
    }
    values["width"] = _parse_uint(fields["w"][0], fields["w"][1])
    values["height"] = _parse_uint(fields["h"][0], fields["h"][1])
    if values["width"] <= 0 or values["height"] <= 0:
        raise _ProfileStop("malformed", "nonpositive_frame_dimensions", None)
    values["confidence"] = _parse_confidence(fields["c"]) if "c" in fields else None
    return values


def _parse_mask(fields: dict[str, tuple[bytes, int]]) -> dict[str, int | str | None]:
    supported = {"x", "y", "data", "c"}
    if fields.keys() - supported:
        raise _ProfileStop("unsupported", "unsupported_mask_field", None)
    if {"x", "y", "data"} - fields.keys():
        raise _ProfileStop("malformed", "mask_missing_required_field", None)
    if fields["x"][0] != b"0" or fields["y"][0] != b"0":
        raise _ProfileStop("malformed", "invalid_mask_origin", fields["x"][1])
    data, data_start = fields["data"]
    first_comma = data.find(b",")
    second_comma = data.find(b",", first_comma + 1) if first_comma >= 0 else -1
    if first_comma <= 0 or second_comma <= first_comma + 1 or second_comma + 1 >= len(data):
        raise _ProfileStop("malformed", "invalid_mask_data", data_start)
    height = _parse_uint(data[:first_comma], data_start)
    width = _parse_uint(data[first_comma + 1 : second_comma], data_start + first_comma + 1)
    encoded = data[second_comma + 1 :]
    marker, payload = encoded[:1], encoded[1:]
    if marker not in {b"~", b"!"} or not payload:
        raise _ProfileStop("malformed", "invalid_mask_encoding", data_start + second_comma + 1)
    if any(char not in _MASK_ALPHABET for char in payload):
        raise _ProfileStop("malformed", "invalid_mask_payload_alphabet", data_start + second_comma + 2)
    return {
        "height": height,
        "width": width,
        "encoding": "lossless" if marker == b"~" else "one_bit",
        "confidence": _parse_confidence(fields["c"]) if "c" in fields else None,
        "payload_start": data_start + second_comma + 2,
        "payload_end": data_start + len(data),
    }


def _parse_confidence(field: tuple[bytes, int]) -> str:
    value, offset = field
    if len(value) > MAX_CONFIDENCE_CHARS:
        raise _ProfileStop("unsupported", "confidence_limit_exceeded", offset)
    if not _CONFIDENCE.fullmatch(value):
        raise _ProfileStop("unsupported", "invalid_confidence", offset)
    exponent_match = re.search(rb"[eE]([+-]?[0-9]+)\Z", value)
    if exponent_match:
        exponent = int(exponent_match.group(1))
        if abs(exponent) > MAX_CONFIDENCE_EXPONENT:
            raise _ProfileStop("unsupported", "confidence_limit_exceeded", offset)
    confidence = Fraction(value.decode("ascii"))
    if confidence < 0 or confidence > 1:
        raise _ProfileStop("unsupported", "confidence_out_of_range", offset)
    return value.decode("ascii")


def _parse_uint(value: bytes, offset: int) -> int:
    if not _UINT.fullmatch(value):
        raise _ProfileStop("malformed", "invalid_integer", offset)
    if len(value) > 16:
        raise _ProfileStop("unsupported", "integer_limit_exceeded", offset)
    parsed = int(value)
    if parsed > MAX_SAFE_INTEGER:
        raise _ProfileStop("unsupported", "integer_limit_exceeded", offset)
    return parsed


def _parse_sint(value: bytes, offset: int) -> int:
    if not _SINT.fullmatch(value):
        raise _ProfileStop("malformed", "invalid_integer", offset)
    digits = value[1:] if value.startswith(b"-") else value
    if len(digits) > 16:
        raise _ProfileStop("unsupported", "integer_limit_exceeded", offset)
    parsed = int(value)
    if abs(parsed) > MAX_SAFE_INTEGER:
        raise _ProfileStop("unsupported", "integer_limit_exceeded", offset)
    return parsed


def _stopped(
    candidate_digest: str,
    status: Literal["unsupported", "malformed"],
    code: str,
    offset: int | None,
) -> SamAnnotationSidecar:
    return _make_sidecar(
        candidate_digest,
        status,
        (),
        (SamAnnotationDiagnostic(code, offset),),
    )


def _make_sidecar(
    candidate_digest: str,
    status: Literal["empty", "parsed", "unsupported", "malformed"],
    records: tuple[SamImageRecord, ...],
    diagnostics: tuple[SamAnnotationDiagnostic, ...],
) -> SamAnnotationSidecar:
    sidecar_digest = _digest_sidecar_fields(
        1, SAM_ANNOTATION_PROFILE, candidate_digest, status, records, diagnostics
    )
    return SamAnnotationSidecar(
        schema_version=1,
        profile_version=SAM_ANNOTATION_PROFILE,
        candidate_digest=candidate_digest,
        status=status,
        records=records,
        diagnostics=diagnostics,
        sidecar_digest=sidecar_digest,
    )


def _digest_sidecar(sidecar: SamAnnotationSidecar) -> str:
    return _digest_sidecar_fields(
        sidecar.schema_version,
        sidecar.profile_version,
        sidecar.candidate_digest,
        sidecar.status,
        sidecar.records,
        sidecar.diagnostics,
    )


def _digest_sidecar_fields(
    schema_version: int,
    profile_version: str,
    candidate_digest: str,
    status: str,
    records: tuple[SamImageRecord, ...],
    diagnostics: tuple[SamAnnotationDiagnostic, ...],
) -> str:
    payload = {
        "schema_version": schema_version,
        "profile_version": profile_version,
        "candidate_digest": candidate_digest,
        "status": status,
        "records": [asdict(record) for record in records],
        "diagnostics": [asdict(diagnostic) for diagnostic in diagnostics],
    }
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()
