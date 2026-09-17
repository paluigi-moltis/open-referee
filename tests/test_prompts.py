"""Tests for the referee prompt system: lens selection, citation extraction,
prompt content guarantees."""

from __future__ import annotations

from open_referee.ingestion.readers import document_from_markdown
from open_referee.pipeline import prompts
from open_referee.pipeline.orchestrator import ReviewPipeline, _extract_intext_citations

# ------------------------------------------------------------ lens selection --


def _pipeline():
    return ReviewPipeline.__new__(ReviewPipeline)  # no cfg needed for _lenses_for


def test_lenses_theory_paper():
    lenses = _pipeline()._lenses_for(
        {
            "mathematical_density": "heavy",
            "statistical_content": "none",
            "methodological_style": "theory",
        }
    )
    names = [n for n, _ in lenses]
    assert "math" in names
    assert "empirical" not in names
    assert "prose" in names and "lit" in names


def test_lenses_empirical_paper():
    lenses = _pipeline()._lenses_for(
        {
            "mathematical_density": "light",
            "statistical_content": "causal_inference",
            "methodological_style": "empirical",
        }
    )
    names = [n for n, _ in lenses]
    assert "math" in names  # light density still includes math
    assert "empirical" in names
    assert "prose" in names and "lit" in names


def test_lenses_pure_prose_paper():
    lenses = _pipeline()._lenses_for(
        {
            "mathematical_density": "none",
            "statistical_content": "none",
            "methodological_style": "other",
        }
    )
    names = [n for n, _ in lenses]
    assert names == ["prose", "lit"]


def test_lenses_missing_triage_fields_safe():
    lenses = _pipeline()._lenses_for({})
    names = [n for n, _ in lenses]
    assert "prose" in names and "lit" in names


def test_all_lens_prompts_carry_persona_and_schema():
    for name, system in [
        ("math", prompts.MATH_VERIFIER_SYSTEM),
        ("empirical", prompts.EMPIRICAL_VERIFIER_SYSTEM),
        ("prose", prompts.PROSE_VERIFIER_SYSTEM),
        ("lit", prompts.LIT_VERIFIER_SYSTEM),
    ]:
        assert "top academic journal" in system, name
        assert "STRICT JSON" in system, name
        assert "paragraph_anchor" in system, name
        assert "severity" in system.lower(), name


# -------------------------------------------------------- citation extraction --

DOC = """# Paper

Smith (2001) proved that classical widgets converge. This extends the
framework of (Doe and Roe, 1999; Alpha, 2005) to noisy settings.

Numerical evidence supports the claim [1], and robustness checks appear in
[2, 3]. The estimator follows Jones2020 closely.
"""


def test_intext_extraction_author_year():
    doc = document_from_markdown(DOC, source_format="md")
    out = _extract_intext_citations(doc)
    assert "Smith (2001)" in out
    assert "(Doe and Roe, 1999; Alpha, 2005)" in out
    # claim context is attached
    assert "classical widgets converge" in out


def test_intext_extraction_numeric_and_natbib():
    doc = document_from_markdown(DOC, source_format="md")
    out = _extract_intext_citations(doc)
    assert "[1]" in out
    assert "[2, 3]" in out
    assert "Jones2020" in out


def test_intext_extraction_no_citations():
    doc = document_from_markdown("# T\n\nNo citations at all here.", source_format="md")
    out = _extract_intext_citations(doc)
    assert "no in-text citations" in out


def test_intext_extraction_caps_at_limit():
    text = "# T\n\n" + "\n\n".join(f"Claim number {i} (Author{i}, 2001) holds." for i in range(200))
    doc = document_from_markdown(text, source_format="md")
    out = _extract_intext_citations(doc)
    n = out.count("::")
    assert n <= 60


# --------------------------------------------------------------- prompt design --


def test_persona_present_in_all_stage_prompts():
    for p in [
        prompts.TRIAGE_SYSTEM,
        prompts.CHALLENGER_SYSTEM,
        prompts.BIBLIOGRAPHY_SYSTEM,
        prompts.META_SYSTEM,
        prompts.VALIDATOR_SYSTEM,
        prompts.FIGURE_SYSTEM,
    ]:
        assert "referee for a top academic journal" in p or "top academic journal" in p


def test_severity_rubric_in_comment_producers():
    for p in [
        prompts.MATH_VERIFIER_SYSTEM,
        prompts.EMPIRICAL_VERIFIER_SYSTEM,
        prompts.PROSE_VERIFIER_SYSTEM,
        prompts.LIT_VERIFIER_SYSTEM,
        prompts.FIGURE_SYSTEM,
        prompts.CHALLENGER_SYSTEM,
    ]:
        assert "0.80-1.00" in p


def test_bibliography_prompt_covers_existence_and_quotation():
    p = prompts.BIBLIOGRAPHY_SYSTEM
    assert "EXISTENCE" in p
    assert "QUOTATION CONSISTENCY" in p
    assert "in_text_issues" in p


def test_math_lens_covers_statements_proofs_and_cases():
    p = prompts.MATH_VERIFIER_SYSTEM
    for needle in [
        "statement",
        "proof",
        "without loss of generality",
        "boundary",
        "notation",
        "circular",
    ]:
        assert needle.lower() in p.lower(), needle


def test_empirical_lens_covers_econometric_practice():
    p = prompts.EMPIRICAL_VERIFIER_SYSTEM
    for needle in [
        "identification",
        "parallel trends",
        "instrument",
        "clustering",
        "multiple hypothesis",
        "robustness",
        "external validity",
    ]:
        assert needle.lower() in p.lower(), needle


def test_meta_prompt_requires_recommendation_and_strengths():
    p = prompts.META_SYSTEM
    assert "strengths" in p.lower()
    assert "recommendation" in p.lower()
    assert "major revision" in p


def test_validator_prompt_drops_unsubstantiated():
    p = prompts.VALIDATOR_SYSTEM
    assert "DROP" in p
    assert "fabricated" in p
