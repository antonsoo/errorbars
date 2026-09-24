"""errorbars: statistical rigor for LLM eval results."""

from errorbars.stats import (
    ClusterDiagnostics,
    MeanEstimate,
    bootstrap_ci,
    cluster_robust_se,
    design_effect,
    intraclass_correlation,
    mean_ci_clt,
    wilson_ci,
    within_between_variance,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "MeanEstimate",
    "ClusterDiagnostics",
    "mean_ci_clt",
    "wilson_ci",
    "bootstrap_ci",
    "cluster_robust_se",
    "intraclass_correlation",
    "design_effect",
    "within_between_variance",
]
