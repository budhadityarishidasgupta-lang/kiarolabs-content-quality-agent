# confidence-calibration

Severity and confidence are separate.

- severity = impact if true
- confidence = certainty the issue is real

Thresholds:
- >= 0.95 strong recommendation
- 0.80 - 0.94 human review
- 0.60 - 0.79 informational
- < 0.60 no finding unless a critical deterministic rule failed
