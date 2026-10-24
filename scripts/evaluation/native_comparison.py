"""Opt-in native CLI comparison using the existing trusted runtime supervisor.

This administrative harness uses synthetic data only. It refuses unavailable
quota, a busy application queue or missing roles rather than bypassing ordinary
provider limits. A failed observation is resumable and never becomes a fake score.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from reliability_benchmark import HERE, check_snapshot, write_json


def native_payload(study):
    study = Path(study).resolve()
    manifest = json.loads((study / "manifest.json").read_text())
    corpus = json.loads((HERE / "corpus.json").read_text())["cases"]
    sys.path.insert(0, str(HERE.parents[1] / "backend"))
    sys.path.insert(0, str(HERE.parents[1]))
    from core.analysis_evidence import ReliabilityReport
    from runtime.output_schema import strict_output_schema

    contexts = []
    for case in corpus:
        expected = next(row for row in manifest["cases"] if row["id"] == case["id"])
        repository = study / "repos" / case["id"]
        check_snapshot(repository, expected)
        for mode in ("source", "codebase-memory-mcp"):
            navigation = json.loads(
                (study / "navigation" / (case["id"] + "-" + mode + ".json")).read_text()
            )
            if navigation["git_sha"] != expected["git_sha"]:
                raise ValueError("Navigation context does not match the frozen source")
            contexts.append(
                {
                    "case_id": case["id"],
                    "mode": mode,
                    "git_sha": expected["git_sha"],
                    "question": case["question"],
                    "sources": navigation["sources"],
                    "files": {path: (repository / path).read_text() for path in expected["files"]},
                }
            )
    return {
        "contexts": contexts,
        "schema": strict_output_schema(ReliabilityReport.model_json_schema()),
    }


BACKEND_PROGRAM = r"""
import contextlib
import io
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from django.conf import settings
from django.db import transaction
from core.agent import RULES, ProviderUnavailable, runtime_call as trusted_runtime_call
from core.models import AIConnection, AIIdentity, Job
from core.providers import identity_for, quota_group, release_connections

def runtime_call(*args, **kwargs):
    try:
        return trusted_runtime_call(*args, **kwargs)
    except ProviderUnavailable as error:
        return {"failure":{"kind":error.kind},"quota_windows":error.quota_windows or {}, **error.context_observation}

