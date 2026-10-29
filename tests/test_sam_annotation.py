from dataclasses import replace
import hashlib

import pytest

from krakadyl.adapters.sam_annotation import (
    SamAnnotationInputError,
    extract_mask_payload,
    parse_sam_annotation,
)


def _record(object_id="7", *, x1="1", x2="4", confidence="7.5e-1"):
    return (
        f"{object_id}<|box;y2=5;h=24;x2={x2};w=32;y1=2;x1={x1};c={confidence}|>"
        f"<|mask;data=2,3,~!!!!M;c=0.75;y=0;x=0|>"
    )


def test_image_profile_parses_ordered_fields_and_keeps_mask_payload_opaque():
    candidate = ("<0f>" + _record() + "," + _record("9", x1="10", x2="12")).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "parsed"
    assert parsed.candidate_digest == hashlib.sha256(candidate).hexdigest()
    assert parsed.schema_version == 1
    assert len(parsed.records) == 2
    first = parsed.records[0]
    assert (first.object_id, first.frame_index) == ("7", 0)
    assert (first.x1, first.y1, first.x2_inclusive, first.y2_inclusive) == (1, 2, 4, 5)
    assert (first.frame_width, first.frame_height) == (32, 24)
    assert (first.mask_height, first.mask_width, first.mask_encoding) == (2, 3, "lossless")
    assert first.box_confidence == "7.5e-1"
    assert first.mask_confidence == "0.75"
    assert extract_mask_payload(candidate, parsed, first) == b"!!!!M"


def test_box_and_mask_tokens_can_appear_in_either_order():
    candidate = (
        b"<0f>7<|mask;x=0;y=0;data=2,3,~!!!!M|>"
        b"<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|>"
    )

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "parsed"
    assert len(parsed.records) == 1
    assert extract_mask_payload(candidate, parsed, parsed.records[0]) == b"!!!!M"


def test_whitespace_around_fields_preserves_mask_offsets_with_final_crlf():
    candidate = (
        b"<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|>"
        b"<|mask; x = 0 ; y = 0 ; data=2,3,~!!!!M |>\r\n"
    )

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "parsed"
    assert extract_mask_payload(candidate, parsed, parsed.records[0]) == b"!!!!M"


def test_object_id_lexeme_is_preserved():
    candidate = ("<0f>" + _record("007")).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "parsed"
    assert parsed.records[0].object_id == "007"


def test_object_ids_with_equal_numeric_value_cannot_alias_within_frame():
    candidate = ("<0f>" + _record("007") + "," + _record("7")).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "malformed"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "duplicate_object_id"


def test_frame_dimensions_must_match_across_records():
    first = _record("7")
    second = _record("9").replace("w=32", "w=64").replace("h=24", "h=48")
    candidate = ("<0f>" + first + "," + second).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "malformed"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "inconsistent_frame_dimensions"


def test_mask_dimensions_outside_hosted_subset_are_unsupported():
    candidate = (
        b"<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|>"
        b"<|mask;x=0;y=0;data=2,32,~!!!!M|>"
    )

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "unsupported"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "mask_dimensions_out_of_profile"


def test_optional_record_commas_and_adjacent_records_follow_pinned_profile():
    candidate = ("<0f>," + _record("7") + _record("9")).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "parsed"
    assert tuple(record.object_id for record in parsed.records) == ("7", "9")


def test_malformed_later_record_does_not_leave_a_valid_prefix():
    first = _record("7")
    second = "9<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|>"
    candidate = ("<0f>" + first + "," + second).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "malformed"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "record_requires_box_and_mask"


def test_empty_whitespace_and_final_line_endings_are_distinct():
    assert parse_sam_annotation(b"").status == "empty"
    assert parse_sam_annotation(b"   ").status == "unsupported"
    assert parse_sam_annotation(("<0f>" + _record() + "\n").encode()).status == "parsed"
    assert parse_sam_annotation(("<0f>" + _record() + "\r\n").encode()).status == "parsed"
    assert parse_sam_annotation(("<0f>" + _record() + "\n\n").encode()).status == "unsupported"


