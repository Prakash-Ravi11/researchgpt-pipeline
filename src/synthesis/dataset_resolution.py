"""Canonical benchmark identities for gap counting, without rewriting evidence.

Fuzzy matches target a fixed registry, never another unresolved spelling. This
avoids order-dependent, transitive merges. Similarity is unit-cost Levenshtein
``1 - distance / max_length`` (the normalized Levenshtein definition).
"""
from dataclasses import dataclass
import re
import unicodedata

MIN_SIMILARITY = 0.88

# Keep variants separate. Sources document benchmark identity, not fuzzy scores.
# Extend aliases only when a repository/benchmark author establishes equivalence.
BENCHMARKS = (
    ("HotpotQA", ("Hotpot QA", "hotpot_qa"), "https://hotpotqa.github.io/"),
    ("2WikiMultiHopQA", ("2Wiki", "2WikimQA"), "https://github.com/Alab-NII/2wikimultihop"),
    ("SQuAD", ("Stanford Question Answering Dataset", "Stanford Question Answering Dataset (SQuAD)"), "https://huggingface.co/datasets/rajpurkar/squad"),
    ("SQuAD 2.0", ("SQuAD v2", "squad_v2"), "https://huggingface.co/datasets/rajpurkar/squad_v2"),
    ("Natural Questions", ("NQ", "NQDataset"), "https://huggingface.co/datasets/google-research-datasets/natural_questions"),
    ("NQ-open", ("NQ open",), "https://github.com/google-research/language/tree/master/language/orqa"),
    ("MS MARCO", ("MS-MARCO", "MSMARCO"), "https://huggingface.co/datasets/microsoft/ms_marco"),
    ("CUAD", ("Contract Understanding Atticus Dataset", "CUAD (Contract Understanding Atticus Dataset)"), "https://www.atticusprojectai.org/cuad"),
    ("LegalBench", (), "https://github.com/HazyResearch/legalbench"),
    ("LegalBench-RAG", (), "https://huggingface.co/datasets/awinml/legalbench-rag"),
    ("MMLU", (), "https://huggingface.co/datasets/cais/mmlu"),
    ("MMLU-Pro", (), "https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro"),
    ("MovieLens", (), "https://grouplens.org/datasets/movielens/"),
    ("TriviaQA", (), "https://nlp.cs.washington.edu/triviaqa/"),
    ("MuSiQue", (), "https://github.com/StonyBrookNLP/musique"),
    ("InfoSeek", (), "https://github.com/open-vision-language/infoseek"),
    ("E-VQA", (), "https://github.com/google-research/google-research/tree/master/encyclopedic_vqa"),
    ("HealthcareMagic", (), "https://github.com/Kent0n-Li/ChatDoctor"),
    ("HealthcareMagic-101", (), "https://github.com/Kent0n-Li/ChatDoctor"),
    ("TREC-COVID", (), "https://ir.nist.gov/covidSubmit/"),
    ("WikiText", (), "https://huggingface.co/datasets/Salesforce/wikitext"),
    ("ScienceQA", (), "https://github.com/lupantech/ScienceQA"),
    ("GLUE", (), "https://gluebenchmark.com/"),
    ("SuperGLUE", (), "https://super.gluebenchmark.com/"),
    ("ContractNLI", ("Contract Natural Language Inference",), "https://github.com/stanfordnlp/contract-nli"),
    ("PrivacyQA", ("Privacy Question Answering",), "https://github.com/AbhilashaRavichander/PrivacyQA_EMNLP"),
    ("StrategyQA", ("Commonsense Reasoning: StrategyQA",), "https://github.com/eladsegal/strategyqa"),
    ("REAL-MM-RAG", ("REAL-MM-RAG-Bench",), "https://huggingface.co/collections/ibm-research/real-mm-rag-bench"),
)

_CITATION = re.compile(
    r"\s*\((?:[^()]*(?:et\s+al\.?|&)[^()]*\b(?:19|20)\d{2}[a-z]?"
    r"|[A-Z][A-Za-z'’.-]+\s*,?\s+(?:19|20)\d{2}[a-z]?)\)\s*$", re.I)
_REF = re.compile(r"\s*\[\d+(?:\s*[,;–-]\s*\d+)*\]\s*$")
_QUALIFIERS = re.compile(
    r"\b(?:open|pro|raw|answerable|unanswerable|train|training|test|testing|"
    r"validation|dev|verified|full|distractor|large|small|base|subset|split)\b", re.I)


