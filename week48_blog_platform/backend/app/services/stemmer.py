"""Pure-Python Porter Stemming Algorithm and English stop-words filter."""

import re
import unicodedata
from typing import List, Set

ENGLISH_STOP_WORDS: Set[str] = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "cannot",
    "could",
    "did",
    "do",
    "does",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "its",
    "itself",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "were",
    "weren't",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "won't",
    "would",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


class PorterStemmer:
    """Implementation of Martin Porter's 1980 Stemming Algorithm."""

    def is_cons(self, word: str, i: int) -> bool:
        """Determine whether character at position i is a consonant."""
        ch = word[i]
        if ch in "aeiou":
            return False
        if ch == "y":
            if i == 0:
                return True
            return not self.is_cons(word, i - 1)
        return True

    def measure(self, word: str) -> int:
        """Calculate the measure m of word: [C](VC)^m[V]."""
        cons: List[bool] = []
        for i in range(len(word)):
            cons.append(self.is_cons(word, i))

        m_count = 0
        state = "start"
        for c in cons:
            if state in ("start", "C"):
                if not c:
                    state = "V"
            elif state == "V":
                if c:
                    m_count += 1
                    state = "C"
        return m_count

    def contains_vowel(self, word: str) -> bool:
        """Check if stem contains at least one vowel."""
        for i in range(len(word)):
            if not self.is_cons(word, i):
                return True
        return False

    def ends_double_cons(self, word: str) -> bool:
        """Check if stem ends with double consonant (e.g., -tt, -ss)."""
        if len(word) < 2:
            return False
        return word[-1] == word[-2] and self.is_cons(word, len(word) - 1)

    def cvc(self, word: str) -> bool:
        """Check if word ends in consonant-vowel-consonant, last not w, x, y."""
        if len(word) < 3:
            return False
        if (
            self.is_cons(word, len(word) - 1)
            and not self.is_cons(word, len(word) - 2)
            and self.is_cons(word, len(word) - 3)
        ):
            if word[-1] not in "wxy":
                return True
        return False

    def step1a(self, word: str) -> str:
        """Handle plural and third person singular s suffixes."""
        if word.endswith("sses"):
            return word[:-2]
        if word.endswith("ies"):
            return word[:-2]
        if word.endswith("ss"):
            return word
        if word.endswith("s"):
            return word[:-1]
        return word

    def step1b(self, word: str) -> str:
        """Handle past tense -ed and progressive -ing suffixes."""
        if word.endswith("eed"):
            stem = word[:-3]
            if self.measure(stem) > 0:
                return word[:-1]
            return word

        matched = False
        stem = ""
        if word.endswith("ed"):
            stem = word[:-2]
            if self.contains_vowel(stem):
                matched = True
        elif word.endswith("ing"):
            stem = word[:-3]
            if self.contains_vowel(stem):
                matched = True

        if matched:
            if stem.endswith("at") or stem.endswith("bl") or stem.endswith("iz"):
                return stem + "e"
            if self.ends_double_cons(stem) and not (
                stem.endswith("l") or stem.endswith("s") or stem.endswith("z")
            ):
                return stem[:-1]
            if self.measure(stem) == 1 and self.cvc(stem):
                return stem + "e"
            return stem

        return word

    def step1c(self, word: str) -> str:
        """Change terminal y to i if preceded by another vowel."""
        if word.endswith("y"):
            stem = word[:-1]
            if self.contains_vowel(stem):
                return stem + "i"
        return word

    def step2(self, word: str) -> str:
        """Map double suffixes to single suffixes if m > 0."""
        step2_map = {
            "ational": "ate",
            "tional": "tion",
            "enci": "ence",
            "anci": "ance",
            "izer": "ize",
            "abli": "able",
            "alli": "al",
            "entli": "ent",
            "eli": "e",
            "ousli": "ous",
            "ization": "ize",
            "ation": "ate",
            "ator": "ate",
            "alism": "al",
            "iveness": "ive",
            "fulness": "ful",
            "ousness": "ous",
            "aliti": "al",
            "iviti": "ive",
            "biliti": "ble",
        }
        for suffix, repl in step2_map.items():
            if word.endswith(suffix):
                stem = word[: -len(suffix)]
                if self.measure(stem) > 0:
                    return stem + repl
                return word
        return word

    def step3(self, word: str) -> str:
        """Clean suffixes like -ful, -ness, -ic if m > 0."""
        step3_map = {
            "icate": "ic",
            "ative": "",
            "alize": "al",
            "iciti": "ic",
            "ical": "ic",
            "ful": "",
            "ness": "",
        }
        for suffix, repl in step3_map.items():
            if word.endswith(suffix):
                stem = word[: -len(suffix)]
                if self.measure(stem) > 0:
                    return stem + repl
                return word
        return word

    def step4(self, word: str) -> str:
        """Remove full derivative suffixes if m > 1."""
        suffixes = [
            "al",
            "ance",
            "ence",
            "er",
            "ic",
            "able",
            "ible",
            "ant",
            "ement",
            "ment",
            "ent",
            "ou",
            "ism",
            "ate",
            "iti",
            "ous",
            "ive",
            "ize",
        ]
        for suffix in suffixes:
            if word.endswith(suffix):
                stem = word[: -len(suffix)]
                if self.measure(stem) > 1:
                    return stem
                return word

        if word.endswith("ion"):
            stem = word[:-3]
            if self.measure(stem) > 1 and len(stem) > 0:
                if stem[-1] in ("s", "t"):
                    return stem
        return word

    def step5a(self, word: str) -> str:
        """Remove final -e if m > 1 or (m == 1 and not cvc)."""
        if word.endswith("e"):
            stem = word[:-1]
            m = self.measure(stem)
            if m > 1:
                return stem
            if m == 1 and not self.cvc(stem):
                return stem
        return word

    def step5b(self, word: str) -> str:
        """Reduce double -ll to single -l if m > 1."""
        if word.endswith("ll"):
            stem = word[:-1]
            if self.measure(stem) > 1:
                return stem
        return word

    def stem(self, word: str) -> str:
        """Apply Porter stemming passes sequentially."""
        w = word.lower().strip()
        if len(w) <= 2:
            return w

        w = self.step1a(w)
        w = self.step1b(w)
        w = self.step1c(w)
        w = self.step2(w)
        w = self.step3(w)
        w = self.step4(w)
        w = self.step5a(w)
        w = self.step5b(w)
        return w


STEMMER = PorterStemmer()


def tokenize(text: str, remove_stopwords: bool = True) -> List[str]:
    """Tokenize, lowercase, strip stopwords, and stem raw input string."""
    if not text:
        return []

    # Unicode NFKD normalization to ASCII
    norm = unicodedata.normalize("NFKD", text)
    ascii_text = norm.encode("ascii", "ignore").decode("utf-8").lower()

    # Find alphanumeric tokens of length >= 2
    raw_tokens = re.findall(r"\b[a-z0-9]{2,}\b", ascii_text)

    tokens: List[str] = []
    for token in raw_tokens:
        if token.isdigit():
            continue
        if remove_stopwords and token in ENGLISH_STOP_WORDS:
            continue
        stemmed = STEMMER.stem(token) if token.isalpha() else token
        if stemmed and len(stemmed) >= 2:
            tokens.append(stemmed)

    return tokens
