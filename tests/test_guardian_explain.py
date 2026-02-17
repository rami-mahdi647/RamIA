from ramia_core_ui import build_guardian_explain


def test_guardian_explain_fallback_is_deterministic_when_model_missing():
    tx = {
        "amount": 150000,
        "fee": 200,
        "outputs": 4,
        "memo": "@@@###",
        "to_addr": "ab12cd34ef56gh78",
        "burst_score": 1.8,
        "timestamp": 1700000000,
    }
    out1 = build_guardian_explain(tx, model_path="./does_not_exist.json")
    out2 = build_guardian_explain(tx, model_path="./does_not_exist.json")

    assert out1["ok"] is True
    assert out1["suggestions"] == out2["suggestions"]
    assert 2 <= len(out1["reasons"]) <= 4
    assert len(out1["suggestions"]) == 4
    assert out1["fee_multiplier"] >= 1.0


def test_guardian_explain_returns_safe_reason_bounds():
    out = build_guardian_explain(
        {
            "amount": 1000,
            "fee": 5000,
            "outputs": 1,
            "memo": "ok",
            "to_addr": "alice",
            "burst_score": 0.0,
        },
        model_path=None,
    )

    assert out["ok"] is True
    assert 1 <= len(out["reasons"]) <= 4
    assert all("private" not in r.lower() for r in out["reasons"])
