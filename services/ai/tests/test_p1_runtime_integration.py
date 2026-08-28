from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import inspect
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from app.context.runtime import BusinessContextClient, P1RuntimeContextResponse, validate_freshness_response, validate_runtime_context
from app.integrations.result_storage import ObjectWriteError, S3ResultObjectStore, build_result_key, canonical_json
from app.requirement_clarification.formal_mock import FormalMockRequirementClarifier
from app.providers.base import MalformedResponseSubtype, ProviderMalformedResponse
from app.tasking.repository import EXPIRES_AT, RETENTION_CLASS, InMemoryTaskRepository, MySQLTaskRepository, TaskRecord
from app.workers.runtime import TaskRuntime


AI_ROOT = Path(__file__).parents[1]
VALID_SAMPLE = AI_ROOT / "contracts" / "candidates" / "m2-requirement-clarification" / "fixed-samples" / "valid.json"


def requirement_content(*, mode="standard", saved=False, raw="需求原文"):
    content = deepcopy(json.loads(VALID_SAMPLE.read_text(encoding="utf-8"))["requirement_content"])
    content["raw_input"] = raw
    content["raw_input_ref"] = {"source_type":"manual", "source_id":"4", "source_version_id":None, "content_hash":hashlib.sha256(raw.encode("utf-8")).hexdigest(), "label":"Requirement title"}
    content["clarification"]["mode"] = mode
    content["clarification"]["continue_deep_confirmed"] = saved
    return content


def context_payload(*, mode="standard", round_no=2, saved=False, raw="需求原文"):
    return {"contract_version":"p1-runtime-context.v1", "task_public_id":"t-runtime", "target":{"object_type":"requirement","object_id":"4","object_version_id":"5"}, "target_snapshot_hash":"a"*64, "input":{"mode":mode,"round_no":round_no,"continue_deep_confirmed":saved}, "source_ref_ids":["4"], "risk_acceptances":[], "requirement_content":requirement_content(mode=mode,saved=saved,raw=raw)}


def task_record(*, status="queued"):
    return TaskRecord("t-runtime", "1", "2", "3", "4", "5", "a"*64, "command", "trace", status=status, db_id=9)


def test_context_wrapper_strict_target_hash_and_saved_source_binding():
    payload = context_payload()
    response = validate_runtime_context(payload, task_public_id="t-runtime", target_snapshot_hash="a"*64, target_object_type="requirement", target_object_id="4", target_object_version_id="5")
    assert response.requirement_content["raw_input_ref"] == payload["requirement_content"]["raw_input_ref"]
    with pytest.raises(ValueError): P1RuntimeContextResponse.model_validate({**payload, "extra":True})
    wrong = deepcopy(payload); wrong["target"]["object_id"] = "6"
    with pytest.raises(ValueError, match="target id"): validate_runtime_context(wrong, task_public_id="t-runtime", target_snapshot_hash="a"*64, target_object_id="4")
    wrong = deepcopy(payload); wrong["requirement_content"]["raw_input_ref"]["content_hash"] = "b"*64
    with pytest.raises(ValueError, match="content_hash"): P1RuntimeContextResponse.model_validate(wrong)


def test_deep_round_four_requires_saved_confirmation_and_legacy_missing_is_false():
    with pytest.raises(ValueError): P1RuntimeContextResponse.model_validate(context_payload(mode="deep",round_no=4,saved=False))
    assert P1RuntimeContextResponse.model_validate(context_payload(mode="deep",round_no=4,saved=True)).input.continue_deep_confirmed
    legacy = context_payload(); del legacy["requirement_content"]["clarification"]["continue_deep_confirmed"]
    assert P1RuntimeContextResponse.model_validate(legacy).input.continue_deep_confirmed is False


def test_context_request_only_token_budget_and_freshness_is_strict():
    seen = {}
    def handler(request): seen.update(json.loads(request.content)); return httpx.Response(200,json={"ok":True})
    client = BusinessContextClient(base_url="http://business",token="t",transport=httpx.MockTransport(handler))
    assert client.context_snapshot("t-runtime",trace_id="trace",token_budget=100)["ok"] and seen == {"token_budget":100}
    with pytest.raises(ValueError): client.context_snapshot("t-runtime",trace_id="trace",token_budget=0)
    valid = {"fresh":True,"current_snapshot_hash":"a"*64,"current_version_id":"5"}
    assert validate_freshness_response(valid,target_snapshot_hash="a"*64,target_object_version_id="5").fresh
    with pytest.raises(ValueError): validate_freshness_response({**valid,"extra":1},target_snapshot_hash="a"*64,target_object_version_id="5")


