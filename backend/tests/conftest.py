import pytest

from core.artifacts import ArtifactOutput
from core.models import AIConnection, Environment, EnvironmentRepository


@pytest.fixture
def storage(settings, tmp_path):
    settings.DATA_DIR = tmp_path
    settings.MEDIA_ROOT = tmp_path / "requests"
    return tmp_path


@pytest.fixture
def environment(db):
    AIConnection.objects.update_or_create(
        pk=1, defaults={"agent": "codex", "status": "CONNECTED", "availability": "AVAILABLE"}
    )
    value = Environment.objects.create(name="Staging", status="READY")
    EnvironmentRepository.objects.create(
        environment=value, repository="company/backend", branch="main", sha="a" * 40
    )
    return value


@pytest.fixture
def ticket():
    return {
        "title": "Export contracts",
        "context": "Operations team",
        "business_need": "Export CSV",
        "current_behavior": "Export absent",
        "expected_behavior": "Export available",
        "decisions": ["All active contracts"],
        "acceptance_criteria": ["A CSV can be downloaded"],
        "proposed_solution": "Reuse the export service",
        "technical_analysis": "See contracts/export.py",
        "components": ["contracts/export.py"],
        "database_impact": "No changes",
        "risks": ["Data volume"],
        "tests": ["Verify active contract filtering"],
    }


@pytest.fixture
def bundle():
    return ArtifactOutput.model_validate(
        {
            "status": "READY",
            "technical_summary": "Reuse the existing export mechanism.",
            "ticket": {
                "title": "Export active contracts",
                "context": "The team is preparing an audit. It needs to share active contracts.",
                "need": "Share active contracts.",
                "expected_behavior": ["Download active contracts only."],
                "proposed_solution": "Reuse the export service and add an active filter.",
                "technical_impact": ["contracts/export.py: selection filter"],
                "risks": ["Verify read permissions."],
                "acceptance_criteria": ["Terminated contracts are excluded."],
            },
            "goal": {
                "business_intent": "Share active contracts.",
                "current_behavior": "The service exports all contracts.",
                "required_behavior": ["Limit the export to active contracts."],
                "technical_context": ["Existing export service"],
                "relevant_files": ["contracts/export.py: selection"],
                "constraints": ["Do not modify the database."],
                "implementation_guidance": ["Add the filter to the existing service."],
                "acceptance_criteria": ["Terminated contracts are excluded."],
                "tests_expected": ["Verify that terminated contracts are excluded."],
                "useful_attachments": [],
            },
        }
    )


@pytest.fixture
def code_report():
    return {
        "current_behavior": "All contracts are exported.",
        "proposed_solution": "Filter active records.",
        "evidence": ["contracts/export.py: selection"],
        "impacts": ["Export"],
        "database_impact": "No migration",
        "risks": [],
        "tests_expected": ["Exclude a terminated contract."],
        "uncertainties": [],
    }
