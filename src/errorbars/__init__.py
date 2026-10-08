"""errorbars: statistical rigor for LLM eval results."""

from errorbars.inputs import load_inputs
from errorbars.stats import (
    ClusterDiagnostics,
    MeanEstimate,
    bootstrap_ci,
    cluster_degrees_of_freedom,
    cluster_robust_se,
    design_effect,
    intraclass_correlation,
    mean_ci_clt,
    wilson_ci,
    within_between_variance,
)

__version__ = "0.2.4"

__all__ = [
    "__version__",
    "load_inputs",
    "MeanEstimate",
    "ClusterDiagnostics",
    "mean_ci_clt",
    "wilson_ci",
    "bootstrap_ci",
    "cluster_robust_se",
    "cluster_degrees_of_freedom",
    "intraclass_correlation",
    "design_effect",
    "within_between_variance",
]