def test_mysql_task_dict_row_normalizes_numeric_contract_identifiers():
    row = {
        "id": 9, "task_public_id": "t-runtime", "user_id": 1, "project_id": 2,
        "project_version_id": 3, "module": "product_design", "task_type": "requirement.clarify",
        "target_object_type": "requirement", "target_object_id": 4, "target_object_version_id": 5,
        "target_snapshot_hash": "a" * 64, "command_id": "command", "trace_id": "trace",
        "status": "queued", "failure_code": None,
    }
    task = MySQLTaskRepository._row(row)
    assert (task.user_id, task.project_id, task.project_version_id) == ("1", "2", "3")
    assert (task.target_object_id, task.target_object_version_id) == ("4", "5")
    assert task.db_id == 9


def test_mysql_task_tuple_row_normalizes_identifiers_and_preserves_null_version():
    row = (9, "t-runtime", 1, 2, 3, "product_design", "requirement.clarify", "requirement", 4, None, "a" * 64, "command", "trace", "queued", None)
    task = MySQLTaskRepository._row(row)
    assert (task.user_id, task.project_id, task.project_version_id) == ("1", "2", "3")
    assert task.target_object_id == "4"
    assert task.target_object_version_id is None
    assert task.db_id == 9


def test_mapped_mysql_task_version_matches_freshness_string_guard():
    row = {
        "id": 9, "task_public_id": "t-runtime", "user_id": 1, "project_id": 2,
        "project_version_id": 3, "module": "product_design", "task_type": "requirement.clarify",
        "target_object_type": "requirement", "target_object_id": 4, "target_object_version_id": 5,
        "target_snapshot_hash": "a" * 64, "command_id": "command", "trace_id": "trace",
        "status": "queued", "failure_code": None,
    }
    task = MySQLTaskRepository._row(row)
    valid = {"fresh": True, "current_snapshot_hash": "a" * 64, "current_version_id": "5"}
    assert validate_freshness_response(valid, target_snapshot_hash=task.target_snapshot_hash, target_object_version_id=task.target_object_version_id).fresh
    with pytest.raises(ValueError, match="version"):
        validate_freshness_response({**valid, "current_version_id": "6"}, target_snapshot_hash=task.target_snapshot_hash, target_object_version_id=task.target_object_version_id)


class FakeS3:
    def __init__(self): self.objects = {}
    def head_object(self,**kw):
        if kw["Key"] not in self.objects: raise FileNotFoundError
        return {"Metadata":{"sha256":self.objects[kw["Key"]][1]}}
    def get_object(self,**kw):
        if kw["Key"] not in self.objects: raise FileNotFoundError
        return {"Body":io.BytesIO(self.objects[kw["Key"]][0])}
    def put_object(self,**kw):
        assert kw["IfNoneMatch"] == "*" and kw["ContentType"] == "application/json"
        if kw["Key"] in self.objects: raise RuntimeError("precondition failed")
        self.objects[kw["Key"]] = (kw["Body"],kw["Metadata"]["sha256"])


def test_s3_canonical_write_once_and_body_metadata_tampering():
    fake=FakeS3(); store=S3ResultObjectStore(fake,bucket="b")
    content={"z":"中文","a":{"array":[2,{"b":1,"a":0}]}}
    expected='{"a":{"array":[2,{"a":0,"b":1}]},"z":"中文"}'.encode("utf-8")
    assert canonical_json(content)==expected and not expected.endswith(b"\n")
    key,digest=store.put_result(project_id="1",task_public_id="t-runtime",ai_call_id="2",result_no=1,content=content)
    assert fake.objects[key][0]==expected
    assert key==build_result_key(prefix="ai-results/",project_id="1",task_public_id="t-runtime",ai_call_id="2",result_no=1,content_fingerprint=digest)
    assert store.put_result(project_id="1",task_public_id="t-runtime",ai_call_id="2",result_no=1,content=content)==(key,digest)
    fake.objects[key]=(b"{}",digest)
    with pytest.raises(ObjectWriteError,match="body hash"): store.verify_result(key=key,content_fingerprint=digest)
    fake.objects[key]=(expected,"c"*64)
    with pytest.raises(ObjectWriteError,match="hash mismatch"): store.verify_result(key=key,content_fingerprint=digest)


