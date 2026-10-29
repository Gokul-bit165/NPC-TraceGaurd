"""Model-input cleaning shared by training (dataset/run_preprocess_v2.py) and production (every text model wrapper).

Input is the *visible* text of an email (hidden HTML/zero-width text is stripped earlier by the app's sanitiser).
Output is what the models were trained on: normalised, lower-cased, URLs / addresses / phone numbers / greeting names masked,
source-specific markers removed. Keep this file identical in behaviour to what built the training data: tests/test_text_clean.py
compares it with the rows stored in dataset/processed_v2.
"""
from __future__ import annotations

import html
import re
import unicodedata

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')]+", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

GENERIC_GREETING = set("""sir madam friend customer user student students staff all team colleague colleagues everyone beloved sirs
there member valued dear mr mrs ms dr prof professor client sir/madam sir/ madam folks guys partner winner candidate applicant
account holder owner you your the a an to from and or""".split())
RX_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]\d{3,4}[\s.-]\d{3,4}(?!\d)")
RX_GREET = re.compile(r"\b(dear|hi|hello|hey)\s+([A-Za-z][A-Za-z'-]{1,20})(?=[\s,.:;!])", re.I)
MARKERS = {
    "reply_fwd_prefix": re.compile(r"^(?:\s*(?:re|fw|fwd)\s*:\s*)+", re.I),
    "list_tag": re.compile(r"\[[^\]\[]{2,30}\]"),
    "enron_words": re.compile(r"\b(?:enron|ect|hou|ees|enron\s+communications)\b", re.I),
    "quote_marks": re.compile(r"(?:(?<=\s)|^)>+(?=\s|$)"),
    "separator_runs": re.compile(r"[_=\-*+~#]{4,}"),
    "list_footer": re.compile(r"(?:https?://\S*listinfo\S*|\S*mailing list\S*|to unsubscribe\b[^.]{0,80}\.|unsubscribe\b[^.]{0,60}\.)", re.I),
    "tokenised_url_dump": re.compile(r"\burltoken\b(?:\s+urltoken\b)+"),
}
MAX_CHARS = 3000


def normalise(text: str) -> tuple[str, int]:
    """Visible text -> model text. URLs / addresses become tokens (the URL count is returned)."""
    text = unicodedata.normalize("NFKC", html.unescape(text))
    n_urls = len(URL_RE.findall(text))
    text = URL_RE.sub(" urltoken ", text)
    text = EMAIL_RE.sub(" emailtoken ", text)
    return re.sub(r"\s+", " ", text).strip(), n_urls


def detok(s: str) -> str:
    """Undo Enron/Ling-style tokenisation (' , ' ' . ' ' ' s') so writing style cannot reveal the source."""
    s = re.sub(r"\s+([,.;:!?%)\]])", r"\1", s)
    s = re.sub(r"([(\[$])\s+", r"\1", s)
    s = re.sub(r"\s+'\s*(s|t|re|ve|ll|d|m)\b", r"'\1", s)
    s = re.sub(r"\s+-\s+", " - ", s)
    return re.sub(r"\s+", " ", s).strip()


def trim(s: str, n: int = MAX_CHARS) -> str:
    return s if len(s) <= n else s[: int(n * 0.8)] + " " + s[-int(n * 0.2):]


def clean_visible(visible: str, counts: dict | None = None, src: str = "") -> tuple[str, int, int, int]:
    """Returns (model_text, n_urls, n_phone_numbers_masked, greeting_name_masked 0/1). `counts` collects marker statistics when given."""
    txt, n_urls = normalise(visible)
    for name, rx in MARKERS.items():
        new = rx.sub(" ", txt)
        if new != txt:
            if counts is not None:
                counts.setdefault(src, {}).setdefault(name, 0)
                counts[src][name] += 1
            txt = new
    txt = detok(txt)
    n_phone = len(RX_PHONE.findall(txt))
    txt = RX_PHONE.sub(" phonetoken ", txt)

    def _greet(m):
        return m.group(0) if m.group(2).lower() in GENERIC_GREETING else f"{m.group(1)} nametoken"
    new = RX_GREET.sub(_greet, txt)
    n_name = int(new != txt)
    txt = re.sub(r"\s+", " ", new).strip().lower()
    return txt, n_urls, n_phone, n_name


def model_text(visible: str) -> str:
    """Production entry point: visible email text -> exactly what the models were trained on."""
    return trim(clean_visible(visible or "")[0])
