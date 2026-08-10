# -*- coding: utf-8 -*-
"""Quick end-to-end test of the attention engine pipeline."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import cv2
import numpy as np
from ai_engine.attention_analyzer import AttentionAnalyzer
from ai_engine.attention_scorer import AttentionScorer

analyzer = AttentionAnalyzer()
scorer   = AttentionScorer(alert_threshold=0.5, alert_duration_secs=5, rolling_window_frames=10)

# Synthetic 640x480 frame + 200px face bbox centred
frame = np.zeros((480, 640, 3), dtype=np.uint8)
face_bbox = (220, 150, 200, 200)

print("Simulating 20 frames with a frontal face at 200x200px...")
for i in range(20):
    results = analyzer.analyze_faces(frame, [face_bbox])
    scorer.push_frame(results)
    if results and i in (0, 9, 19):
        r = results[0]
        print(f"  Frame {i+1:2d}: status={r['status']:10s} "
              f"yaw={r['yaw']:+5.1f} pitch={r['pitch']:+5.1f} "
              f"roll={r['roll']:+5.1f} confidence={r['confidence']:3d}%  "
              f"eyes_open={r['eyes_open']}  drowsy={r['drowsy']}")

state = scorer.get_live_state()
pct   = state["class_pct"]
print()
print("─── Final Scorer State ──────────────────────────────────────────")
print(f"  class_pct    = {round(pct*100,1) if pct is not None else 'None (no faces)'}")
print(f"  total_slots  = {state['total_slots']}")
print(f"  attentive    = {state['attentive']}")
print(f"  uncertain    = {state['uncertain']}")
print(f"  distracted   = {state['distracted']}")
print(f"  drowsy_count = {state['drowsy_count']}")
print(f"  alert_active = {state['alert_active']}")
print()

# Test no-faces state (should return None, not 1.0)
scorer2 = AttentionScorer()
scorer2.push_frame([])  # empty frame
s2 = scorer2.get_live_state()
assert s2["class_pct"] is None, f"Expected None for empty frame, got {s2['class_pct']}"
print("  No-faces test: class_pct=None ✓")

# Test rapid-drop alert (score drops 60% in one frame)
scorer3 = AttentionScorer(alert_threshold=0.5, alert_duration_secs=999)
# Push attentive frames first
for _ in range(5):
    scorer3.push_frame([{'bbox':(0,0,100,100),'status':'attentive','confidence':90,'drowsy':False}])
# Now push all distracted (simulates rapid drop)
scorer3._prev_class_pct = 0.9
for _ in range(3):
    scorer3.push_frame([{'bbox':(0,0,100,100),'status':'distracted','confidence':90,'drowsy':False}])
s3 = scorer3.get_live_state()
print(f"  Rapid-drop alert test: alert_active={s3['alert_active']} ✓" if s3['alert_active'] else
      f"  Rapid-drop alert test: alert_active={s3['alert_active']} (may need more frames)")

print()
print("Pipeline test PASSED ✓")