def outbox_validator():
    root=AI_ROOT/"schemas"/"v0.1"; base=json.loads((root/"event-envelope.schema.json").read_text(encoding="utf-8")); schema=json.loads((root/"ai-outbox-event.schema.json").read_text(encoding="utf-8")); schema["allOf"][0]=base; schema["$defs"]=base["$defs"]
    def local(value):
        if isinstance(value,dict): return {key:local(item) for key,item in value.items()}
        if isinstance(value,list): return [local(item) for item in value]
        if isinstance(value,str) and value.startswith("event-envelope.schema.json#/"): return value.removeprefix("event-envelope.schema.json")
        return value
    return Draft202012Validator(local(schema),format_checker=FormatChecker())


class CaptureCursor:
    def execute(self,*args): self.args=args


@pytest.mark.parametrize(("name","result","status","failure"),[("ai.task.preparing","success","preparing",None),("ai.task.quality_blocked","blocked","quality_blocked","TRACEABILITY_INCOMPLETE"),("ai.task.stale_target","blocked","stale_target","TARGET_NOT_FRESH"),("ai.task.failed","failed","failed","AI_RUNTIME_FAILED")])
def test_task_outbox_envelopes_validate(name,result,status,failure):
    cursor=CaptureCursor(); MySQLTaskRepository._insert_outbox(cursor,task_record(),event_name=name,result_status=result,now=datetime.now(UTC),task_status=status,failure_code=failure)
    envelope=json.loads(cursor.args[1][6]); outbox_validator().validate(envelope)
    assert envelope["payload_json"]["task_status"]==status and "content_ref" not in json.dumps(envelope)


def test_result_generated_outbox_validates_and_uses_result_fingerprint():
    cursor=CaptureCursor(); MySQLTaskRepository._insert_outbox(cursor,task_record(),event_name="ai.result.generated",result_status="success",now=datetime.now(UTC),ai_call_id=2,ai_result_id=3,result_payload={"candidate_only":True,"result_id":"3","content_fingerprint":"b"*64,"target_snapshot_hash":"a"*64})
    envelope=json.loads(cursor.args[1][6]); outbox_validator().validate(envelope)
    assert envelope["payload_json"]["content_fingerprint"]=="b"*64 and "content_ref" not in json.dumps(envelope)


class TrackingRepository(InMemoryTaskRepository):
    def __init__(self): super().__init__(); self.history=[]
    def update_status(self,task_public_id,status,*,failure_code=None): super().update_status(task_public_id,status,failure_code=failure_code); self.history.append(status)
    def mark_status_with_event(self,task_public_id,status,*,failure_code=None,event_name=None): super().mark_status_with_event(task_public_id,status,failure_code=failure_code,event_name=event_name); self.history.append(status)


class ContextClient:
    def __init__(self,*,stale=False,fail=False): self.stale,self.fail=stale,fail
    def target_freshness(self,task_public_id,*,trace_id,target_snapshot_hash): return {"fresh":not self.stale,"current_snapshot_hash":(("b" if self.stale else "a")*64),"current_version_id":"6" if self.stale else "5"}
    def context_snapshot(self,task_public_id,*,trace_id,token_budget):
        if self.fail: raise RuntimeError("context unavailable")
        return context_payload()


def make_runtime(repo,*,context=None,provider=None,store=None):
    repo.bundle={"fingerprint":"f"*64}
    return TaskRuntime(repository=repo,context_client=context or ContextClient(),provider=provider or FormalMockRequirementClarifier(),token_budget=12000,object_store=store or S3ResultObjectStore(FakeS3(),bucket="b"))


def result_source_refs(value):
    refs=[]
    if isinstance(value,dict):
        for key,item in value.items():
            if key=="source_refs": refs.extend(item)
            else: refs.extend(result_source_refs(item))
    elif isinstance(value,list):
        for item in value: refs.extend(result_source_refs(item))
    return refs


