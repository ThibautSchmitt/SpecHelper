"""Exercise complete history reads and bounded progress reads without native inference."""

import json
import os
import statistics
import time
from pathlib import Path

import pytest
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.api import request_dict
from core.models import AnalysisRun, Request, RequestMessage, ResultVersion


@pytest.mark.django_db
def test_long_conversation_read_preserves_history_and_keeps_progress_small(client, environment, tmp_path):
    value = Request.objects.create(
        environment=environment, need="Explain the current implementation", status="READY",
        discussion_state={"enabled": True, "mode": "discussion", "revision": 1000},
    )
    RequestMessage.objects.bulk_create([
        RequestMessage(request=value, role="user" if index % 2 == 0 else "assistant",
                       kind="discussion_message" if index % 2 == 0 else "discussion_reply",
                       content=f"History message {index}: " + "context " * 128)
        for index in range(1000)
    ])
    for number in range(1, 21):
        run = AnalysisRun.objects.create(
            request=value, number=number, status="DONE",
            orchestration={"business_summary": {"summary": "source " * 10000}},
            context_snapshot={"dossier": {"need": f"Need {number}"}},
        )
        ResultVersion.objects.create(request=value, run=run, number=number, status="READY",
                                     context_snapshot=run.context_snapshot)

    reads = []
    for _ in range(5):
        fresh = Request.objects.select_related("environment", "source_question_version").get(pk=value.pk)
        start = time.perf_counter()
        with CaptureQueriesContext(connection) as queries:
            payload = request_dict(fresh, full=True)
            encoded = json.dumps(payload, cls=DjangoJSONEncoder).encode()
        reads.append({"seconds": time.perf_counter() - start, "queries": len(queries),
                      "bytes": len(encoded),
                      "latest_run_queries": sum('FROM "core_analysisrun"' in q["sql"] and 'LIMIT 1' in q["sql"] for q in queries),
                      "latest_version_queries": sum('FROM "core_resultversion"' in q["sql"] and 'LIMIT 1' in q["sql"] for q in queries)})
        assert len(payload["messages"]) == 1000
        assert len(payload["analysis_runs"]) == 20
        assert len(payload["versions"]) == 20
        assert payload["latest_version"]["number"] == 20
        assert payload["business_summary"]["summary"] == "source " * 10000
        assert reads[-1]["latest_run_queries"] == 1
        assert reads[-1]["latest_version_queries"] == 1

    endpoint = f"/api/analyses/{value.pk}/progress"
    progress = client.get(endpoint)
    assert progress.status_code == 200
    cursor = progress.json()["progress_cursor"]
    unchanged = client.get(endpoint, {"cursor": cursor})
    assert unchanged.json() == {"unchanged": True, "progress_cursor": cursor}
    assert len(unchanged.content) < 1000
    assert b"History message" not in progress.content
    report = {"messages": 1000, "analysis_runs": 20, "reads": reads,
              "median_seconds": statistics.median(r["seconds"] for r in reads),
              "progress_bytes": len(progress.content), "unchanged_progress_bytes": len(unchanged.content)}
    path = Path(os.environ.get("SPECHELPER_BENCHMARK_REPORT", tmp_path / "conversation-read.json"))
    path.write_text(json.dumps(report, indent=2) + "\n")
