"""Deterministic Devanagari → Roman (Hinglish-style) transliteration.

Used by the voice pipeline to compare a Devanagari speech transcript with a
Roman-script one, and as a fallback when speech recognition returns Hindi
script. It follows common Hinglish spelling (aa, ee, oo, sh, chh) and drops the
word-final inherent vowel ("नाक" → "naak", "दर्द" → "dard"); it does not try to
handle every medial schwa deletion.
"""

from __future__ import annotations

import re

VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
          "ओ": "o", "औ": "au", "ऑ": "o", "ॲ": "e"}
MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
          "ौ": "au", "ॉ": "o", "ॅ": "e"}
CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
}
NUKTA_FORMS = {"क": "q", "ख": "kh", "ग": "g", "ज": "z", "फ": "f", "ड": "r", "ढ": "rh"}
DIGITS = {chr(0x0966 + i): str(i) for i in range(10)}
VIRAMA, NUKTA, ANUSVARA, CHANDRABINDU, VISARGA = "्", "़", "ं", "ँ", "ः"
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def has_devanagari(text: str) -> bool:
    return bool(DEVANAGARI.search(text or ""))


def _word(word: str) -> str:
    out: list[str] = []
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        if ch in CONSONANTS:
            base = CONSONANTS[ch]
            if i + 1 < n and word[i + 1] == NUKTA:
                base = NUKTA_FORMS.get(ch, base)
                i += 1
            nxt = word[i + 1] if i + 1 < n else ""
            if nxt in MATRAS:
                out.append(base + MATRAS[nxt])
                i += 2
                continue
            if nxt == VIRAMA:
                out.append(base)
                i += 2
                continue
            # inherent vowel, dropped at the end of a word (Hindi schwa deletion)
            out.append(base + ("" if i + 1 >= n else "a"))
            i += 1
            continue
        if ch in VOWELS:
            out.append(VOWELS[ch])
        elif ch in (ANUSVARA, CHANDRABINDU):
            out.append("n")
        elif ch == VISARGA:
            out.append("h")
        elif ch in DIGITS:
            out.append(DIGITS[ch])
        elif ch == NUKTA:
            pass
        else:
            out.append(ch)
        i += 1
    s = "".join(out)
    return s


def transliterate(text: str) -> str:
    """Transliterate Devanagari words; Latin-script words (English in Hinglish speech) are kept."""
    text = text.replace("।", ".").replace("॥", ".")
    return re.sub(r"[ऀ-ॿ]+", lambda m: _word(m.group(0)), text)