def test_worker_ready_sequence_call_enum_and_manual_source_binding():
    class CapturingProvider(FormalMockRequirementClarifier):
        def run(self,task,sources): self.execution=super().run(task,sources); return self.execution
    provider=CapturingProvider(); repo=TrackingRepository(); repo.create_task(task_record()); make_runtime(repo,provider=provider).execute(task_public_id="t-runtime",trace_id="trace")
    assert repo.history==["preparing","generating","checking","ready"] and repo.calls[0]["status"]=="succeeded"
    assert repo.tasks["t-runtime"].status=="ready" and len(repo.results)==1
    assert repo.contexts[0]["source_type"]=="manual" and repo.contexts[0]["source_id"]=="4" and repo.contexts[0]["source_version_id"] is None
    assert repo.contexts[0]["content_fingerprint"]==requirement_content()["raw_input_ref"]["content_hash"]
    expected=requirement_content()["raw_input_ref"]; refs=result_source_refs(provider.execution.result)
    assert refs and all(ref==expected for ref in refs)
    for event in repo.outbox: outbox_validator().validate(event)


@pytest.mark.parametrize(("surface","field","value"),[("context","source_type","requirement"),("context","source_version_id","7"),("result","label","tampered title")])
def test_worker_rejects_tampered_source_binding_before_result_write(surface,field,value):
    class TamperingProvider(FormalMockRequirementClarifier):
        def run(self,task,sources):
            execution=super().run(task,sources)
            if surface=="context": execution.context_snapshot["sources"][0][field]=value
            else: result_source_refs(execution.result)[0][field]=value
            return execution
    fake=FakeS3(); store=S3ResultObjectStore(fake,bucket="b"); repo=TrackingRepository(); repo.create_task(task_record())
    with pytest.raises(ValueError,match="source"):
        make_runtime(repo,provider=TamperingProvider(),store=store).execute(task_public_id="t-runtime",trace_id="trace")
    assert fake.objects=={} and repo.results==[] and repo.contexts==[]
    assert repo.tasks["t-runtime"].status=="failed" and repo.calls[0]["status"]=="succeeded"
    assert all(event.get("event_name")!="ai.result.generated" for event in repo.outbox)


def test_worker_quality_blocked_call_succeeds_without_readable_result():
    class QualityProvider(FormalMockRequirementClarifier):
        def run(self,task,sources): execution=super().run(task,sources); execution.result["result_kind"]="unsupported"; return execution
    repo=TrackingRepository(); repo.create_task(task_record()); make_runtime(repo,provider=QualityProvider()).execute(task_public_id="t-runtime",trace_id="trace")
    assert repo.history==["preparing","generating","checking","quality_blocked"] and repo.calls[0]["status"]=="succeeded"
    assert repo.results==[] and repo.get_task("t-runtime").result_ref is None
    outbox_validator().validate(repo.outbox[-1])


def test_worker_stale_and_exception_reach_terminal_facts():
    stale=TrackingRepository(); stale.create_task(task_record()); make_runtime(stale,context=ContextClient(stale=True)).execute(task_public_id="t-runtime",trace_id="trace")
    assert stale.history==["preparing","stale_target"]; outbox_validator().validate(stale.outbox[-1])
    failed=TrackingRepository(); failed.create_task(task_record())
    with pytest.raises(RuntimeError,match="context unavailable"): make_runtime(failed,context=ContextClient(fail=True)).execute(task_public_id="t-runtime",trace_id="trace")
    assert failed.history==["preparing","failed"] and failed.tasks["t-runtime"].failure_code=="AI_RUNTIME_FAILED"; outbox_validator().validate(failed.outbox[-1])


def test_call_fails_only_when_provider_invocation_raises():
    class ProviderFailure(FormalMockRequirementClarifier):
        def run(self,task,sources): raise RuntimeError("provider failed")
    provider_failed=TrackingRepository(); provider_failed.create_task(task_record())
    with pytest.raises(RuntimeError,match="provider failed"): make_runtime(provider_failed,provider=ProviderFailure()).execute(task_public_id="t-runtime",trace_id="trace")
    assert provider_failed.calls[0]["status"]=="failed" and provider_failed.tasks["t-runtime"].status=="failed"
    class StorageFailure:
        def put_result(self,**kwargs): raise ObjectWriteError("storage failed")
    storage_failed=TrackingRepository(); storage_failed.create_task(task_record())
    with pytest.raises(ObjectWriteError,match="storage failed"): make_runtime(storage_failed,store=StorageFailure()).execute(task_public_id="t-runtime",trace_id="trace")
    assert storage_failed.calls[0]["status"]=="succeeded" and storage_failed.tasks["t-runtime"].status=="failed"


