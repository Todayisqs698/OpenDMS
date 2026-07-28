import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backend.app.camera as camera
from modules.ai.local_decision_engine import check_fatigue


def test_drivepilot_fatigue_thresholds_are_used():
    assert camera._SLIGHT_CLOSED_SEC == 1.10
    assert camera._SEVERE_CLOSED_SEC == 2.50
    assert camera._SLIGHT_PERCLOS == 0.30
    assert camera._SEVERE_PERCLOS == 0.52


def test_fatigue_escalation_matches_drivepilot_timing():
    assert check_fatigue(1.0).get("action_code") == "normal"
    assert check_fatigue(camera._SLIGHT_CLOSED_SEC).get("severity") == "mild"
    assert check_fatigue(camera._SEVERE_CLOSED_SEC).get("severity") == "severe"


def test_camera_realtime_policy_does_not_import_head_or_gaze_alerts():
    source = Path(camera.__file__).read_text(encoding="utf-8")
    assert "check_head_deviation" not in source
    assert "check_gaze_deviation" not in source
