"""Trace a paired estimate back to its question cohort and observed scores.

The ledger is descriptive. Searching, sorting and inspecting it never fits a new
test or treats a selected subset as an independently chosen evaluation cohort.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from errorbars.compare import PairedComparison, SelectedInference, paired_compare, select_inference
from errorbars.io import EvalData

__all__ = ["ComparisonReview", "review_comparison"]


@dataclass(frozen=True)
class Observation:
    score: float
    sample: str | None
    source: int | None
    record: int | None
    line_start: int | None
    line_end: int | None
    metric: str | None
    filter: str | None
    question_hash: str | None
    scorer: str | None = None
    scorer_config: str | None = None


@dataclass(frozen=True)
class Question:
    question_id: str
    cluster_id: str | None
    presence: str
    mean_a: float | None
    mean_b: float | None
    difference: float | None
    observations_a: list[Observation]
    observations_b: list[Observation]
    identity: str
    scoring: str = "unavailable"


@dataclass(frozen=True)
class ClusterSensitivity:
    cluster_id: str
    n: int
    mean_difference: float
    contribution: float
    without_difference: float | None
    shift: float | None


@dataclass(frozen=True)
class ComparisonReview:
    model_a: str
    model_b: str
    confidence: float
    comparison: PairedComparison | None
    unavailable_reason: str | None
    cohort: dict[str, int | float | None]
    questions: list[Question]
    clusters: list[ClusterSensitivity]
    sources: list[str]
    warnings: list[str]

    @property
    def inference(self) -> SelectedInference | None:
        if self.comparison is None:
            return None
        shared = [q for q in self.questions if q.presence == "shared"]
        single = len(shared) == self.comparison.n and all(
            len(q.observations_a) == len(q.observations_b) == 1 for q in shared
        )
        return select_inference(self.comparison, single_observation_per_question=single)

    def as_dict(self) -> dict[str, Any]:
        inference = self.inference
        return {
            "format": "errorbars-comparison",
            "schema_version": 1,
            "model_a": self.model_a,
            "model_b": self.model_b,
            "confidence": self.confidence,
            "difference": "A - B, in original score units; higher is not necessarily better",
            "analysis_unit": "question",
            "comparison": self.comparison.as_dict() if self.comparison is not None else None,
            "inference": inference.as_dict() if inference is not None else None,
            "unavailable_reason": self.unavailable_reason,
            "cohort": self.cohort,
            "questions": [asdict(q) for q in self.questions],
            "clusters": [asdict(c) for c in self.clusters],
            "sources": [{"id": i, "name": name} for i, name in enumerate(self.sources)],
            "warnings": self.warnings,
        }


def _sum_states(values: list[float]) -> list[tuple[float, float]]:
    """Compensated prefixes, so deleting a dominant group retains small remainders.

    Subtracting its sum from an already-rounded total can erase every other
    group's contribution. Prefix/suffix states also keep this linear in groups.
    """
    states = [(0.0, 0.0)]
    total = correction = 0.0
    for value in values:
        updated = total + value
        error = (total - updated) + value if abs(total) >= abs(value) else (value - updated) + total
        correction = math.fsum((correction, error))
        total = updated
        states.append((total, correction))
    return states


def _sensitivity(questions: list[Question], mean: float | None) -> list[ClusterSensitivity]:
    groups: dict[str, list[float]] = {}
    for question in questions:
        if question.difference is not None and question.cluster_id is not None:
            groups.setdefault(question.cluster_id, []).append(question.difference)
    n = sum(len(v) for v in groups.values())
    if not groups or len(groups) == n or mean is None:
        return []
    names = sorted(groups)
    sums = [math.fsum(groups[name]) for name in names]
    before, after = _sum_states(sums), _sum_states(list(reversed(sums)))
    result = []
    for i, name in enumerate(names):
        size = len(groups[name])
        remaining = n - size
        without = math.fsum((*before[i], *after[len(names) - i - 1])) / remaining if remaining else None
        result.append(
            ClusterSensitivity(
                name, size, sums[i] / size, sums[i] / n, without,
                without - mean if without is not None else None,
            )
        )
    return sorted(result, key=lambda c: (-abs(c.shift or 0), c.cluster_id))


def review_comparison(
    data: EvalData, model_a: str, model_b: str, confidence: float = 0.95
) -> ComparisonReview:
    """Build a complete cohort ledger with an optional paired estimate.

    Unlike the numeric-only comparison, this remains useful with fewer than two
    shared questions, or just one independent cluster. In those cases inference
    is unavailable; observed means and missing questions remain inspectable.
    Known conflicting question signatures block inference. Matching ids alone
    are retained as unavailable identity evidence, not proof of equal content.
    """
    data.validate()
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    if model_a == model_b:
        raise ValueError("a comparison needs two different models")
    for model in (model_a, model_b):
        if model not in data.models():
            raise ValueError(f"no model {model!r} in the data")

    a, b = data.filter_model(model_a), data.filter_model(model_b)
    scores_a, scores_b = a.scores_by_question(), b.scores_by_question()
    common = sorted(scores_a.keys() & scores_b.keys())
    cmap = data.cluster_by_question()
    cluster_ids = [cmap[q] for q in common] if cmap else None
    n_clusters = len(set(cluster_ids)) if cluster_ids is not None else None
    clustered = cluster_ids is not None and len(set(cluster_ids)) < len(common)
    conflicts = data.pairing_conflicts(model_a, model_b)
    conflict_ids = set(conflicts)
    scoring_states = (
        data.scoring_states(model_a, model_b) if data.scoring is not None
        else dict.fromkeys(common, "unavailable")
    )
    scoring_conflicts = [q for q, state in scoring_states.items() if state == "conflicting"]
    incompatible = conflict_ids | set(scoring_conflicts)
    problem = None
    if conflicts:
        problem = (
            f"conflicting question content for {len(conflicts)} shared ids "
            f"(including {conflicts[0]!r}); inspect the source records before pairing"
        )
    elif scoring_conflicts:
        problem = (
            f"conflicting scoring rules for {len(scoring_conflicts)} shared ids "
            f"(including {scoring_conflicts[0]!r}); re-score both runs under the same "
            "scorer and parameters before comparing"
        )
    elif len(common) < 2:
        problem = (
            "fewer than 2 shared question_ids between the two models "
            f"({len(scores_a)} questions for A, {len(scores_b)} for B, {len(common)} in both)"
        )
    elif n_clusters == 1:
        problem = "need at least 2 independent clusters for a cluster-robust comparison; found 1"
    comparison = (
        paired_compare(
            [scores_a[q] for q in common], [scores_b[q] for q in common],
            clusters=cluster_ids if clustered else None, confidence=confidence,
        ) if problem is None else None
    )

    source_ids: dict[str, int] = {}

    def observations(part: EvalData) -> dict[str, list[Observation]]:
        result: dict[str, list[Observation]] = {}
        for i, (qid, score) in enumerate(zip(part.question_id, part.score, strict=True)):
            source = part.sources[i] if part.sources is not None else None
            source_id = source_ids.setdefault(source.path, len(source_ids)) if source else None
            rule = part.scoring[i] if part.scoring is not None else None
            result.setdefault(qid, []).append(Observation(
                float(score), part.sample[i] if part.sample is not None else None, source_id,
                source.record if source else None, source.line_start if source else None,
                source.line_end if source else None, source.metric if source else None,
                source.filter if source else None,
                part.question_hash[i] if part.question_hash is not None else None,
                rule.name if rule else None, rule.config_hash if rule else None,
            ))
        return result

    obs_a, obs_b = observations(a), observations(b)
    hashes_a, hashes_b = a.hashes_by_question(model_a), b.hashes_by_question(model_b)
    identity_counts = {"matching": 0, "partial": 0, "conflicting": 0, "unavailable": 0}
    questions = []
    for qid in sorted(scores_a.keys() | scores_b.keys()):
        mean_a, mean_b = scores_a.get(qid), scores_b.get(qid)
        presence = (
            "shared" if mean_a is not None and mean_b is not None
            else "only_a" if mean_b is None else "only_b"
        )
        identity = "unavailable"
        if qid in conflict_ids:
            identity = "conflicting"
            presence = "conflicting"
        elif qid in hashes_a and qid in hashes_b:
            identity = "matching" if all(
                o.question_hash is not None for o in obs_a[qid] + obs_b[qid]
            ) else "partial"
        if qid in incompatible:
            presence = "conflicting"
        if mean_a is not None and mean_b is not None:
            identity_counts[identity] += 1
        paired_difference = (
            mean_a - mean_b if mean_a is not None and mean_b is not None and qid not in incompatible else None
        )
        questions.append(Question(
            qid, cmap.get(qid), presence, mean_a, mean_b,
            paired_difference,
            obs_a.get(qid, []), obs_b.get(qid, []), identity, scoring_states.get(qid, "unavailable"),
        ))
    shared_a = math.fsum(scores_a[q] for q in common) / len(common) if common else None
    shared_b = math.fsum(scores_b[q] for q in common) / len(common) if common else None
    difference = math.fsum(scores_a[q] - scores_b[q] for q in common) / len(common) if common else None
    cohort = {
        "n_a": len(scores_a), "n_b": len(scores_b), "n_shared": len(common),
        "n_only_a": len(scores_a) - len(common), "n_only_b": len(scores_b) - len(common),
        "n_observations_a": len(a), "n_observations_b": len(b),
        "n_shared_observations_a": sum(len(obs_a[q]) for q in common),
        "n_shared_observations_b": sum(len(obs_b[q]) for q in common),
        "mean_all_a": math.fsum(scores_a.values()) / len(scores_a),
        "mean_all_b": math.fsum(scores_b.values()) / len(scores_b),
        "mean_shared_a": shared_a, "mean_shared_b": shared_b,
        "mean_difference": None if incompatible else comparison.mean_diff if comparison else difference,
        "n_clusters": n_clusters,
        **{f"n_identity_{key}": value for key, value in identity_counts.items()},
        **{f"n_scoring_{state}": sum(value == state for value in scoring_states.values())
           for state in ("matching", "conflicting", "unavailable")},
    }
    warnings = list(comparison.warnings) if comparison else [f"Inference unavailable: {problem}."]
    if cohort["n_only_a"] or cohort["n_only_b"]:
        warnings.append(
            "The runs cover different questions. Only shared questions enter the paired estimate; "
            "missing scores are not zeros. Selective missingness can bias this cohort."
        )
    if len(a) > len(scores_a) or len(b) > len(scores_b):
        warnings.append(
            "Repeated generations are averaged within each question and model first. Each shared "
            "question has equal weight; sample labels do not pair individual generations across models."
        )
    warnings.extend([
        "Pairing uses question ids and rejects conflicting known question signatures. Missing "
        "signatures leave content identity unchecked. Matching signatures are not a check on "
        "scoring rules: confirm comparable metrics and filters. Prompt variants may intentionally differ.",
        "Intervals describe sampling uncertainty under the chosen question/cluster model. "
        "An interval containing zero does not establish equivalence. No multiple-comparison "
        "adjustment is applied to this single comparison.",
    ])
    if data.scoring is not None:
        warnings.append(
            f"Recorded scoring rules: {cohort['n_scoring_matching']} matching, "
            f"{cohort['n_scoring_conflicting']} conflicting, "
            f"{cohort['n_scoring_unavailable']} unchecked shared questions. "
            "Matching names and configuration fingerprints do not verify scorer code, "
            "unrecorded defaults, external grader state or equivalent score units."
        )
    return ComparisonReview(
        model_a, model_b, confidence, comparison, problem, cohort, questions,
        _sensitivity(questions, cohort["mean_difference"]),
        [Path(path).name for path in source_ids], warnings,
    )