def test_malformed_provider_log_is_visible_and_contains_no_provider_content(caplog):
    class MalformedProvider(FormalMockRequirementClarifier):
        provider_id = "deepseek"
        model = "deepseek-v4-flash"

        def run(self, task, sources):
            raise ProviderMalformedResponse(
                "safe fixture",
                subtype=MalformedResponseSubtype.INVALID_QUESTION_COUNT,
                field="questions",
                rule="min_1_max_3",
            )

    repo = TrackingRepository()
    repo.create_task(task_record())
    with caplog.at_level(logging.WARNING, logger="app.workers.runtime"):
        make_runtime(repo, provider=MalformedProvider()).execute(
            task_public_id="t-runtime", trace_id="trace"
        )
    message = next(
        record.getMessage()
        for record in caplog.records
        if "provider response rejected" in record.getMessage()
    )
    assert "subtype=INVALID_QUESTION_COUNT" in message
    assert "field=questions" in message
    assert "rule=min_1_max_3" in message
    assert "safe fixture" not in message
    assert repo.tasks["t-runtime"].failure_code == "PROVIDER_MALFORMED_RESPONSE"


class SqlCursor:
    def __init__(self,*,fail_on_outbox=False): self.statements=[]; self.lastrowid=0; self.fail_on_outbox=fail_on_outbox
    def execute(self,sql,params=()):
        self.statements.append((sql,params))
        if sql.startswith("INSERT INTO ai_task"): self.lastrowid=9
        elif sql.startswith("INSERT INTO ai_call"): self.lastrowid=2
        elif sql.startswith("INSERT INTO ai_result"): self.lastrowid=3
        elif sql.startswith("INSERT INTO ai_event_outbox") and self.fail_on_outbox: raise RuntimeError("outbox insert failed")
    def fetchone(self):
        sql=self.statements[-1][0]
        if "FROM ai_task WHERE task_public_id" in sql and "SELECT status" not in sql: return None
        if "MAX(sequence_no)" in sql: return {"next_sequence_no":1}
        if "SELECT status FROM ai_task" in sql: return {"status":"checking"}
        return None
    def fetchall(self): return []
    def close(self): pass


class SqlConnection:
    def __init__(self,*,fail_on_outbox=False): self.cursor_value=SqlCursor(fail_on_outbox=fail_on_outbox); self.commits=0; self.rollbacks=0
    def cursor(self): return self.cursor_value
    def commit(self): self.commits+=1
    def rollback(self): self.rollbacks+=1
    def close(self): pass


def test_create_task_insert_uses_pymysql_compatible_bind_arity_and_commits():
    class ArityCursor(SqlCursor):
        @staticmethod
        def interpolate(sql, params):
            return sql % tuple("bound" for _ in params)
        def execute(self, sql, params=()):
            self.interpolate(sql, params)
            super().execute(sql, params)
    connection=SqlConnection(); connection.cursor_value=ArityCursor()
    created=MySQLTaskRepository(lambda:connection).create_task(replace(task_record(),db_id=None))
    insert_sql,params=next(item for item in connection.cursor_value.statements if item[0].startswith("INSERT INTO ai_task"))
    columns=insert_sql[insert_sql.index("(")+1:insert_sql.index(") VALUES")].split(",")
    values=insert_sql[insert_sql.index("VALUES (")+8:-1].split(",")
    assert len(columns)==len(values)==19 and values[2]=="1"
    assert insert_sql.count("%s")==len(params)==18
    assert created.db_id==9 and connection.commits==1 and connection.rollbacks==0
    with pytest.raises(TypeError,match="not enough arguments"):
        connection.cursor_value.interpolate(insert_sql[:-1]+",%s)",params)


def execution():
    ref=requirement_content()["raw_input_ref"]; source={"source_id":ref["source_id"],"source_version_id":ref["source_version_id"],"source_type":ref["source_type"],"content_fingerprint":ref["content_hash"],"was_injected":True,"exclusion_reason":None,"token_count":0}
    return SimpleNamespace(result={"quality":{"format_status":"passed","required_items_total":8,"required_items_met":5,"traceability_status":"passed","safety_status":"passed","major_error":False}},context_snapshot={"sources":[source]})


