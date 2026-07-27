#!/usr/bin/env python3
"""Select sentence-level manuscript citations from a bounded source library."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.5"
SCHEMA_VERSION = 2

SELECTOR_PROMPT = """You are selecting citations for a computational chemistry manuscript.

You will receive sentence packets. Each packet contains one manuscript sentence, a sentence type, and a small candidate citation set retrieved from a bounded source library.

Strict rules:
1. Use only candidate citation_key values supplied in the packet.
2. Return zero citations when no candidate directly supports the sentence.
3. Prefer primary_project_pdf candidates for literature/background claims about the catalyst system.
4. Use second_neighbor_reference candidates mainly for standard methods, software, functionals, PAW, k-point sampling, thermodynamic/electrochemical formalisms, and canonical reference conventions.
5. Do not cite second-neighbor sources for new calculated results, counts, convergence outcomes, or claims unique to the current project.
6. Do not cite a VASP paper merely because a sentence says the present calculations were not executed with VASP.
7. Do not cite sentences whose support is the manuscript's own figure, for example sentences centered on "Fig. 1", "Fig. 3", or "Fig. S1", unless the sentence makes an explicit literature or experimental comparison.
8. Keep citation sets small: normally 1-3 keys.
9. If unsure, return no citation or mark needs_human_check true.

Return JSON only.

