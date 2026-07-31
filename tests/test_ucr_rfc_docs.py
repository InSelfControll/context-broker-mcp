"""Validation tests for the Universal Context Router RFC series."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RFC_DIR = ROOT / "docs" / "rfc"

EXPECTED_RFCS = {
    "RFC-000-vision.md": "# RFC-000: Vision",
    "RFC-001-architecture.md": "# RFC-001: Universal Context Router Architecture",
    "RFC-002-universal-tool-registry.md": "# RFC-002: Universal Tool Registry",
    "RFC-003-semantic-routing-engine.md": "# RFC-003: Semantic Routing Engine",
    "RFC-004-skill-aware-decomposition.md": "# RFC-004: Skill-Aware Decomposition",
    "RFC-005-planning-engine.md": "# RFC-005: Planning Engine",
    "RFC-006-context-compression.md": "# RFC-006: Context Compression",
    "RFC-007-dynamic-tool-exposure.md": "# RFC-007: Dynamic Tool Exposure",
    "RFC-008-execution-engine.md": "# RFC-008: Execution Engine",
    "RFC-009-universal-adapter-framework.md": "# RFC-009: Universal Adapter Framework",
    "RFC-010-security-architecture.md": "# RFC-010: Security Architecture",
    "RFC-011-plugin-sdk.md": "# RFC-011: Plugin SDK",
    "RFC-012-storage.md": "# RFC-012: Storage",
    "RFC-013-observability.md": "# RFC-013: Observability",
    "RFC-014-benchmarks.md": "# RFC-014: Benchmarks",
    "RFC-015-public-apis.md": "# RFC-015: Public APIs",
    "RFC-016-testing-strategy.md": "# RFC-016: Testing Strategy",
    "RFC-017-deployment.md": "# RFC-017: Deployment",
    "RFC-018-roadmap.md": "# RFC-018: Roadmap",
}

REQUIRED_SECTIONS = [
    "## Summary",
    "## Goals",
    "## Non-Goals",
    "## Terminology",
    "## Motivation",
    "## Design",
    "## Interfaces",
    "## Extension Points",
    "## Security Considerations",
    "## Observability Considerations",
    "## Compatibility",
    "## Trade-offs",
    "## Open Questions",
    "## Related RFCs",
]

FORBIDDEN_PHRASES = [
    "private repository",
    "internal repository",
    "proprietary repository",
    "private API",
    "internal API",
    "customer data",
    "company confidential",
]

INTERFACE_RFCS = [
    "RFC-002-universal-tool-registry.md",
    "RFC-005-planning-engine.md",
    "RFC-007-dynamic-tool-exposure.md",
    "RFC-008-execution-engine.md",
    "RFC-009-universal-adapter-framework.md",
    "RFC-010-security-architecture.md",
    "RFC-011-plugin-sdk.md",
    "RFC-015-public-apis.md",
]


def test_rfc_index_and_template_exist() -> None:
    assert (RFC_DIR / "README.md").exists()
    assert (RFC_DIR / "templates" / "rfc-template.md").exists()


def test_all_expected_rfc_files_exist_with_titles() -> None:
    for filename, title in EXPECTED_RFCS.items():
        path = RFC_DIR / filename
        assert path.exists(), filename
        assert path.read_text().startswith(title), filename


def test_every_rfc_has_required_sections() -> None:
    for filename in EXPECTED_RFCS:
        text = (RFC_DIR / filename).read_text()
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{filename} missing {section}"


def test_rfc_docs_do_not_use_private_or_proprietary_examples() -> None:
    for path in RFC_DIR.glob("RFC-*.md"):
        text = path.read_text().lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in text, f"{path.name} contains forbidden phrase: {phrase}"


def test_public_interface_rfcs_define_versioned_interfaces() -> None:
    for filename in INTERFACE_RFCS:
        text = (RFC_DIR / filename).read_text()
        assert ".v1" in text or "Version:" in text, filename


def test_rfc_index_links_every_rfc() -> None:
    text = (RFC_DIR / "README.md").read_text()
    for filename in EXPECTED_RFCS:
        assert filename in text


def test_rfc_required_topic_specific_content_is_present() -> None:
    required_phrases = {
        "RFC-001-architecture.md": [
            "registry load",
            "index warmup",
            "request routing",
            "result capture",
        ],
        "RFC-002-universal-tool-registry.md": ["risk taxonomy", "critical"],
        "RFC-012-storage.md": ["backup", "restore"],
        "RFC-016-testing-strategy.md": [
            "golden fixtures",
            "public-only test data policy",
            "ci requirements",
        ],
        "RFC-017-deployment.md": ["health checks", "upgrade", "migration"],
        "RFC-018-roadmap.md": ["avoid promising proprietary integrations"],
    }
    for filename, phrases in required_phrases.items():
        text = (RFC_DIR / filename).read_text().lower()
        for phrase in phrases:
            assert phrase in text, f"{filename} missing {phrase}"


def test_rfc_open_questions_are_topic_specific() -> None:
    question_blocks = {}
    for filename in EXPECTED_RFCS:
        text = (RFC_DIR / filename).read_text()
        block = text.split("## Open Questions", 1)[1].split("## Related RFCs", 1)[0].strip()
        question_blocks[filename] = block

    repeated_blocks = {
        block for block in question_blocks.values() if list(question_blocks.values()).count(block) > 1
    }
    assert not repeated_blocks
