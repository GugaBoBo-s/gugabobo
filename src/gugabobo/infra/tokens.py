from __future__ import annotations

"""Lightweight, dependency-free token estimation.

We can't rely on tiktoken (extra dependency, downloads encoding files over a
flaky network), and the relay does not expose exact tokenizer behaviour. For
context-budget management we only need a conservative estimate that never
badly *under*-counts, so we err on the high side.

Heuristic: CJK characters cost ~1 token each; other characters cost ~1 token
per 4 characters (typical for English/whitespace/punctuation under BPE).
"""


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF  # CJK unified ideographs
        or 0x3400 <= code <= 0x4DBF  # CJK extension A
        or 0x3040 <= code <= 0x30FF  # hiragana + katakana
        or 0xAC00 <= code <= 0xD7A3  # hangul syllables
        or 0xFF00 <= code <= 0xFFEF  # fullwidth forms
    )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = 0
    other = 0
    for char in text:
        if _is_cjk(char):
            cjk += 1
        else:
            other += 1
    # +3 per message-like unit is added by the caller; here we only estimate
    # the raw content, rounding the non-CJK portion up.
    return cjk + (other + 3) // 4


def estimate_message_tokens(role: str, content: str) -> int:
    # Chat-format overhead per message (role markers, separators): ~4 tokens.
    return estimate_tokens(role) + estimate_tokens(content) + 4
