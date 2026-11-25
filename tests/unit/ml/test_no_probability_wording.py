"""SC-009, FR-004-16: la puntuación de anomalía no se nombra ni documenta como probabilidad."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGETS = [
    *sorted((ROOT / "src/security_anomaly/ml").glob("*.py")),
    ROOT / "src/security_anomaly/schemas/ml.py",
    *sorted((ROOT / "specs/004-model-training/contracts").glob("*.md")),
]
WORD = re.compile(r"probabilidad|probability", re.IGNORECASE)
NEGATION = re.compile(r"\bno es\b|\bnunca\b|\bnot\b|\bnever\b|\bNO\b|\bsin\b", re.IGNORECASE)


def _violations(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    found = []
    for number, line in enumerate(lines):
        if WORD.search(line):
            window = " ".join(lines[max(0, number - 1) : number + 2])
            if not NEGATION.search(window):
                found.append(f"{path.name}:{number + 1}: {line.strip()}")
    return found


def test_the_probability_word_only_appears_in_disclaimers() -> None:
    assert TARGETS
    problems = [v for path in TARGETS for v in _violations(path)]
    assert not problems, problems


def test_no_identifier_is_named_like_a_probability() -> None:
    import security_anomaly.ml as ml
    from security_anomaly.schemas import ml as models

    names = [
        *dir(ml),
        *dir(models),
        *models.Score.model_fields,
        *models.EvaluationReport.model_fields,
    ]
    assert not [n for n in names if re.search(r"prob", n, re.IGNORECASE)]