@pytest.mark.parametrize(
    "candidate",
    [
        b"<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|>",
        b"<0f>7<|box;x1=1;x1=1;y1=2;x2=4;y2=5;w=32;h=24|><|mask;x=0;y=0;data=2,3,~!!!!M|>",
        b"<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|><|mask;x=0;y=0;data=2,3,?!!!!M|>",
        b"<0f>7<|box;x1=1;y1=2;x2=40;y2=5;w=32;h=24|><|mask;x=0;y=0;data=2,3,~!!!!M|>",
        "<0f>٧<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|><|mask;x=0;y=0;data=2,3,~!!!!M|>".encode("utf-8"),
        b"<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|><|mask;x=0;y=0;data=2,3,~!!!!M|><|mask;x=0;y=0;data=2,3,~!!!!M|>",
    ],
)
def test_malformed_records_are_all_or_nothing(candidate):
    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "malformed"
    assert parsed.records == ()
    assert len(parsed.diagnostics) == 1


def test_mask_dimension_product_over_safe_limit_is_unsupported_without_allocation():
    candidate = (
        b"<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24|>"
        b"<|mask;x=0;y=0;data=9007199254740991,2,~!!!!M|>"
    )

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "unsupported"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "mask_dimensions_out_of_profile"


def test_unknown_protocol_field_is_unsupported_without_partial_records():
    candidate = (
        "<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24;future=1|>"
        "<|mask;x=0;y=0;data=2,3,~!!!!M|>"
    ).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "unsupported"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "unsupported_box_field"


def test_record_count_above_profile_cap_is_unsupported_without_records():
    candidate = ("<0f>" + ",".join(_record(str(index)) for index in range(4097))).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "unsupported"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "record_limit_exceeded"


def test_valid_out_of_profile_frame_returns_unsupported_without_records():
    candidate = ("<2f>" + _record()).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "unsupported"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "unsupported_frame"


@pytest.mark.parametrize(
    "confidence_fields",
    ["c=1.01", "c=invalid", "c=0.5;c=0.5", "c"],
)
def test_invalid_optional_confidence_is_unsupported_without_records(confidence_fields):
    candidate = (
        "<0f>7<|box;x1=1;y1=2;x2=4;y2=5;w=32;h=24;"
        + confidence_fields
        + "|><|mask;x=0;y=0;data=2,3,~!!!!M|>"
    ).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "unsupported"
    assert parsed.records == ()


def test_candidate_binding_is_checked_before_mask_offset_is_used():
    candidate = ("<0f>" + _record()).encode("ascii")
    parsed = parse_sam_annotation(candidate)

    with pytest.raises(ValueError, match="candidate digest"):
        extract_mask_payload(candidate + b"x", parsed, parsed.records[0])


def test_sidecar_tampering_is_detected_before_payload_slice():
    candidate = ("<0f>" + _record()).encode("ascii")
    parsed = parse_sam_annotation(candidate)
    changed_record = replace(parsed.records[0], mask_payload_start=0)
    changed_sidecar = replace(parsed, records=(changed_record,))

    with pytest.raises(ValueError, match="sidecar digest"):
        extract_mask_payload(candidate, changed_sidecar, changed_record)


def test_confidence_exponent_is_bounded_before_exact_conversion():
    candidate = ("<0f>" + _record(confidence="1e999999999999999999999")).encode("ascii")

    parsed = parse_sam_annotation(candidate)

    assert parsed.status == "unsupported"
    assert parsed.records == ()
    assert parsed.diagnostics[0].code == "confidence_limit_exceeded"


def test_sidecar_digest_is_deterministic_and_candidate_bound():
    candidate = ("<0f>" + _record()).encode("ascii")

    first = parse_sam_annotation(candidate)
    second = parse_sam_annotation(candidate)
    changed = parse_sam_annotation(candidate + b"\n")

    assert first.sidecar_digest == second.sidecar_digest
    assert first.candidate_digest != changed.candidate_digest
    assert first.sidecar_digest != changed.sidecar_digest


def test_wrong_type_and_oversized_input_fail_before_parsing():
    with pytest.raises(SamAnnotationInputError, match="bytes"):
        parse_sam_annotation("<0f>")
    with pytest.raises(SamAnnotationInputError, match="8 MiB"):
        parse_sam_annotation(b"x" * (8 * 1024 * 1024 + 1))
