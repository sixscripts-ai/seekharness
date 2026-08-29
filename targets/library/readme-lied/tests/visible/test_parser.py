from signalbox.parser import normalize_record

def test_normalize_record():
    got = normalize_record({"email": "  USER@EXAMPLE.COM ", "score": "7", "active": 1})
    assert got == {"email": "user@example.com", "score": 7, "active": True}
