from __future__ import annotations

import json

from dev_task_router.execution_evidence import ExecutionEvidenceLedger


def test_evidence_record_is_idempotent(tmp_path) -> None:
    ledger = ExecutionEvidenceLedger(tmp_path)

    first = ledger.record(
        task_id="feature",
        dispatch_id="d1",
        kind="prepared",
        data={"difficulty": "MEDIUM", "before_git_digest": "abc"},
    )
    second = ledger.record(
        task_id="feature",
        dispatch_id="d1",
        kind="prepared",
        data={"difficulty": "MEDIUM", "before_git_digest": "abc"},
    )

    assert first.event_id == second.event_id
    assert first.record_hash == second.record_hash
    assert len(ledger.events()) == 1
    assert ledger.verify_chain() is True


def test_evidence_chain_links_compact_execution_boundaries(tmp_path) -> None:
    ledger = ExecutionEvidenceLedger(tmp_path)
    prepared = ledger.record(
        task_id="feature",
        dispatch_id="d1",
        kind="PREPARED",
        data={"difficulty": "MEDIUM"},
    )
    submitted = ledger.record(
        task_id="feature",
        dispatch_id="d1",
        kind="SUBMITTED",
        data={"backend": "windows-uia-conversation"},
    )
    collected = ledger.record(
        task_id="feature",
        dispatch_id="d1",
        kind="RESPONSE_COLLECTED",
        data={"response_digest": "deadbeef", "response_chars": 42},
    )

    assert prepared.sequence == 1
    assert submitted.previous_hash == prepared.record_hash
    assert collected.previous_hash == submitted.record_hash
    assert ledger.latest_for_dispatch("d1") == collected
    assert ledger.verify_chain() is True


def test_evidence_file_contains_metadata_not_conversation_body(tmp_path) -> None:
    ledger = ExecutionEvidenceLedger(tmp_path)
    secret_body = "full assistant response should not be stored here"
    ledger.record(
        task_id="feature",
        dispatch_id="d1",
        kind="RESPONSE_COLLECTED",
        data={"response_digest": "digest-only", "response_chars": len(secret_body)},
    )

    text = ledger.path.read_text(encoding="utf-8")
    row = json.loads(text)

    assert secret_body not in text
    assert row["data"]["response_digest"] == "digest-only"
    assert row["kind"] == "RESPONSE_COLLECTED"


def test_chain_verification_detects_tampering(tmp_path) -> None:
    ledger = ExecutionEvidenceLedger(tmp_path)
    ledger.record(task_id="feature", dispatch_id="d1", kind="PREPARED")
    ledger.record(task_id="feature", dispatch_id="d1", kind="SUBMITTED")

    rows = ledger.path.read_text(encoding="utf-8").splitlines()
    second = json.loads(rows[1])
    second["data"]["unexpected"] = True
    rows[1] = json.dumps(second, ensure_ascii=False, sort_keys=True)
    ledger.path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    assert ledger.verify_chain() is False
