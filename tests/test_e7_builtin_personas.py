from __future__ import annotations

from coworker.personas.registry import PersonaRegistry


def test_e7_media_and_company_personas_are_builtin_and_safe() -> None:
    registry = PersonaRegistry()

    media = registry.get("media")
    company = registry.get("company")
    assert media is not None
    assert company is not None
    assert media.builtin is True
    assert company.builtin is True
    assert media.family == "knowledge"
    assert company.family == "knowledge"
    assert media.workspace == "deliverable"
    assert company.workspace == "deliverable"
    assert "engineering_os" in media.tools
    assert "engineering_os" in company.tools

    media_manifest = media.manifest
    company_manifest = company.manifest
    assert media_manifest is not None
    assert company_manifest is not None
    assert media_manifest.messaging is True
    assert media_manifest.connectors is True
    assert company_manifest.messaging is True
    assert company_manifest.connectors is True

    media_prompt = media_manifest.system_prompt
    company_prompt = company_manifest.system_prompt
    assert "go-tool-runtime" in media_prompt
    assert "AI-Engineering-OS" in media_prompt
    assert "approval" in media_prompt.lower()
    assert "Artifact Publisher" in media_prompt
    assert "go-tool-runtime" in company_prompt
    assert "AI-Engineering-OS" in company_prompt
    assert "Drafting is not sending" in company_prompt
    assert "approval" in company_prompt.lower()


def test_e7_personas_reuse_existing_authorities_instead_of_new_runtimes() -> None:
    registry = PersonaRegistry()
    for persona_id in ("media", "company"):
        entry = registry.get(persona_id)
        assert entry is not None and entry.manifest is not None
        prompt = entry.manifest.system_prompt.lower()
        assert "second" in prompt or "second" in entry.manifest.description.lower() or "existing" in prompt
        assert "tool registry" in prompt
        assert "arbitrary" in prompt