def test_repository_four_facts_share_retention_and_legal_call_context_mapping():
    connections=[]
    def factory(): value=SqlConnection(); connections.append(value); return value
    repo=MySQLTaskRepository(factory); created=repo.create_task(replace(task_record(),db_id=None)); bundle={"profile_id":1,"model_id":2,"skill_version_id":3,"prompt_version_id":4,"context_strategy_version_id":5,"template_version_id":6,"runtime_config_version":"0.2.0"}; call_id=repo.create_call(created,bundle,capability_fingerprint="f"*64); repo.persist_success(created,call_id,None,execution(),"key","b"*64)
    statements=[item for connection in connections for item in connection.cursor_value.statements]; inserts={sql.split(" (")[0].removeprefix("INSERT INTO "):params for sql,params in statements if sql.startswith("INSERT INTO ai_")}
    assert inserts["ai_task"][2:4]==(RETENTION_CLASS,EXPIRES_AT); assert inserts["ai_call"][3:5]==(RETENTION_CLASS,EXPIRES_AT); assert inserts["ai_result"][1:3]==(RETENTION_CLASS,EXPIRES_AT); assert inserts["ai_context_usage"][1:3]==(RETENTION_CLASS,EXPIRES_AT)
    call_insert=next(item for item in statements if item[0].startswith("INSERT INTO ai_call")); assert call_insert[1][-3]=="started" and call_insert[1][-1]=="unavailable"
    assert any(sql.startswith("UPDATE ai_call SET status") and params[0]=="succeeded" for sql,params in statements)
    context_insert=next(item for item in statements if item[0].startswith("INSERT INTO ai_context_usage")); assert context_insert[1][5:9]==("manual",4,None,"direct")


def test_repository_persists_pricing_version_with_profile_calculated_cost():
    connection=SqlConnection(); repo=MySQLTaskRepository(lambda:connection)
    value=execution(); value.provider_response={"provider":"deepseek","model":"deepseek-v4-flash","provider_request_id":"request-1","usage":{"input_tokens":10,"output_tokens":5,"billed_tokens":15,"estimated_cost":"0.000001","currency_code":"USD","cost_source":"profile_calculated","pricing_version":"2026-07-29"}}
    repo.persist_success(task_record(status="checking"),2,None,value,"key","b"*64)
    sql,params=next(item for item in connection.cursor_value.statements if item[0].startswith("UPDATE ai_call SET status"))
    assert "pricing_version=%s" in sql
    assert params[7:9]==("profile_calculated","2026-07-29")


def test_result_transaction_rolls_back_if_outbox_fails_and_non_numeric_source_fails_closed():
    connection=SqlConnection(fail_on_outbox=True); repo=MySQLTaskRepository(lambda:connection)
    with pytest.raises(RuntimeError,match="outbox insert failed"): repo.persist_success(task_record(status="checking"),2,None,execution(),"key","b"*64)
    assert connection.commits==0 and connection.rollbacks==1
    bad=execution(); bad.context_snapshot["sources"][0]["source_id"]="manual/ref"; connection=SqlConnection()
    with pytest.raises(ValueError,match="source_id"): MySQLTaskRepository(lambda:connection).persist_success(task_record(status="checking"),2,None,bad,"key","b"*64)
    assert connection.rollbacks==1


def test_worker_production_factory_and_mysql_repository_fail_closed_without_runtime_or_redis_authority(monkeypatch):
    for name in ("AI_DATABASE_URL","AI_RESULT_STORAGE_ENDPOINT","AI_RESULT_STORAGE_BUCKET","AI_BUSINESS_API_URL","AI_BUSINESS_API_JWT_SECRET"): monkeypatch.delenv(name,raising=False)
    from app.workers.tasks import _build_runtime_from_env
    with pytest.raises(RuntimeError,match="not configured"): _build_runtime_from_env()
    source=inspect.getsource(MySQLTaskRepository); assert "redis" not in source.lower() and "InMemory" not in source


def test_mysql_bundle_resolver_rejects_content_hash_drift():
    class Cursor:
        def execute(self,sql,params=()): pass
        def fetchall(self):
            return [{"model_id":1,"provider_code":"formal_mock","model_code":"requirement-clarifier-v1","profile_id":2,"profile_name":"portfolio-p1-formal-mock","runtime_config_version":"0.2.0","skill_version_id":3,"skill_content_hash":"a"*64,"skill_rule_text":"actual","prompt_version_id":4,"prompt_content_hash":"b"*64,"system_prompt":"s","user_template":"u","prompt_variables_json":{},"template_version_id":5,"template_content_hash":"c"*64,"template_content":"t","context_strategy_version_id":6,"context_strategy_content_hash":"d"*64,"required_context_json":{},"optional_context_json":{},"limit_config_json":{},"compression_policy_json":{}}]
        def close(self): pass
    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass
    with pytest.raises(RuntimeError,match="hash drift"):
        MySQLTaskRepository(Connection).resolve_bundle()
