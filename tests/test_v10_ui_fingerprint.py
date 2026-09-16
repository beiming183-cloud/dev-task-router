from __future__ import annotations

from dev_task_router.ui_fingerprint import UIFingerprint, UIFingerprintStore


def test_ui_fingerprint_does_not_persist_dynamic_ui_text(tmp_path) -> None:
    secret = "Top Secret Project Conversation"
    rows = {
        "conversation": [
            {"name": secret, "control_type": "Text", "automation_id": "conversation-title"},
            {"name": "Send", "control_type": "Button", "automation_id": "send-button"},
        ]
    }
    fingerprint = UIFingerprint.from_rows(
        rows,
        tracked_labels={"conversation.send": ("Send",)},
        platform="win32",
    )
    store = UIFingerprintStore(tmp_path)
    store.save(fingerprint)

    raw = store.path.read_text(encoding="utf-8")
    assert secret not in raw
    assert fingerprint.tracked_hits == {"conversation.send": 1}
    assert fingerprint.stable_control_count == 1
    assert store.compare(fingerprint).status == "MATCH"


def test_untracked_dynamic_message_controls_do_not_create_false_drift(tmp_path) -> None:
    labels = {"conversation.send": ("Send",)}
    baseline = UIFingerprint.from_rows(
        {
            "conversation": [
                {"name": "Chat A", "control_type": "Text", "automation_id": "message-100"},
                {"name": "Send", "control_type": "Button", "automation_id": "send-button"},
            ]
        },
        tracked_labels=labels,
        platform="win32",
    )
    current = UIFingerprint.from_rows(
        {
            "conversation": [
                {"name": "Chat B", "control_type": "Text", "automation_id": "message-999"},
                {"name": "Send", "control_type": "Button", "automation_id": "send-button"},
            ]
        },
        tracked_labels=labels,
        platform="win32",
    )
    store = UIFingerprintStore(tmp_path)
    store.save(baseline)

    assert baseline.digest == current.digest
    assert store.compare(current).status == "MATCH"


def test_ui_fingerprint_detects_calibrated_selector_structure_drift(tmp_path) -> None:
    baseline = UIFingerprint.from_rows(
        {
            "mode": [
                {"name": "High", "control_type": "MenuItem", "automation_id": "effort-high"},
            ]
        },
        tracked_labels={"mode.effort.high": ("High",)},
        platform="win32",
    )
    store = UIFingerprintStore(tmp_path)
    assert store.compare(baseline).status == "UNCALIBRATED"
    store.save(baseline)

    drift = UIFingerprint.from_rows(
        {
            "mode": [
                {"name": "Thinking High", "control_type": "MenuItem", "automation_id": "effort-high-v2"},
            ]
        },
        tracked_labels={"mode.effort.high": ("High",)},
        platform="win32",
    )
    comparison = store.compare(drift)
    assert comparison.status == "DRIFT"
    assert comparison.drifted is True
    assert any("digest changed" in reason for reason in comparison.reasons)
