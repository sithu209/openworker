from __future__ import annotations

import pytest

from coworker.review_policy import (
    ReviewPolicyError,
    ReviewRequirement,
    ReviewRoute,
    choose_review_route,
    google_drive_review_required,
)


def test_machine_verifiable_acceptance_never_requires_google_drive():
    req = ReviewRequirement(machine_verifiable=True)
    assert choose_review_route(req) is ReviewRoute.MACHINE_VERIFIABLE
    assert google_drive_review_required(req) is False


def test_text_only_llm_review_does_not_require_google_drive():
    req = ReviewRequirement(textual_llm_judgment=True)
    assert choose_review_route(req) is ReviewRoute.CHATGPT_TEXT_DIRECT
    assert google_drive_review_required(req) is False


@pytest.mark.parametrize(
    "req",
    [
        ReviewRequirement(visual_judgment=True),
        ReviewRequirement(audio_judgment=True),
        ReviewRequirement(layout_judgment=True),
        ReviewRequirement(machine_verifiable=True, visual_judgment=True),
    ],
)
def test_perceptual_quality_gate_requires_multimodal_drive_review(req):
    assert choose_review_route(req) is ReviewRoute.CHATGPT_MULTIMODAL_DRIVE
    assert google_drive_review_required(req) is True


def test_file_type_is_not_used_to_guess_review_route():
    # A caller cannot make Drive authoritative merely because an artifact happens to
    # be a PDF/image/video.  The acceptance requirement must state the judgement type.
    with pytest.raises(ReviewPolicyError, match="review requirement is undeclared"):
        choose_review_route(ReviewRequirement())
