"""Text cleaning, initial heuristic flags, and comment-quality diagnostics."""
from __future__ import annotations
import html, re, unicodedata
from .constants import THEMES
_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://|www\.")

def normalize(text: str | None) -> str:
    if text is None: return ""
    s = html.unescape(str(text))
    s = _HTML_RE.sub(" ", s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return _WS_RE.sub(" ", s.lower()).strip()

# v0.3.3: menções a outros usuários identificam pessoas que não estão no estudo.
# O YouTube entrega "@handle" no texto e, no textDisplay, um link <a> para o canal.
_MENTION_LINK_RE = re.compile(r'<a\s[^>]*href="[^"]*(?:/channel/|/@|/user/|/c/)[^"]*"[^>]*>.*?</a>', re.I | re.S)
_MENTION_RE = re.compile(r"(?<![\w.])[\u200b\u200c\u200d\ufeff]*@[\w.\-\u00c0-\u024f]+", re.U)
MENTION_PLACEHOLDER = "@usuario"

def pseudonymize_mentions(text: str | None) -> str:
    """Troca menções a usuários (@handle e links para canais) por um marcador fixo."""
    if not text: return text or ""
    return _MENTION_RE.sub(MENTION_PLACEHOLDER, _MENTION_LINK_RE.sub(MENTION_PLACEHOLDER, str(text)))

def clean_text(text: str | None) -> str:
    if text is None: return ""
    return _WS_RE.sub(" ", _HTML_RE.sub(" ", html.unescape(str(text)))).strip()

def has_cjk(text: str | None) -> bool:
    return bool(text and _CJK_RE.search(text))

def classify_themes(text_clean: str) -> dict[str, bool]:
    n = normalize(text_clean)
    return {name: bool(re.search(pattern, n)) for name, pattern in THEMES.items()}

def comment_quality(text_clean: str) -> dict[str, object]:
    length = len(text_clean)
    stripped = re.sub(r"[^\w\s]", "", text_clean, flags=re.UNICODE).strip()
    emoji_only = length > 0 and not stripped
    contains_url = bool(_URL_RE.search(text_clean))
    return {
        "comment_length": length,
        "contains_url": contains_url,
        "emoji_only": emoji_only,
        "low_information": (length < 15 or emoji_only) and not contains_url,
        "topic_id": None,
    }
