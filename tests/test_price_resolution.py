import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "execution"))

from report_engine import _resolve_current_price, calculate_v2_risk

def test_resolve_current_price_from_details():
    mock_str_data = {
        "details": {
            "ltf_layer1": {
                "last_close": 4405.50,
                "atr": 5.0,
                "fvgs": [],
                "order_blocks": []
            },
            "raw_ltf_structure": [
                {"type": "HH", "price": 4500.0, "index": 100}
            ]
        }
    }
    # Should resolve 4405.50 (or live quote if available), NOT the swing high 4500.0
    price = _resolve_current_price("UNKNOWN_TEST_SYM", mock_str_data)
    assert price == 4405.50, f"Expected 4405.50, got {price}"

def test_calculate_v2_risk_uses_current_price():
    mock_str_data = {
        "details": {
            "ltf_layer1": {
                "last_close": 4405.50,
                "atr": 5.0,
                "fvgs": [],
                "order_blocks": []
            },
            "raw_ltf_structure": [
                {"type": "HH", "price": 4500.0, "index": 100}
            ]
        }
    }
    risk = calculate_v2_risk("SHORT_BIAS", mock_str_data, 0, symbol="UNKNOWN_TEST_SYM")
    assert risk is not None
    assert risk["ENTRY_PRICE"] == 4405.50, f"Expected ENTRY_PRICE 4405.50, got {risk['ENTRY_PRICE']}"
    assert risk["CURRENT_PRICE"] == 4405.50
    # Stop loss for SHORT should be based on 4405.50 + buffer (not 4500.0)
    assert risk["STOP_LOSS"] < 4450.0, f"SL too high: {risk['STOP_LOSS']}"
