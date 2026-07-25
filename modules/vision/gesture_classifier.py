"""
15+ gesture geometric classifier — pure MediaPipe Hands landmark math, zero deps

Geometric rules based on finger joint angles:
- Finger extended: tip-to-wrist distance > MCP-to-wrist distance
- Thumb direction: thumb tip angle relative to palm
- Inter-finger angles, relative positions

MediaPipe Hand Landmarks (21 points):
  0=Wrist, 1-4=Thumb(CMC,MCP,IP,TIP), 5-8=Index, 9-12=Middle, 13-16=Ring, 17-20=Pinky
"""
from __future__ import annotations
import math
import logging

logger = logging.getLogger(__name__)

# Gesture -> action mapping
GESTURE_ACTION_MAP = {
    "open_palm":      {"action_code": "open_ac",     "label": "open AC",         "icon": "open"},
    "fist":           {"action_code": "close_ac",    "label": "close AC",        "icon": "fist"},
    "thumbs_up":      {"action_code": "confirm",     "label": "confirm / play",  "icon": "thumbs_up"},
    "thumbs_down":    {"action_code": "cancel",      "label": "cancel / pause",  "icon": "thumbs_down"},
    "index_point":    {"action_code": "attention",   "label": "driver status",   "icon": "point"},
    "peace":          {"action_code": "greeting",    "label": "wake assistant",  "icon": "peace"},
    "ok_sign":        {"action_code": "confirm_ac",  "label": "confirm AC set",  "icon": "ok"},
    "three_fingers":  {"action_code": "mode_3",      "label": "switch mode",     "icon": "three"},
    "four_fingers":   {"action_code": "mode_4",      "label": "navigate home",   "icon": "four"},
    "pinch":          {"action_code": "zoom_in",     "label": "zoom in / up",    "icon": "pinch"},
    "swipe_left":     {"action_code": "prev_track",  "label": "previous track",  "icon": "swipe_l"},
    "swipe_right":    {"action_code": "next_track",  "label": "next track",      "icon": "swipe_r"},
    "palm_up":        {"action_code": "volume_up",   "label": "volume up",       "icon": "palm_up"},
    "palm_down":      {"action_code": "volume_down", "label": "volume down",     "icon": "palm_dn"},
    "call_me":        {"action_code": "call",        "label": "answer call",     "icon": "call"},
    "rock_on":        {"action_code": "mute",        "label": "mute / DND",      "icon": "rock"},
}


