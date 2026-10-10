"""Plot retained variance measurements; no inferred confidence bands."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent


def main() -> None:
    results = json.loads((ROOT / "results.json").read_text())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.hashsalt": "repeat-planning"})
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.9), facecolor="#f2f3ee")
    fig.subplots_adjust(top=0.76, bottom=0.21, left=0.085, right=0.975, wspace=0.3)
    for ax, dataset in zip(axes, results["public_outcomes"]["datasets"], strict=True):
        k = np.geomspace(1, 100, 200)
        baseline = dataset["pilot_accuracy"]
        ax.set_facecolor("#f2f3ee")
        ax.plot(
            k,
            dataset["pilot_between_variance"] + dataset["pilot_within_variance"] / k,
            color="#2454a6",
            linewidth=2,
            label="Pilot components: B + W/k",
        )
        ax.plot(
            k,
            baseline * (1 - baseline) / k,
            color="#ad4f34",
            linestyle="--",
            linewidth=1.8,
            label="Old assumption: p(1-p)/k",
        )
        rows = dataset["variance_by_repeat_count"]
        ax.scatter(
            [r["samples_per_question"] for r in rows],
            [r["observed_question_variance"] for r in rows],
            color="#14181c",
            s=28,
            zorder=3,
            label="Measured on check draws",
        )
        ax.set_xscale("log")
        ax.set_xticks([1, 2, 4, 10, 100], ["1", "2", "4", "10", "100"])
        ax.set_ylim(bottom=0)
        ax.set_xlabel("Answers per question (k)")
        ax.set_ylabel("Variance of question means")
        ax.set_title(dataset["source"].removeprefix("GSM8K_").removesuffix(".json"), loc="left", fontsize=12)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#d4d8d3", linewidth=0.7)
        ax.set_axisbelow(True)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.905), ncol=3, frameon=False, fontsize=9
    )
    fig.suptitle("More answers cannot remove question difficulty", x=0.085, y=0.98, ha="left", fontsize=16)
    fig.text(
        0.085,
        0.09,
        "GSM8K: 127 shared questions, 10,000 recorded answers per model per question.",
        fontsize=9,
    )
    fig.text(
        0.085,
        0.05,
        "Fit: first 5,000 draws. Check: last 5,000. Published grading labels; same questions in both halves.",
        fontsize=8.5,
        color="#50565d",
    )
    for extension in ["svg", "png"]:
        fig.savefig(
            ROOT / f"variance-floor.{extension}",
            dpi=140,
            metadata={"Date": None} if extension == "svg" else None,
        )
    plt.close(fig)


if __name__ == "__main__":
    main()
