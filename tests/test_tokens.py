from gugabobo.infra.tokens import estimate_message_tokens, estimate_tokens


def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0


def test_estimate_tokens_cjk_roughly_one_per_char():
    assert estimate_tokens("你好世界") == 4


def test_estimate_tokens_ascii_roughly_quarter():
    assert estimate_tokens("abcdefgh") == 2


def test_estimate_message_tokens_includes_overhead():
    tokens = estimate_message_tokens("user", "你好")
    assert tokens >= estimate_tokens("你好") + 4


def test_longer_text_costs_more():
    short = estimate_tokens("你好")
    long = estimate_tokens("你好" * 100)
    assert long > short