class GestureClassifier:
    """Geometry-based gesture classifier using MediaPipe 21-point hand landmarks."""

    # Landmark indices
    WRIST = 0
    THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP = 4, 8, 12, 16, 20
    THUMB_IP, INDEX_PIP, MIDDLE_PIP, RING_PIP, PINKY_PIP = 3, 6, 10, 14, 18
    THUMB_MCP, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP = 2, 5, 9, 13, 17

    @staticmethod
    def _distance(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)

    def _is_finger_extended(self, tip, pip, mcp, wrist):
        """Finger is extended if tip is further from wrist than MCP."""
        tip_dist = self._distance(tip, wrist)
        mcp_dist = self._distance(mcp, wrist)
        return tip_dist > mcp_dist * 1.05

    def _get_extended_fingers(self, landmarks):
        """Return set of extended finger names."""
        wrist = landmarks[self.WRIST]
        fingers = {
            "thumb": (landmarks[self.THUMB_TIP], landmarks[self.THUMB_IP], landmarks[self.THUMB_MCP]),
            "index": (landmarks[self.INDEX_TIP], landmarks[self.INDEX_PIP], landmarks[self.INDEX_MCP]),
            "middle": (landmarks[self.MIDDLE_TIP], landmarks[self.MIDDLE_PIP], landmarks[self.MIDDLE_MCP]),
            "ring": (landmarks[self.RING_TIP], landmarks[self.RING_PIP], landmarks[self.RING_MCP]),
            "pinky": (landmarks[self.PINKY_TIP], landmarks[self.PINKY_PIP], landmarks[self.PINKY_MCP]),
        }
        extended = set()
        for name, (tip, pip, mcp) in fingers.items():
            if self._is_finger_extended(tip, pip, mcp, wrist):
                extended.add(name)
        return extended

    def _thumb_orientation(self, landmarks):
        """Return thumb direction: 'up' / 'down' / 'side'."""
        wrist = landmarks[self.WRIST]
        thumb_tip = landmarks[self.THUMB_TIP]
        dx = thumb_tip[0] - wrist[0]
        dy = wrist[1] - thumb_tip[1]  # y is inverted in image coords
        if abs(dy) < abs(dx) * 0.5:
            return "side"
        return "up" if dy > 0 else "down"

    def _is_pinch(self, landmarks):
        """Thumb tip and index tip are very close."""
        return self._distance(landmarks[self.THUMB_TIP], landmarks[self.INDEX_TIP]) < 0.03

    def classify(self, landmarks_21: list) -> tuple:
        """
        Classify gesture from 21 normalized landmarks.

        Args:
            landmarks_21: 21 points [(x, y), ...] in normalized coords (0~1)

        Returns:
            (gesture_name, confidence, action_code, label, icon)
            or (None, 0.0, "", "", "")
        """
        if not landmarks_21 or len(landmarks_21) < 21:
            return None, 0.0, "", "", ""

        pts = landmarks_21
        ext = self._get_extended_fingers(pts)
        n_ext = len(ext)

        # 1. Pinch: thumb + index tips very close
        if self._is_pinch(pts) and "index" in ext:
            a = GESTURE_ACTION_MAP["pinch"]
            return "pinch", 0.85, a["action_code"], a["label"], a["icon"]

        # 2. OK sign: pinch + other 3 fingers extended
        if self._is_pinch(pts) and n_ext >= 4 and "middle" in ext and "ring" in ext and "pinky" in ext:
            a = GESTURE_ACTION_MAP["ok_sign"]
            return "ok_sign", 0.88, a["action_code"], a["label"], a["icon"]

        # 3-4. Thumbs up/down
        thumb_dir = self._thumb_orientation(pts)
        if thumb_dir == "up" and "thumb" in ext and n_ext <= 2:
            a = GESTURE_ACTION_MAP["thumbs_up"]
            return "thumbs_up", 0.90, a["action_code"], a["label"], a["icon"]
        if thumb_dir == "down" and "thumb" in ext and n_ext <= 2:
            a = GESTURE_ACTION_MAP["thumbs_down"]
            return "thumbs_down", 0.90, a["action_code"], a["label"], a["icon"]

        # 5. Index point: only index extended
        if ext == {"index"}:
            a = GESTURE_ACTION_MAP["index_point"]
            return "index_point", 0.92, a["action_code"], a["label"], a["icon"]

        # 6. Peace: index + middle
        if ext == {"index", "middle"} and "thumb" not in ext:
            a = GESTURE_ACTION_MAP["peace"]
            return "peace", 0.92, a["action_code"], a["label"], a["icon"]

        # 7. Three fingers
        if n_ext == 3:
            if ext == {"index", "middle", "ring"} or ext == {"thumb", "index", "middle"}:
                a = GESTURE_ACTION_MAP["three_fingers"]
                return "three_fingers", 0.85, a["action_code"], a["label"], a["icon"]

        # 8. Four fingers
        if n_ext == 4:
            a = GESTURE_ACTION_MAP["four_fingers"]
            return "four_fingers", 0.85, a["action_code"], a["label"], a["icon"]

        # 9. Open palm: all 5 extended
        if n_ext == 5:
            a = GESTURE_ACTION_MAP["open_palm"]
            return "open_palm", 0.90, a["action_code"], a["label"], a["icon"]

        # 10. Fist: none extended
        if n_ext == 0:
            a = GESTURE_ACTION_MAP["fist"]
            return "fist", 0.90, a["action_code"], a["label"], a["icon"]

        # 11. Rock on: index + pinky
        if ext == {"index", "pinky"}:
            a = GESTURE_ACTION_MAP["rock_on"]
            return "rock_on", 0.88, a["action_code"], a["label"], a["icon"]

        # 12. Call me: thumb + pinky
        if ext == {"thumb", "pinky"}:
            a = GESTURE_ACTION_MAP["call_me"]
            return "call_me", 0.88, a["action_code"], a["label"], a["icon"]

        # 13-14. Palm direction (mid fingertip vs wrist y)
        mid_tip_y = pts[self.MIDDLE_TIP][1]
        wrist_y = pts[self.WRIST][1]
        palm_facing_up = mid_tip_y > wrist_y

        if palm_facing_up and n_ext >= 4:
            a = GESTURE_ACTION_MAP["palm_up"]
            return "palm_up", 0.80, a["action_code"], a["label"], a["icon"]
        if not palm_facing_up and n_ext >= 4 and "thumb" not in ext:
            a = GESTURE_ACTION_MAP["palm_down"]
            return "palm_down", 0.80, a["action_code"], a["label"], a["icon"]

        # 15-16. Swipe (index lateral offset from wrist)
        index_x = pts[self.INDEX_TIP][0]
        wrist_x = pts[self.WRIST][0]
        if "index" in ext and abs(index_x - wrist_x) > 0.15:
            if index_x < wrist_x:
                a = GESTURE_ACTION_MAP["swipe_left"]
                return "swipe_left", 0.75, a["action_code"], a["label"], a["icon"]
            else:
                a = GESTURE_ACTION_MAP["swipe_right"]
                return "swipe_right", 0.75, a["action_code"], a["label"], a["icon"]

        return None, 0.0, "", "", ""

    @staticmethod
    def get_available_gestures():
        return [
            {"gesture": k, "action_code": v["action_code"], "label": v["label"], "icon": v["icon"]}
            for k, v in GESTURE_ACTION_MAP.items()
        ]


class GestureStabilizer:
    """Debounce filter: requires N stable frames before triggering."""

    def __init__(self, hold_frames: int = 6):
        self.hold_frames = hold_frames
        self._current = None
        self._counter = 0
        self._last_triggered = None
        self._cooldown = 0  # 防止同一手势连续刷屏，触发后冷却N帧

    def update(self, gesture_name: str | None) -> dict | None:
        """
        Returns stabilized gesture action dict, or None.
        """
        if gesture_name is None:
            self._current = None
            self._counter = 0
            self._last_triggered = None
            self._cooldown = 0
            return None

        # 如果与上次触发的手势不同，重置冷却
        if gesture_name != self._last_triggered:
            self._cooldown = 0
        else:
            if self._cooldown > 0:
                self._cooldown -= 1
                return None

        if gesture_name == self._current:
            self._counter += 1
            if self._counter >= self.hold_frames:
                self._last_triggered = gesture_name
                self._cooldown = 20  # 触发后冷却20帧（约1秒），防止连续刷屏
                a = GESTURE_ACTION_MAP.get(gesture_name, {})
                if a:
                    return {
                        "gesture": gesture_name,
                        "action_code": a["action_code"],
                        "label": a["label"],
                        "icon": a["icon"],
                    }
        else:
            self._current = gesture_name
            self._counter = 1

        return None

    def reset(self):
        self._current = None
        self._counter = 0
        self._last_triggered = None
        self._cooldown = 0