def execute(data):
    with contextlib.redirect_stdout(io.StringIO()):
        connection=AIConnection.objects.filter(agent=data["agent"],enabled=True,status="CONNECTED").order_by("preference","id").first()
        if connection is None:
            return {"status":"blocked","reason":"No connected supported comparison provider", "responses":[]}
        identity=identity_for(connection)
        credential=str(identity.credential_id) if identity.credential_id else None
        health=runtime_call("/health?agent="+connection.agent+"&quota=true"+("&identity_id="+credential if credential else ""), timeout=25)
        if health.get("ordinary_usage_allowed") is not True:
            return {"status":"blocked","reason":"The provider has not confirmed ordinary usage is available", "quota":health.get("quota_windows",{}),"responses":[]}
        if Job.objects.filter(status__in=["QUEUED","RUNNING"]).exists():
            return {"status":"blocked","reason":"The application queue is not idle", "responses":[]}
        if not {"analyst","counter_analyst","verifier"}<=set(connection.roles):
            return {"status":"blocked","reason":"The comparison connection does not allow all three roles", "responses":[]}
        with transaction.atomic():
            members=list(quota_group(identity).select_for_update())
            if any(item.availability=="BUSY" for item in members):
                return {"status":"blocked","reason":"The comparison identity is busy", "responses":[]}
            ids=[item.pk for item in members]
            AIIdentity.objects.filter(pk__in=ids).update(availability="BUSY",retry_after=None)
            AIConnection.objects.filter(identity_id__in=ids).exclude(availability="MODEL_UNAVAILABLE").update(availability="BUSY",retry_after=None)
        results=[]
        attempts=[]
        deadline=time.monotonic()+900
        try:
            for item in data["contexts"]:
                if Job.objects.filter(status__in=["QUEUED","RUNNING"]).exists():
                    return {"status":"interrupted","reason":"Application work is waiting", "responses":results,"attempts":attempts}
                request_id=str(uuid.uuid4())
                workspace=Path(settings.DATA_DIR)/"analysis-workspaces"/request_id
                repository=workspace/item["case_id"]
                repository.mkdir(parents=True)
                attachments=Path(settings.DATA_DIR)/"requests"/request_id/"attachments"
                attachments.mkdir(parents=True)
                for relative, content in item["files"].items():
                    target=repository/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content)
                env={**os.environ,"GIT_AUTHOR_DATE":"2026-01-01T00:00:00+00:00","GIT_COMMITTER_DATE":"2026-01-01T00:00:00+00:00"}
                for arguments in (["init","-q","--initial-branch=main"],["config","user.name","Synthetic evaluation"],["config","user.email","fixture@example.invalid"],["add","--all"],["commit","-q","-m","test: pin synthetic evaluation corpus"]):
                    subprocess.run(["git","-C",str(repository),*arguments],check=True,capture_output=True,env=env)
                actual=subprocess.check_output(["git","-C",str(repository),"rev-parse","HEAD"],text=True).strip()
                if actual!=item["git_sha"]:
                    raise ValueError("Synthetic source reconstruction changed its Git version")
                outputs=[];usage=[];started=time.monotonic()
                for role,profile in (("analyst","code"),("counter_analyst","independent"),("verifier","synthesis")):
                    remaining=int(deadline-time.monotonic())
                    if remaining<5:
                        return {"status":"interrupted","reason":"The fixed comparison deadline was reached", "responses":results,"attempts":attempts}
                    role_data={"question":item["question"],"environment":"Synthetic evaluation","baseline":{"repository":item["case_id"],"sha":item["git_sha"]},"navigation_mode":item["mode"],"source_targets":item["sources"]}
                    if role=="verifier":role_data["independent_reports"]=outputs
                    instruction=("Perform an independent source analysis." if role=="analyst" else "Inspect independently before receiving any analyst conclusions." if role=="counter_analyst" else "Reconcile the two independent reports, actively seek limits and counterexamples, and produce the final qualified report.")
                    prompt=RULES+"\n"+instruction+" Return at most four decisive concise claims. Reopen the actual files under /workspace/"+item["case_id"]+" to verify exact excerpts and line ranges at the baseline commit. Keep each excerpt under ten lines. Explain configuration, temporal scope, actual exceptions and historical anomalies. No live business database is configured: JSON records are synthetic fixture files, not a live database. Never turn no counterexample found into universal validity. No numeric confidence. No source execution or modification. English output.\nUNTRUSTED DATA:\n"+json.dumps(role_data)
                    before=time.monotonic()
                    response=runtime_call("/run",{"request_id":request_id,"context_id":str(uuid.uuid4()),"independent_context":True,"session_id":None,"agent":connection.agent,"model":connection.model,"identity_id":credential,"phase":"analysis","profile":profile,"public_role":role,"workspace":str(workspace),"database":None,"context_resources":[],"context_dir":None,"prompt":prompt,"schema":data["schema"],"timeout":min(45,remaining)},timeout=min(45,remaining)+3)
                    attempts.append({"case_id":item["case_id"],"mode":item["mode"],"role":role,"usage":response.get("usage",{}),"seconds":time.monotonic()-before,"model":response.get("model",connection.model),"failure":response.get("failure"),"timed_out":response.get("timed_out",False)})
                    if response.get("failure"):
                        return {"status":"interrupted","reason":response["failure"]["kind"],"responses":results,"attempts":attempts,"quota":response.get("quota_windows",{})}
                    if response.get("timed_out"):
                        raise TimeoutError("A native comparison role timed out")
                    outputs.append(response["output"])
                    usage.append({"role":role,"usage":response.get("usage",{}),"model":response.get("model",connection.model),"seconds":time.monotonic()-before})
                results.append({"case_id":item["case_id"],"mode":item["mode"],"git_sha":item["git_sha"],"output":outputs[-1],"role_outputs":outputs,"role_usage":usage,"analysis_seconds":time.monotonic()-started,"input_tokens":sum(row["usage"]["input_tokens"] for row in usage) if all(isinstance(row["usage"].get("input_tokens"),int) for row in usage) else None,"output_tokens":sum(row["usage"]["output_tokens"] for row in usage) if all(isinstance(row["usage"].get("output_tokens"),int) for row in usage) else None,"cost":None})
                print("EVALUATION_PROGRESS "+json.dumps({"case_id":item["case_id"],"mode":item["mode"],"roles":3}),flush=True,file=__import__("sys").stderr)
        except Exception as error:
            return {"status":"interrupted","reason":type(error).__name__,"responses":results,"attempts":attempts}
        finally:
            release_connections([connection.pk])
        return {"status":"complete","responses":results,"attempts":attempts}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enable-inference", action="store_true")
    parser.add_argument("--agent", choices=["codex", "claude"], default="codex")
    args = parser.parse_args()
    if not args.enable_inference:
        parser.error(
            "Native provider inference is opt-in: pass --enable-inference after reviewing the study"
        )
    data = native_payload(args.study)
    data["agent"] = args.agent
    program = (
        BACKEND_PROGRAM + "\nprint('EVALUATION_RESULT '+json.dumps(execute(" + repr(data) + ")))\n"
    )
    completed = subprocess.run(
        [
            "rtk",
            "proxy",
            "docker",
            "compose",
            "exec",
            "-T",
            "worker",
            "python",
            "manage.py",
            "shell",
            "-c",
            "exec(__import__('sys').stdin.read())",
        ],
        input=program,
        text=True,
        capture_output=True,
        timeout=960,
        check=True,
    )
    if completed.stderr:
        print(completed.stderr.strip())
    result_line = next(
        (
            line.removeprefix("EVALUATION_RESULT ")
            for line in completed.stdout.splitlines()
            if line.startswith("EVALUATION_RESULT ")
        ),
        None,
    )
    if not result_line:
        raise ValueError("The trusted runtime did not return a comparison result")
    result = json.loads(result_line)
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "reason": result.get("reason"),
                "completed_analyses": len(result["responses"]),
            }
        )
    )


if __name__ == "__main__":
    main()