def _clean(label: str) -> str:
    text = unicodedata.normalize("NFKC", label).strip()
    # Strip references, not parenthesized versions, subsets, or configurations.
    previous = None
    while previous != text:
        previous, text = text, _CITATION.sub("", _REF.sub("", text)).strip()
    return re.sub(r"\s+(?:dataset|benchmark|corpus)s?\s*$", "", text, flags=re.I).strip()


def _key(text: str) -> str:
    text = text.casefold()
    return "".join(c for i, c in enumerate(text) if c.isalnum() or (
        c == "." and 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit()))


def levenshtein_similarity(left: str, right: str) -> float:
    """Unit insertion/deletion/substitution costs; no token-sort approximation."""
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    size = max(len(left), len(right))
    if len(left) < len(right):
        left, right = right, left
    row = list(range(len(right) + 1))
    for i, char in enumerate(left, 1):
        following = [i]
        for j, other in enumerate(right, 1):
            following.append(min(following[-1] + 1, row[j] + 1, row[j - 1] + (char != other)))
        row = following
    return 1.0 - row[-1] / size


def _identity_parts(text: str) -> tuple:
    return (tuple(re.findall(r"\d+(?:\.\d+)?(?:[km])?", text.casefold())),
            frozenset(m.group().casefold() for m in _QUALIFIERS.finditer(text)))


@dataclass(frozen=True)
class DatasetResolution:
    original: str
    canonical: str
    method: str
    similarity: float | None
    repository: str | None = None


class DatasetResolver:
    def __init__(self, benchmarks=BENCHMARKS, threshold: float = MIN_SIMILARITY):
        if not MIN_SIMILARITY <= threshold <= 1.0:
            raise ValueError("Dataset similarity threshold must be between 0.88 and 1.0")
        self.threshold = threshold
        self.aliases = {}
        for canonical, aliases, source in benchmarks:
            for alias in (canonical, *aliases):
                key = _key(_clean(alias))
                if key in self.aliases and self.aliases[key][0] != canonical:
                    raise ValueError(f"Ambiguous dataset alias: {alias}")
                self.aliases[key] = (canonical, _clean(alias), source)

    def resolve(self, label: str) -> DatasetResolution:
        clean = _clean(label)
        key = _key(clean)
        if key in self.aliases:
            name, _, source = self.aliases[key]
            return DatasetResolution(label, name, "alias", 1.0, source)
        # Both sides of an expanded acronym must independently identify the
        # same registered benchmark; never discard an unknown parenthesis.
        expanded = re.fullmatch(r"(.+?)\s*\(([^()]+)\)", clean)
        if expanded:
            left = self.aliases.get(_key(_clean(expanded.group(1))))
            right = self.aliases.get(_key(_clean(expanded.group(2))))
            if left and right and left[0] == right[0]:
                return DatasetResolution(label, left[0], "alias", 1.0, left[2])
        # Audit's AIME24/AIME 2024 example; editions remain separate.
        aime = re.fullmatch(r"AIME[\s_-]*(?:20)?(\d{2})", clean, re.I)
        if aime:
            year = "20" + aime.group(1)
            return DatasetResolution(label, "AIME " + year, "regex", 1.0,
                                     "https://maa.org/maa-invitational-competitions/")
        best_by_name = {}
        # Descriptions/multiple benchmarks are not a single named identity.
        if key and len(clean) <= 80 and len(clean.split()) <= 6:
            for target, (canonical, alias, source) in self.aliases.items():
                if _identity_parts(clean) != _identity_parts(alias):
                    continue
                # An added qualifier cannot disappear through a high score.
                if key.startswith(target) or target.startswith(key):
                    continue
                if min(len(key), len(target)) / max(len(key), len(target)) < self.threshold:
                    continue
                score = levenshtein_similarity(key, target)
                if score >= self.threshold and score > best_by_name.get(canonical, (0, None))[0]:
                    best_by_name[canonical] = (score, source)
        matches = sorted(best_by_name.items(), key=lambda item: (-item[1][0], item[0]))
        # Close competing identities abstain instead of choosing arbitrarily.
        if matches and (len(matches) == 1 or matches[0][1][0] - matches[1][1][0] >= 0.02):
            name, (score, source) = matches[0]
            return DatasetResolution(label, name, "levenshtein", score, source)
        return DatasetResolution(label, label.strip(), "unresolved", None)

    def resolve_many(self, labels) -> list[DatasetResolution]:
        if isinstance(labels, str):
            labels = [labels]
        return [self.resolve(s) for s in (labels or []) if isinstance(s, str) and s.strip()]


def canonical_dataset_names(labels, resolver: DatasetResolver | None = None) -> list[str]:
    resolver = resolver or DatasetResolver()
    return sorted({r.canonical for r in resolver.resolve_many(labels)})
