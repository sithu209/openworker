"""Evidence-review routing policy for OpenWorker.

Google Drive is a review transport, not a generic job-data transport.  It is selected
only when ChatGPT must inspect perceptual output (image/video/audio/layout).  Pure
text, structured data, hashes, databases, ledgers, and deterministic receipts stay on
the machine-verifiable path unless a caller explicitly requests textual LLM review.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReviewPolicyError(ValueError):
    """Raised when a work item does not declare enough evidence to choose a route."""


class ReviewRoute(str, Enum):
    MACHINE_VERIFIABLE = "machine-verifiable"
    CHATGPT_TEXT_DIRECT = "chatgpt-text-direct"
    CHATGPT_MULTIMODAL_DRIVE = "chatgpt-multimodal-drive"


@dataclass(frozen=True)
class ReviewRequirement:
    """Explicit quality requirements for one acceptance boundary.

    Routing is driven by *how quality must be judged*, never by file extension alone.
    A PDF, for example, can be machine-verifiable when only its hash/structure matters,
    or multimodal when page layout must be visually inspected.
    """

    machine_verifiable: bool = False
    textual_llm_judgment: bool = False
    visual_judgment: bool = False
    audio_judgment: bool = False
    layout_judgment: bool = False

    @property
    def multimodal_required(self) -> bool:
        return self.visual_judgment or self.audio_judgment or self.layout_judgment


def choose_review_route(requirement: ReviewRequirement) -> ReviewRoute:
    """Choose the narrowest review route that can satisfy the declared quality gate.

    Precedence is intentional:
    1. Perceptual judgement requires a multimodal review bundle and Drive publication.
    2. Text-only LLM judgement does not require Drive.
    3. Deterministic/hash/database/receipt acceptance stays local and machine-verifiable.
    4. An undeclared gate fails closed instead of guessing that Drive is required.
    """

    if requirement.multimodal_required:
        return ReviewRoute.CHATGPT_MULTIMODAL_DRIVE
    if requirement.textual_llm_judgment:
        return ReviewRoute.CHATGPT_TEXT_DIRECT
    if requirement.machine_verifiable:
        return ReviewRoute.MACHINE_VERIFIABLE
    raise ReviewPolicyError(
        "review requirement is undeclared: specify machine_verifiable, "
        "textual_llm_judgment, or a perceptual judgement flag"
    )


def google_drive_review_required(requirement: ReviewRequirement) -> bool:
    """Return True only for review gates that genuinely require multimodal inspection."""

    return choose_review_route(requirement) is ReviewRoute.CHATGPT_MULTIMODAL_DRIVE


__all__ = [
    "ReviewPolicyError",
    "ReviewRequirement",
    "ReviewRoute",
    "choose_review_route",
    "google_drive_review_required",
]
