#!/usr/bin/env python3
"""Normalize scoped numeric reference paragraphs without rewriting unrelated DOCX XML."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


WORDPROCESSINGML_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DEFAULT_LABEL_PATTERN = r"^\[(?P<number>\d+)\]\s*"
DEFAULT_REPLACEMENT_TEMPLATE = "[{number}] {reference}"


@dataclass(frozen=True)
class Paragraph:
    index: int
    start: int
    end: int
    xml: str
    text: str


@dataclass(frozen=True)
class Settings:
    references: dict[str, str]
    start_heading: str
    stop_heading: str | None
    start_occurrence: int
    stop_occurrence: int
    case_sensitive_headings: bool
    label_pattern: re.Pattern[str]
    replacement_template: str
    require_all_configured_references: bool


def compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def count_elements(xml: bytes, element_name: str) -> int:
    root = ET.fromstring(xml)
    return sum(1 for element in root.iter() if local_name(element.tag) == element_name)


def word_prefix(document_xml: str) -> str:
    match = re.search(
        rf'xmlns:([A-Za-z_][A-Za-z0-9_.-]*)="{re.escape(WORDPROCESSINGML_URI)}"',
        document_xml,
    )
    return match.group(1) if match else "w"


def paragraph_pattern(prefix: str) -> re.Pattern[str]:
    escaped = re.escape(prefix)
    return re.compile(rf"<{escaped}:p(?:\s[^>]*)?>.*?</{escaped}:p>", re.DOTALL)


def text_pattern(prefix: str) -> re.Pattern[str]:
    escaped = re.escape(prefix)
    return re.compile(
        rf"(<{escaped}:t(?:\s[^>]*)?>)(.*?)(</{escaped}:t>)",
        re.DOTALL,
    )


def paragraph_text(paragraph_xml: str, texts: re.Pattern[str]) -> str:
    return "".join(html.unescape(match.group(2)) for match in texts.finditer(paragraph_xml))


def collect_paragraphs(document_xml: str) -> tuple[list[Paragraph], re.Pattern[str]]:
    prefix = word_prefix(document_xml)
    paragraphs_re = paragraph_pattern(prefix)
    texts_re = text_pattern(prefix)
    paragraphs = [
        Paragraph(
            index=index,
            start=match.start(),
            end=match.end(),
            xml=match.group(0),
            text=compact_text(paragraph_text(match.group(0), texts_re)),
        )
        for index, match in enumerate(paragraphs_re.finditer(document_xml))
    ]
    return paragraphs, texts_re


def normalize_reference_map(raw: Any) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict) or not raw:
        return {}, ["Config field 'references' must be a non-empty object."]
    normalized: dict[str, str] = {}
    for raw_number, raw_reference in raw.items():
        number = str(raw_number).strip()
        if not number.isdigit() or int(number) < 1:
            errors.append(f"Reference key must be a positive integer: {raw_number!r}")
            continue
        canonical = str(int(number))
        reference = compact_text(raw_reference)
        if not reference:
            errors.append(f"Reference {canonical} has empty text.")
            continue
        if canonical in normalized:
            errors.append(f"Duplicate configured reference number after normalization: {canonical}")
            continue
        normalized[canonical] = reference
    return normalized, errors


def positive_int(config: dict[str, Any], key: str, default: int) -> tuple[int, str | None]:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default, f"Config field '{key}' must be a positive integer."
    return value, None


def boolean_value(
    config: dict[str, Any],
    key: str,
    default: bool,
) -> tuple[bool, str | None]:
    value = config.get(key, default)
    if not isinstance(value, bool):
        return default, f"Config field '{key}' must be a boolean."
    return value, None


def load_settings(config_path: Path) -> tuple[Settings | None, dict[str, Any], list[str]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        return None, {}, ["Reference config must be a JSON object."]
    errors: list[str] = []
    references, reference_errors = normalize_reference_map(config.get("references"))
    errors.extend(reference_errors)

    start_heading = compact_text(config.get("main_references_heading") or "References")
    stop_value = config.get("stop_at_heading", "Supporting Information")
    stop_heading = compact_text(stop_value) if stop_value is not None else None
    if not start_heading:
        errors.append("Config field 'main_references_heading' cannot be empty.")
    if stop_value is not None and not stop_heading:
        errors.append("Config field 'stop_at_heading' must be non-empty or null.")

    start_occurrence, error = positive_int(config, "main_references_heading_occurrence", 1)
    if error:
        errors.append(error)
    stop_occurrence, error = positive_int(config, "stop_at_heading_occurrence", 1)
    if error:
        errors.append(error)

    label_source = str(config.get("reference_label_pattern") or DEFAULT_LABEL_PATTERN)
    try:
        label_pattern = re.compile(label_source)
        if "number" not in label_pattern.groupindex:
            errors.append("Config field 'reference_label_pattern' must contain a named 'number' group.")
    except re.error as exc:
        label_pattern = re.compile(DEFAULT_LABEL_PATTERN)
        errors.append(f"Invalid reference_label_pattern: {exc}")

    replacement_template = str(
        config.get("replacement_template") or DEFAULT_REPLACEMENT_TEMPLATE
    )
    try:
        replacement_template.format(number="1", reference="Reference text")
    except (KeyError, ValueError) as exc:
        errors.append(f"Invalid replacement_template: {exc}")

    case_sensitive_headings, error = boolean_value(
        config,
        "case_sensitive_headings",
        True,
    )
    if error:
        errors.append(error)
    require_all_configured_references, error = boolean_value(
        config,
        "require_all_configured_references",
        True,
    )
    if error:
        errors.append(error)

    settings = Settings(
        references=references,
        start_heading=start_heading,
        stop_heading=stop_heading,
        start_occurrence=start_occurrence,
        stop_occurrence=stop_occurrence,
        case_sensitive_headings=case_sensitive_headings,
        label_pattern=label_pattern,
        replacement_template=replacement_template,
        require_all_configured_references=require_all_configured_references,
    )
    return (None if errors else settings), config, errors


def heading_equal(left: str, right: str, case_sensitive: bool) -> bool:
    if case_sensitive:
        return compact_text(left) == compact_text(right)
    return compact_text(left).casefold() == compact_text(right).casefold()


def nth_index(indices: list[int], occurrence: int) -> int | None:
    return indices[occurrence - 1] if len(indices) >= occurrence else None


def find_scope(
    paragraphs: list[Paragraph],
    settings: Settings,
) -> tuple[int | None, int | None, list[str]]:
    errors: list[str] = []
    starts = [
        paragraph.index
        for paragraph in paragraphs
        if heading_equal(
            paragraph.text,
            settings.start_heading,
            settings.case_sensitive_headings,
        )
    ]
    start = nth_index(starts, settings.start_occurrence)
    if start is None:
        errors.append(
            f"Start heading occurrence {settings.start_occurrence} not found: "
            f"{settings.start_heading!r}"
        )
        return None, None, errors

    if settings.stop_heading is None:
        return start, len(paragraphs), errors

    stops = [
        paragraph.index
        for paragraph in paragraphs
        if paragraph.index > start
        and heading_equal(
            paragraph.text,
            settings.stop_heading,
            settings.case_sensitive_headings,
        )
    ]
    stop = nth_index(stops, settings.stop_occurrence)
    if stop is None:
        errors.append(
            f"Stop heading occurrence {settings.stop_occurrence} not found after "
            f"the start heading: {settings.stop_heading!r}"
        )
    return start, stop, errors


def canonical_number(raw_number: str) -> str:
    return str(int(raw_number))


def plan_replacements(
    paragraphs: list[Paragraph],
    start: int,
    stop: int,
    settings: Settings,
) -> tuple[dict[int, str], dict[str, Any], list[str]]:
    replacements: dict[int, str] = {}
    encountered: list[str] = []
    unconfigured: list[str] = []
    duplicate_numbers: list[str] = []
    invalid_numbers: list[str] = []
    for paragraph in paragraphs:
        if not start < paragraph.index < stop:
            continue
        match = settings.label_pattern.match(paragraph.text)
        if not match:
            continue
        raw_number = match.group("number")
        if not raw_number.isdigit() or int(raw_number) < 1:
            if raw_number not in invalid_numbers:
                invalid_numbers.append(raw_number)
            continue
        number = canonical_number(raw_number)
        if number in encountered and number not in duplicate_numbers:
            duplicate_numbers.append(number)
        encountered.append(number)
        if number not in settings.references:
            if number not in unconfigured:
                unconfigured.append(number)
            continue
        replacements[paragraph.index] = settings.replacement_template.format(
            number=number,
            reference=settings.references[number],
        )

    missing_configured = sorted(
        set(settings.references) - set(encountered),
        key=int,
    )
    errors: list[str] = []
    if not encountered:
        errors.append("No reference paragraphs matched within the configured scope.")
    if unconfigured:
        errors.append(
            "Reference paragraphs lack configured text: "
            + ", ".join(sorted(unconfigured, key=int))
        )
    if duplicate_numbers:
        errors.append(
            "Duplicate reference numbers in the configured scope: "
            + ", ".join(sorted(duplicate_numbers, key=int))
        )
    if invalid_numbers:
        errors.append(
            "Reference labels produced non-positive-integer numbers: "
            + ", ".join(repr(number) for number in invalid_numbers)
        )
    if settings.require_all_configured_references and missing_configured:
        errors.append(
            "Configured references are absent from the manuscript scope: "
            + ", ".join(missing_configured)
        )

    details = {
        "encountered_reference_numbers": encountered,
        "unconfigured_reference_numbers": sorted(unconfigured, key=int),
        "duplicate_reference_numbers": sorted(duplicate_numbers, key=int),
        "invalid_reference_numbers": invalid_numbers,
        "missing_configured_reference_numbers": missing_configured,
    }
    return replacements, details, errors


def replace_text_nodes(
    paragraph_xml: str,
    replacement: str,
    texts_re: re.Pattern[str],
) -> str:
    matches = list(texts_re.finditer(paragraph_xml))
    if not matches:
        raise ValueError("Target reference paragraph has no Word text nodes.")
    escaped = html.escape(replacement, quote=False)
    output: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        output.append(paragraph_xml[cursor : match.start()])
        output.append(match.group(1))
        output.append(escaped if index == 0 else "")
        output.append(match.group(3))
        cursor = match.end()
    output.append(paragraph_xml[cursor:])
    return "".join(output)


def apply_replacements(
    document_xml: str,
    paragraphs: list[Paragraph],
    replacements: dict[int, str],
    texts_re: re.Pattern[str],
) -> str:
    output: list[str] = []
    cursor = 0
    for paragraph in paragraphs:
        if paragraph.index not in replacements:
            continue
        output.append(document_xml[cursor : paragraph.start])
        output.append(
            replace_text_nodes(
                paragraph.xml,
                replacements[paragraph.index],
                texts_re,
            )
        )
        cursor = paragraph.end
    output.append(document_xml[cursor:])
    return "".join(output)


def validate_replacements(
    document_xml: str,
    replacements: dict[int, str],
) -> list[str]:
    paragraphs, _ = collect_paragraphs(document_xml)
    by_index = {paragraph.index: paragraph.text for paragraph in paragraphs}
    errors = [
        f"Reference paragraph {index} does not match its configured replacement."
        for index, expected in replacements.items()
        if by_index.get(index) != compact_text(expected)
    ]
    return errors


def paragraph_skeleton(
    paragraph_xml: str,
    texts_re: re.Pattern[str],
) -> str:
    return texts_re.sub(lambda match: match.group(1) + match.group(3), paragraph_xml)


def validate_document_preservation(
    original_xml: str,
    updated_xml: str,
    replacement_indices: set[int],
) -> tuple[dict[str, bool], list[str]]:
    original_paragraphs, original_texts_re = collect_paragraphs(original_xml)
    updated_paragraphs, updated_texts_re = collect_paragraphs(updated_xml)
    paragraph_count_unchanged = len(original_paragraphs) == len(updated_paragraphs)
    untouched_paragraphs_unchanged = paragraph_count_unchanged and all(
        original.xml == updated.xml
        for original, updated in zip(original_paragraphs, updated_paragraphs)
        if original.index not in replacement_indices
    )
    target_paragraph_structure_unchanged = paragraph_count_unchanged and all(
        paragraph_skeleton(original_paragraphs[index].xml, original_texts_re)
        == paragraph_skeleton(updated_paragraphs[index].xml, updated_texts_re)
        for index in replacement_indices
    )
    checks = {
        "paragraph_count_unchanged": paragraph_count_unchanged,
        "untouched_paragraphs_unchanged": untouched_paragraphs_unchanged,
        "target_paragraph_structure_unchanged": target_paragraph_structure_unchanged,
    }
    errors = [
        message
        for passed, message in (
            (paragraph_count_unchanged, "Document paragraph count changed."),
            (
                untouched_paragraphs_unchanged,
                "A paragraph outside the target bibliography changed.",
            ),
            (
                target_paragraph_structure_unchanged,
                "Non-text structure changed inside a target reference paragraph.",
            ),
        )
        if not passed
    ]
    return checks, errors


def write_docx(
    input_docx: Path,
    output_docx: Path,
    document_xml: bytes,
) -> dict[str, Any]:
    output_docx.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_docx.name}.",
        suffix=".tmp",
        dir=output_docx.parent,
    )
    os.close(descriptor)
    Path(temporary_name).unlink()
    try:
        with zipfile.ZipFile(input_docx, "r") as zin, zipfile.ZipFile(
            temporary_name,
            "w",
        ) as zout:
            zout.comment = zin.comment
            for info in zin.infolist():
                data = (
                    document_xml
                    if info.filename == "word/document.xml"
                    else zin.read(info.filename)
                )
                zout.writestr(info, data)
        with zipfile.ZipFile(input_docx, "r") as before, zipfile.ZipFile(
            temporary_name,
            "r",
        ) as after:
            before_names = before.namelist()
            after_names = after.namelist()
            unchanged_parts = all(
                before.read(name) == after.read(name)
                for name in before_names
                if name != "word/document.xml"
            )
            bad_member = after.testzip()
        package_validation = {
            "zip_integrity_ok": bad_member is None,
            "bad_zip_member": bad_member,
            "package_member_names_unchanged": before_names == after_names,
            "non_document_parts_unchanged": unchanged_parts,
        }
        if (
            package_validation["zip_integrity_ok"]
            and package_validation["package_member_names_unchanged"]
            and package_validation["non_document_parts_unchanged"]
        ):
            Path(temporary_name).replace(output_docx)
            package_validation["output_promoted"] = True
        else:
            package_validation["output_promoted"] = False
        return package_validation
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def base_report(
    args: argparse.Namespace,
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "input_docx": str(Path(args.input_docx)),
        "output_docx": str(Path(args.output_docx)),
        "config": str(Path(args.config)),
        "reference_style": config.get("reference_style"),
        "scope": {},
        "normalized_reference_numbers": [],
        "diagnostics": {},
        "preservation": {},
        "validation": {"ok": False, "errors": []},
        "warnings": [],
        "output_written": False,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    input_docx = Path(args.input_docx)
    output_docx = Path(args.output_docx)
    config_path = Path(args.config)
    report_path = (
        Path(args.report_json)
        if args.report_json
        else output_docx.with_suffix(".reference_polish_report.json")
    )

    settings, config, errors = load_settings(config_path)
    report = base_report(args, config)
    if input_docx.resolve() == output_docx.resolve():
        errors.append("Input and output DOCX paths must differ.")
    if errors or settings is None:
        report["validation"]["errors"] = errors
        write_json(report_path, report)
        return report

    with zipfile.ZipFile(input_docx, "r") as zin:
        original_xml = zin.read("word/document.xml")
        input_bad_member = zin.testzip()
    original_text = original_xml.decode("utf-8")
    paragraphs, texts_re = collect_paragraphs(original_text)
    start, stop, scope_errors = find_scope(paragraphs, settings)
    errors.extend(scope_errors)
    report["scope"] = {
        "start_heading": settings.start_heading,
        "stop_heading": settings.stop_heading,
        "start_heading_occurrence": settings.start_occurrence,
        "stop_heading_occurrence": settings.stop_occurrence,
        "start_paragraph_index": start,
        "stop_paragraph_index": stop,
    }

    replacements: dict[int, str] = {}
    details: dict[str, Any] = {}
    if start is not None and stop is not None:
        replacements, details, planning_errors = plan_replacements(
            paragraphs,
            start,
            stop,
            settings,
        )
        errors.extend(planning_errors)
    report["diagnostics"] = details
    report["normalized_reference_numbers"] = [
        canonical_number(
            settings.label_pattern.match(paragraphs[index].text).group("number")
        )
        for index in sorted(replacements)
    ]

    omml_before = count_elements(original_xml, "oMath")
    drawings_before = count_elements(original_xml, "drawing")
    report["preservation"] = {
        "input_zip_integrity_ok": input_bad_member is None,
        "input_bad_zip_member": input_bad_member,
        "omml_equation_elements_before": omml_before,
        "drawing_elements_before": drawings_before,
        "document_xml_sha256_before": sha256(original_xml),
    }
    if input_bad_member:
        errors.append(f"Input DOCX has a corrupt ZIP member: {input_bad_member}")

    if errors:
        report["validation"]["errors"] = errors
        write_json(report_path, report)
        return report

    updated_text = apply_replacements(
        original_text,
        paragraphs,
        replacements,
        texts_re,
    )
    updated_xml = updated_text.encode("utf-8")
    errors.extend(validate_replacements(updated_text, replacements))
    document_checks, document_errors = validate_document_preservation(
        original_text,
        updated_text,
        set(replacements),
    )
    errors.extend(document_errors)
    try:
        ET.fromstring(updated_xml)
    except ET.ParseError as exc:
        errors.append(f"Updated document.xml is not parseable: {exc}")

    omml_after = count_elements(updated_xml, "oMath")
    drawings_after = count_elements(updated_xml, "drawing")
    if omml_after != omml_before:
        errors.append(
            f"OMML equation element count changed from {omml_before} to {omml_after}."
        )
    if drawings_after != drawings_before:
        errors.append(
            f"Drawing element count changed from {drawings_before} to {drawings_after}."
        )

    report["preservation"].update(
        {
            "omml_equation_elements_after": omml_after,
            "drawing_elements_after": drawings_after,
            "document_xml_sha256_after": sha256(updated_xml),
            **document_checks,
        }
    )
    if errors:
        report["validation"]["errors"] = errors
        write_json(report_path, report)
        return report

    package_validation = write_docx(input_docx, output_docx, updated_xml)
    report["preservation"].update(package_validation)
    if not package_validation["zip_integrity_ok"]:
        errors.append(
            "Output DOCX ZIP validation failed: "
            + str(package_validation["bad_zip_member"])
        )
    if not package_validation["package_member_names_unchanged"]:
        errors.append("DOCX package member names changed.")
    if not package_validation["non_document_parts_unchanged"]:
        errors.append("A non-document DOCX package part changed.")

    report["output_written"] = bool(package_validation["output_promoted"])
    report["validation"] = {"ok": not errors, "errors": errors}
    write_json(report_path, report)
    if report["output_written"]:
        print(f"Wrote {output_docx}")
    print(f"Wrote {report_path}")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-docx", required=True)
    parser.add_argument("--output-docx", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--report-json", default="")
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    raise SystemExit(0 if result["validation"]["ok"] else 2)