Schema:
{
  "decisions": [
    {
      "sentence_id": "S001",
      "citation_keys": ["Key1"],
      "confidence": "high | medium | low",
      "needs_human_check": false,
      "reason": "Concise support rationale."
    }
  ]
}
"""

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "no", "not", "of", "on", "or", "that", "the",
    "their", "these", "this", "to", "used", "using", "was", "were", "with",
    "without", "where", "which", "each", "all", "both", "same", "than",
}

PRIMARY_SYSTEM_KEYS: set[str] = set()

ALIAS_KEYWORDS = {
    "vasp": ["Kresse1996", "Kresse1999"],
    "vienna ab initio": ["Kresse1996"],
    "plane wave": ["Kresse1996"],
    "cutoff": ["Kresse1996"],
    "paw": ["Blochl1994", "Kresse1999", "Kresse19992"],
    "projector augmented wave": ["Blochl1994", "Kresse1999", "Kresse19992"],
    "pbe": ["Perdew1996"],
    "perdew": ["Perdew1996"],
    "burke": ["Perdew1996"],
    "ernzerhof": ["Perdew1996"],
    "gga": ["Perdew1996"],
    "k-point": ["Monkhorst1976"],
    "k point": ["Monkhorst1976"],
    "monkhorst": ["Monkhorst1976"],
    "computational hydrogen electrode": ["Nrskov2004", "K20052"],
    "che": ["Nrskov2004", "K20052"],
    "rhe": ["Nrskov2004", "K20052"],
    "reversible hydrogen electrode": ["Nrskov2004", "K20052"],
    "0 v versus rhe": ["Nrskov2004", "K20052"],
    "0 v versus the reversible hydrogen electrode": ["Nrskov2004", "K20052"],
    "hydrogen chemical potential": ["Nrskov2004", "K20052"],
    "potential-dependent": ["Nrskov2004", "K20052"],
    "electron-transfer": ["Nrskov2004", "K20052"],
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_default_env() -> None:
    cwd = Path.cwd()
    for path in (cwd / ".env", cwd / "DEPENDENCY" / ".env"):
        load_env_file(path)


def output_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct:
        return direct
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object.")
    return data


def call_openai(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"OpenAI API request failed: {exc.reason}") from exc


def normalize_text(text: str) -> str:
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace("×", "x").replace("Δ", "delta")
    text = re.sub(r"MoS\s*2", "mos2", text, flags=re.IGNORECASE)
    return text.lower()


def tokens(text: str) -> list[str]:
    normalized = normalize_text(text)
    raw = re.findall(r"[a-z0-9][a-z0-9_\-]*", normalized)
    return [t for t in raw if len(t) > 1 and t not in STOPWORDS]


def split_sentences(text: str) -> list[str]:
    protected = text
    replacements = {
        "e.g.": "e@@g@@",
        "i.e.": "i@@e@@",
        "vs.": "vs@@",
        "Fig.": "Fig@@",
        "Figs.": "Figs@@",
        "Eq.": "Eq@@",
        "Eqs.": "Eqs@@",
        "Ref.": "Ref@@",
        "Refs.": "Refs@@",
        "No.": "No@@",
        "Å−1": "Å−1",
    }
    for old, new in replacements.items():
        protected = protected.replace(old, new)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", protected)
    sentences = []
    reverse = {v: k for k, v in replacements.items()}
    for part in parts:
        sentence = part
        for old, new in reverse.items():
            sentence = sentence.replace(old, new)
        sentence = sentence.strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def compact_authors(authors: Any) -> str:
    if not isinstance(authors, list):
        return ""
    return ", ".join(str(x) for x in authors[:6])


def source_evidence_text(rec: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("citation_key", "title", "year", "doi", "raw_reference", "abstract_excerpt", "collection"):
        value = rec.get(key)
        if value:
            chunks.append(str(value))
    if rec.get("authors"):
        chunks.append(compact_authors(rec.get("authors")))
    for ctx in rec.get("citation_contexts", [])[:4]:
        sentence = ctx.get("sentence")
        if sentence:
            chunks.append(str(sentence))
    return " ".join(chunks)


def build_index(sources: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for rec in sources.get("primary_papers", []) + sources.get("second_neighbor_references", []):
        if not rec.get("citation_key"):
            continue
        source_id = rec.get("paper_id") or rec.get("reference_id") or rec.get("citation_key")
        text = source_evidence_text(rec)
        token_counts = Counter(tokens(text))
        records.append({
            "source_id": source_id,
            "citation_key": rec["citation_key"],
            "source_role": rec.get("source_role"),
            "title": rec.get("title"),
            "authors": rec.get("authors", []),
            "year": rec.get("year"),
            "doi": rec.get("doi"),
            "raw_reference": rec.get("raw_reference"),
            "collection": rec.get("collection"),
            "citation_contexts": rec.get("citation_contexts", []),
            "source_reference_numbers": rec.get("source_reference_numbers", []),
            "evidence_text": text,
            "tokens": token_counts,
        })
    return records


def classify_sentence(sentence: str, section_id: str) -> str:
    s = normalize_text(sentence)
    if re.search(r"\bfig\.?\s+s?\d+", s):
        if not any(x in s for x in ("reported", "observed", "prior", "experiment", "experimental")):
            return "project_specific_result_or_scope"
    if re.search(r"\b(32|all 32|five relaxations|no imaginary|reached the convergence)\b", s):
        return "project_specific_result_or_scope"
    if "not executed as vasp" in s or "no transition-state" in s or "no nudged elastic" in s:
        return "project_specific_scope"
    if re.search(r"\b(vasp|paw|projector augmented wave|pbe|perdew|burke|ernzerhof|k-point|monkhorst|plane-wave|cutoff|spin polarization)\b", s):
        return "method_formalism"
    if re.search(r"\b(computational hydrogen electrode|che|rhe|reversible hydrogen electrode|potential|electron-transfer|free-energy|free energies|free energy|hydrogen chemical potential|liquid water|aqueous hydroxide)\b", s):
        return "electrochemical_formalism"
    if re.search(r"\b(hypothesis|hypothesize|rationale|motivated|motivation|strategy|design principle|literature gap|gap|suggests|indicates|therefore|accordingly|we target|we examined|selected|chosen)\b", s):
        return "strategy_rationale"
    if re.search(r"\b(prior|reported|observed|previous|literature|experiment|experimental|catalyst|catalysis|reaction|activity|selectivity|stability|performance)\b", s):
        return "literature_background"
    if section_id == "vibrational_free_energy_corrections":
        return "method_formalism"
    return "uncited_method_description"


def alias_scores(sentence: str, available_keys: set[str]) -> dict[str, float]:
    normalized = normalize_text(sentence)
    scores: dict[str, float] = {}
    for phrase, keys in ALIAS_KEYWORDS.items():
        if phrase in normalized:
            for key in keys:
                if key in available_keys:
                    scores[key] = scores.get(key, 0.0) + 14.0
    return scores


def should_skip_sentence(sentence: str, sentence_type: str) -> bool:
    s = normalize_text(sentence)
    if sentence_type == "uncited_method_description":
        return True
    if sentence_type.startswith("project_specific"):
        if not any(x in s for x in ("prior", "reference", "reported", "observed")):
            return True
    if "reported relaxations were not executed as vasp" in s:
        return True
    if "relaxations used identical settings" in s:
        return True
    if "spin polarization" in s:
        return True
    if "gas-phase molecules were treated" in s:
        return True
    if "same surface cell" in s and "enable direct thermodynamic comparisons" in s:
        return True
    if re.search(r"\bfig\.?\s+s?\d+", s):
        if not any(x in s for x in ("reported", "observed", "prior", "experiment", "experimental")):
            return True
    return False


def rank_candidates(
    sentence: str,
    sentence_type: str,
    index: list[dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    query_tokens = Counter(tokens(sentence))
    available_keys = {rec["citation_key"] for rec in index}
    aliases = alias_scores(sentence, available_keys)
    ranked: list[dict[str, Any]] = []
    normalized_sentence = normalize_text(sentence)
    for rec in index:
        score = aliases.get(rec["citation_key"], 0.0)
        overlap = 0.0
        for tok, count in query_tokens.items():
            if tok in rec["tokens"]:
                overlap += min(count, rec["tokens"][tok]) * (1.0 + math.log(1 + rec["tokens"][tok]))
        score += overlap

        if sentence_type == "strategy_rationale":
            if rec["source_role"] == "primary_project_pdf":
                score *= 1.75
            if rec.get("collection") in {"strategy", "paper_search", "papers", "literature"}:
                score += 4.0
            if rec["source_role"] == "second_neighbor_reference":
                score *= 0.45
        elif sentence_type == "literature_background":
            if rec["source_role"] == "primary_project_pdf":
                score *= 1.45
            if rec["citation_key"] in PRIMARY_SYSTEM_KEYS:
                score += 5.0
            if rec["source_role"] == "second_neighbor_reference":
                score *= 0.55
        elif sentence_type in {"method_formalism", "electrochemical_formalism"}:
            if rec["source_role"] == "second_neighbor_reference":
                score *= 1.25
            if rec["source_role"] == "primary_project_pdf":
                score *= 0.85
        else:
            if rec["source_role"] == "primary_project_pdf":
                score *= 0.9

        if score > 0:
            snippet = rec.get("title") or rec.get("raw_reference") or rec.get("evidence_text") or ""
            if rec.get("citation_contexts"):
                snippet = rec["citation_contexts"][0].get("sentence", snippet)
            ranked.append({
                "source_id": rec.get("source_id"),
                "citation_key": rec["citation_key"],
                "source_role": rec.get("source_role"),
                "score": round(score, 3),
                "title": rec.get("title"),
                "authors": rec.get("authors", []),
                "year": rec.get("year"),
                "doi": rec.get("doi"),
                "raw_reference": rec.get("raw_reference"),
                "source_reference_numbers": rec.get("source_reference_numbers", []),
                "evidence_snippet": str(snippet)[:700],
            })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:max_candidates]


def deterministic_select(sentence: str, sentence_type: str, candidates: list[dict[str, Any]]) -> tuple[list[str], str, str, bool]:
    if should_skip_sentence(sentence, sentence_type) or not candidates:
        return [], "none", "No citation selected by conservative policy.", False
    high = [c for c in candidates if c["score"] >= 12.0]
    if sentence_type == "strategy_rationale":
        primary = [c for c in candidates if c["source_role"] == "primary_project_pdf" and c["score"] >= 8.0]
        selected = primary[:5] if primary else high[:2]
    elif sentence_type == "literature_background":
        primary = [c for c in high if c["source_role"] == "primary_project_pdf"]
        selected = primary[:2] if primary else high[:1]
    elif sentence_type in {"method_formalism", "electrochemical_formalism"}:
        second = [c for c in high if c["source_role"] == "second_neighbor_reference"]
        selected = second[:2] if second else high[:1]
    else:
        selected = high[:1]
    if selected:
        keys = [c["citation_key"] for c in selected]
        confidence = "high" if selected[0]["score"] >= 16 else "medium"
        return keys, confidence, "Deterministic retrieval selected the highest-scoring policy-compatible candidate(s).", confidence != "high"
    return [], "low", "No candidate exceeded the conservative retrieval threshold.", True


def make_sentence_packets(section_json: dict[str, Any], index: list[dict[str, Any]], max_candidates: int) -> list[dict[str, Any]]:
    packets = []
    n = 1
    for section in section_json.get("sections", []):
        section_id = section.get("section_id", "")
        for block_index, block in enumerate(section.get("content_blocks", [])):
            if block.get("type") != "paragraph":
                continue
            for sentence_index, sentence in enumerate(split_sentences(block.get("text", ""))):
                sentence_type = classify_sentence(sentence, section_id)
                candidates = rank_candidates(sentence, sentence_type, index, max_candidates)
                sentence_id = f"S{n:03d}"
                n += 1
                packets.append({
                    "sentence_id": sentence_id,
                    "section_id": section_id,
                    "block_index": block_index,
                    "sentence_index": sentence_index,
                    "sentence": sentence,
                    "sentence_type": sentence_type,
                    "candidate_citations": candidates,
                })
    return packets


def build_llm_packets(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    llm_packets = []
    for packet in packets:
        candidates = []
        for candidate in packet["candidate_citations"]:
            candidates.append({
                "source_id": candidate.get("source_id"),
                "citation_key": candidate["citation_key"],
                "source_role": candidate["source_role"],
                "title": candidate.get("title"),
                "authors": candidate.get("authors", [])[:8],
                "year": candidate.get("year"),
                "raw_reference": candidate.get("raw_reference"),
                "evidence_snippet": candidate.get("evidence_snippet"),
                "retrieval_score": candidate.get("score"),
            })
        llm_packets.append({
            "sentence_id": packet["sentence_id"],
            "sentence": packet["sentence"],
            "sentence_type": packet["sentence_type"],
            "candidates": candidates,
        })
    return llm_packets


def build_payload(model: str, packets: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = SELECTOR_PROMPT + "\n\nSentence packets:\n" + json.dumps({"packets": build_llm_packets(packets)}, indent=2, ensure_ascii=False)
    return {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
    }


def normalize_llm_decisions(packets: list[dict[str, Any]], raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packet_by_id = {p["sentence_id"]: p for p in packets}
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw.get("decisions"), list):
        raise ValueError("LLM output must contain a decisions list.")
    for item in raw["decisions"]:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("sentence_id") or "")
        if sid not in packet_by_id:
            continue
        allowed = {c["citation_key"] for c in packet_by_id[sid]["candidate_citations"]}
        keys = [str(k) for k in item.get("citation_keys", []) if str(k) in allowed]
        confidence = str(item.get("confidence") or "low").lower()
        if confidence not in {"high", "medium", "low", "none"}:
            confidence = "low"
        out[sid] = {
            "selected_citation_keys": keys,
            "confidence": confidence if keys else "none",
            "needs_human_check": bool(item.get("needs_human_check", False)) or confidence == "low",
            "reason": str(item.get("reason") or "LLM citation decision."),
            "decision_source": "llm",
        }
    return out


def selected_source_ids(keys: list[str], packet: dict[str, Any]) -> list[str]:
    by_key = {c["citation_key"]: c for c in packet.get("candidate_citations", [])}
    ids = []
    for key in keys:
        source_id = by_key.get(key, {}).get("source_id")
        if source_id:
            ids.append(str(source_id))
    return ids


def merge_decisions(packets: list[dict[str, Any]], llm_by_id: dict[str, dict[str, Any]] | None) -> list[dict[str, Any]]:
    decisions = []
    for packet in packets:
        if llm_by_id and packet["sentence_id"] in llm_by_id:
            choice = llm_by_id[packet["sentence_id"]]
        else:
            keys, confidence, reason, human = deterministic_select(
                packet["sentence"], packet["sentence_type"], packet["candidate_citations"]
            )
            choice = {
                "selected_citation_keys": keys,
                "confidence": confidence,
                "needs_human_check": human,
                "reason": reason,
                "decision_source": "deterministic",
            }
        decision = {
            **packet,
            **choice,
        }
        decision["selected_citation_source_ids"] = selected_source_ids(
            decision.get("selected_citation_keys", []),
            packet,
        )
        decisions.append(decision)
    return decisions


def compact_source_record(rec: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": rec.get("source_id"),
        "citation_key": rec.get("citation_key"),
        "source_role": rec.get("source_role"),
        "title": rec.get("title"),
        "authors": rec.get("authors", []),
        "year": rec.get("year"),
        "doi": rec.get("doi"),
        "raw_reference": rec.get("raw_reference"),
        "collection": rec.get("collection"),
        "source_reference_numbers": rec.get("source_reference_numbers", []),
    }


def source_lookup_from_index(index: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {rec["citation_key"]: compact_source_record(rec) for rec in index}


def citation_source_ids(citation_keys: list[str], source_lookup: dict[str, dict[str, Any]]) -> list[str]:
    ids = []
    for key in citation_keys:
        source_id = source_lookup.get(key, {}).get("source_id")
        if source_id:
            ids.append(str(source_id))
    return ids


def citation_sources_used(decisions: list[dict[str, Any]], source_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    used: list[dict[str, Any]] = []
    seen: set[str] = set()
    for decision in decisions:
        for key in decision.get("selected_citation_keys", []):
            if key in seen:
                continue
            source = source_lookup.get(key)
            if source:
                used.append(source)
                seen.add(key)
    return used


def apply_annotations(
    section_json: dict[str, Any],
    decisions: list[dict[str, Any]],
    source_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cited = copy.deepcopy(section_json)
    decisions_by_location: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for decision in decisions:
        key = (decision["section_id"], int(decision["block_index"]))
        decisions_by_location.setdefault(key, []).append(decision)

    for section in cited.get("sections", []):
        section_id = section.get("section_id", "")
        for block_index, block in enumerate(section.get("content_blocks", [])):
            if block.get("type") != "paragraph":
                continue
            location_decisions = decisions_by_location.get((section_id, block_index), [])
            by_sentence = {int(d["sentence_index"]): d for d in location_decisions}
            sentences = split_sentences(block.get("text", ""))
            rendered = []
            annotations = []
            for i, sentence in enumerate(sentences):
                decision = by_sentence.get(i)
                cite_keys = decision.get("selected_citation_keys", []) if decision else []
                if cite_keys:
                    rendered.append(sentence + " " + "{{cite:" + ";".join(cite_keys) + "}}")
                else:
                    rendered.append(sentence)
                if decision:
                    cite_source_ids = citation_source_ids(cite_keys, source_lookup)
                    annotations.append({
                        "sentence_id": decision["sentence_id"],
                        "sentence": decision["sentence"],
                        "citation_keys": cite_keys,
                        "citation_source_ids": cite_source_ids,
                        "sentence_type": decision["sentence_type"],
                        "confidence": decision["confidence"],
                        "reason": decision["reason"],
                        "needs_human_check": decision["needs_human_check"],
                        "decision_source": decision["decision_source"],
                    })
            block["text_with_citation_placeholders"] = " ".join(rendered)
            block["citation_annotations"] = annotations
    cited["citation_schema_version"] = SCHEMA_VERSION
    cited["citation_sources_used"] = citation_sources_used(decisions, source_lookup)
    return cited


def default_outdir(section_json: Path) -> Path:
    if section_json.name == "methods_section_text.json" and section_json.parent.name == "text":
        return section_json.parent.parent / "citations"
    return section_json.parent / "citations"


def write_summary(path: Path, decisions: list[dict[str, Any]], cited_path: Path, sources_path: Path) -> None:
    selected = [d for d in decisions if d.get("selected_citation_keys")]
    needs = [d for d in decisions if d.get("needs_human_check")]
    lines = [
        "# Citation Selection Summary",
        "",
        f"- Cited section JSON: `{cited_path}`",
        f"- Citation sources: `{sources_path}`",
        f"- Sentences evaluated: {len(decisions)}",
        f"- Sentences with citations: {len(selected)}",
        f"- Sentences needing human check: {len(needs)}",
        "",
        "## Selected Citations",
        "",
    ]
    for decision in selected:
        keys = ", ".join(decision["selected_citation_keys"])
        lines.append(f"- `{decision['sentence_id']}` [{decision['sentence_type']}] -> {keys}")
        lines.append(f"  - {decision['sentence']}")
    lines.extend(["", "## Needs Human Check", ""])
    if needs:
        for decision in needs:
            keys = ", ".join(decision.get("selected_citation_keys", [])) or "none"
            lines.append(f"- `{decision['sentence_id']}` -> {keys}: {decision['reason']}")
    else:
        lines.append("- None")
    write_text(path, "\n".join(lines) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section-json", required=True, type=Path, help="Manuscript section JSON to annotate.")
    parser.add_argument("--citation-sources", required=True, type=Path, help="citation_sources.json from citation-source-extractor.")
    parser.add_argument("--outdir", type=Path, help="Output directory. Defaults near the section JSON.")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--no-llm", action="store_true", help="Use deterministic retrieval-only decisions.")
    parser.add_argument("--save-prompt", type=Path, help="Optional path for LLM prompt payload JSON.")
    parser.add_argument("--save-response", type=Path, help="Optional path for raw LLM response JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    load_default_env()
    section_json = read_json(args.section_json)
    sources = read_json(args.citation_sources)
    outdir = args.outdir or default_outdir(args.section_json)
    outdir.mkdir(parents=True, exist_ok=True)

    index = build_index(sources)
    source_lookup = source_lookup_from_index(index)
    packets = make_sentence_packets(section_json, index, args.max_candidates)
    llm_by_id: dict[str, dict[str, Any]] | None = None
    prompt_path = args.save_prompt or outdir / "llm_prompt.json"
    response_path = args.save_response or outdir / "llm_response.json"

    if not args.no_llm:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            payload = build_payload(args.model, packets)
            write_json(prompt_path, payload)
            response = call_openai(payload, api_key)
            write_json(response_path, response)
            raw_decisions = parse_json_text(output_text(response))
            llm_by_id = normalize_llm_decisions(packets, raw_decisions)
        else:
            print("OPENAI_API_KEY not found; falling back to deterministic citation selection.", file=sys.stderr)

    decisions = merge_decisions(packets, llm_by_id)
    cited = apply_annotations(section_json, decisions, source_lookup)

    cited_path = outdir / "cited_section_text.json"
    decisions_path = outdir / "citation_decisions.json"
    summary_path = outdir / "citation_selection_summary.md"
    write_json(cited_path, cited)
    write_json(decisions_path, {
        "schema_version": SCHEMA_VERSION,
        "section_json": str(args.section_json),
        "citation_sources": str(args.citation_sources),
        "decision_mode": "llm" if llm_by_id else "deterministic",
        "sentence_count": len(decisions),
        "cited_sentence_count": sum(1 for d in decisions if d.get("selected_citation_keys")),
        "needs_human_check_count": sum(1 for d in decisions if d.get("needs_human_check")),
        "decisions": decisions,
    })
    write_summary(summary_path, decisions, cited_path, args.citation_sources)

    print(json.dumps({
        "ok": True,
        "decision_mode": "llm" if llm_by_id else "deterministic",
        "sentences": len(decisions),
        "cited_sentences": sum(1 for d in decisions if d.get("selected_citation_keys")),
        "needs_human_check": sum(1 for d in decisions if d.get("needs_human_check")),
        "outdir": str(outdir),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
