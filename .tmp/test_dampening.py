import sys
import os
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'execution'))
from execution.report_engine import aggregate_v2_confidence
import json

# Institutional Scenario: High structure clarity, but a medium news risk alert
str_res = {
    "details": {
        "ltf_layer1": {"layer1_score": 25.0, "notes": "Strong HH/HL chain"}
    },
    "layer2_score": 26.0,
    "final_signal": "LONG_BIAS"
}
hist_res = {"layer3_score": 15.0}
news_res = {
    "layer4_score": 5.0,
    "final_penalty": 50.0,
    "risk_state": "CAUTION"
}

conf, action = aggregate_v2_confidence(str_res, hist_res, news_res)

print(f"Final Confidence: {conf}")
print(f"Action: {action}")
print(f"Dampening Applied: {news_res.get('dampening_applied', False)}")
print(f"Final Penalty after dampening: {conf - (10.0 + 25.0 + 26.0 + 15.0 + 5.0)}") # This should reflect the subtraction logic
