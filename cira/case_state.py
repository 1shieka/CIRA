"""Accumulated case state for a single CIRA investigation session.

Rather than asking the model to re-derive the entire case from the raw
conversation at the moment of PDF generation (risking dropped or
re-invented details), we accumulate structured facts turn over turn as the
investigation proceeds. The verifier's evidence-completeness output is the
primary source for evidence checkbox state; explicit user-confirmed facts
(e.g. "the UTR is 1234") are layered on top and treated as higher trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evidence_registry import CATEGORIES, resolve_category_id, resolve_item_id


@dataclass
class CaseState:
    phase: str = "TRIAGE"  # TRIAGE -> INTERVIEWING -> REPORT_READY -> FIR_GENERATED
    financial_loss: bool | None = None
    urgent_notice_shown: bool = False

    matched_category_id: str | None = None
    match_confidence: float = 0.0

    # item_id -> True/False (collected or not)
    evidence_status: dict[str, bool] = field(default_factory=dict)
    # item_id -> free-text value the user actually gave (e.g. the UTR number itself)
    evidence_values: dict[str, str] = field(default_factory=dict)

    timeline: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    description: str = ""

    # qid -> answer, qid -> question text (free-form Q&A not covered by the matrix)
    followup_answers: dict[str, str] = field(default_factory=dict)
    questions_labels: dict[str, str] = field(default_factory=dict)

    def apply_verifier_output(self, verifier_output: dict[str, Any]) -> None:
        """Fold verifier results into accumulated state. Verified items only move
        from False -> True; we never un-collect something the user already gave,
        even if a later verifier pass mis-parses a turn."""
        matched = verifier_output.get("matched_categories") or []
        if matched:
            resolved = resolve_category_id(matched[0])
            if resolved:
                self.matched_category_id = resolved

        completeness = verifier_output.get("evidence_completeness") or {}
        if self.matched_category_id and completeness:
            for cat_name, score in completeness.items():
                if resolve_category_id(cat_name) == self.matched_category_id:
                    try:
                        self.match_confidence = float(score) / 100.0
                    except (TypeError, ValueError):
                        pass

        if not self.matched_category_id:
            return

        for label in verifier_output.get("collected_required_evidence", []) or []:
            item_id = resolve_item_id(self.matched_category_id, label)
            if item_id:
                self.evidence_status[item_id] = True

        # Do NOT force missing items to False here if we previously recorded
        # them True from explicit user input — only initialize unseen items.
        category = CATEGORIES.get(self.matched_category_id)
        if category:
            for item in category.required:
                self.evidence_status.setdefault(item.item_id, False)

    def record_user_fact(self, item_id: str, value: str) -> None:
        """Mark an evidence item collected from an explicit user-provided value."""
        self.evidence_values[item_id] = value
        self.evidence_status[item_id] = True

    def add_timeline_event(self, time: str, event: str) -> None:
        self.timeline.append({"time": time, "event": event})

    def is_report_ready(self, verifier_status: str) -> bool:
        return verifier_status == "verified"

    def to_pdf_case_data(self) -> dict[str, Any]:
        """Shape this state into the dict expected by generate_pdf_report()."""
        category = CATEGORIES.get(self.matched_category_id) if self.matched_category_id else None
        display_name = category.display_name if category else "Uncategorized / Other Cybercrime"

        evidence_labels: dict[str, str] = {}
        evidence_bool: dict[str, bool] = {}
        if category:
            for item in category.required:
                evidence_labels[item.item_id] = item.label
                evidence_bool[item.item_id] = self.evidence_status.get(item.item_id, False)

        return {
            "description": self.description,
            "classification": {
                "subcategory_name": display_name,
                "category_name": "Cybercrime",
                "match_confidence": self.match_confidence,
            },
            "summary": self.summary,
            "timeline": self.timeline,
            "evidence": evidence_bool,
            "evidence_labels": evidence_labels,
            "followup_answers": self.followup_answers,
            "questions_labels": self.questions_labels,
        }

    def missing_required_labels(self) -> list[str]:
        category = CATEGORIES.get(self.matched_category_id) if self.matched_category_id else None
        if not category:
            return []
        return [
            item.label
            for item in category.required
            if not self.evidence_status.get(item.item_id, False)
        ]
