"""Generate the text fixtures used by the receipt tests.

Run from the repo root:  python tests/fixtures/make_fixtures.py

The fixtures are synthetic on purpose. A real paper would drag licensing questions
into the repo, and the extractor only depends on *structure* — headings, a table
caption, hyperparameter statements, a limitation sentence — not on meaning.
"""

import os
import pathlib

PAGE = "\f"

TITLE = "Dense Reconstruction of Degraded Scenes from Sparse Views"


def para(topic, n, suffix=""):
    return (
        "We study %s and report what changes when the observation model is degraded. "
        "The setting assumes %d calibrated views with overlapping coverage, and the "
        "reconstruction is optimised jointly over geometry and appearance so that both "
        "terms are updated from the same residual. Our treatment keeps the optimiser "
        "identical to the baseline and changes only the residual weighting, which lets "
        "the effect of the weighting be isolated from any other implementation detail. "
        "Every claim below is evaluated under the same protocol, and negative results "
        "are reported alongside positive ones because the failure cases are the part "
        "that transfers to other scenes. We deliberately keep the evaluation narrow: a "
        "single protocol applied to every model, with the same number of iterations and "
        "the same resolution, so that a difference in the table reflects the method and "
        "not the tuning budget. Where a baseline is known to be sensitive to one of these "
        "choices we report both settings and mark which one we treat as primary.%s"
        % (topic, n, suffix)
    )


def build_full():
    parts = []

    # Page 1 — title and abstract
    parts.append(
        "\n".join(
            [
                TITLE,
                "A. Author, B. Author, C. Author",
                "",
                "Abstract",
                "We present a dense reconstruction method for scenes observed under "
                "degraded imaging conditions. The central observation is that the "
                "weighting between photometric and geometric residuals should depend on "
                "the estimated reliability of each pixel rather than on a global constant. "
                "We derive the weighting from a per-pixel variance proxy and integrate it "
                "into the standard differentiable rendering loop, adding no trainable "
                "parameters. Experiments on three datasets show consistent improvement in "
                "the low-visibility regime while leaving the clean regime essentially "
                "unchanged. Code and configurations are released with the paper.",
            ]
        )
    )

    # Page 2 — Introduction
    parts.append(
        "\n".join(
            [
                "I. Introduction",
                para("reconstruction under degraded imaging conditions", 8),
                "",
                para("the interaction between appearance and geometry in the optimiser", 12),
                "",
                para("why a global residual weight is the wrong abstraction", 15),
            ]
        )
    )

    # Page 3 — Related work
    parts.append(
        "\n".join(
            [
                "II. Related Work",
                para("prior work on differentiable rendering for scene reconstruction", 6),
                "",
                para("hand-crafted reliability heuristics used in earlier pipelines", 9),
                "",
                "Table I",
                "Qualitative comparison of residual weighting strategies across the three "
                "datasets considered in this work.",
            ]
        )
    )

    # Page 4 — Method
    parts.append(
        "\n".join(
            [
                "III. Method",
                "A. Optimisation",
                para("the joint objective and its per-pixel weighting", 10),
                "",
                para("the variance proxy and how it is estimated per iteration", 13),
                "",
                "IV. Implementation",
                "We implement the residual weighting as a small module inserted between the "
                "rasteriser and the loss. We train all models on a single RTX 4090 for "
                "30k iterations, and we use the same schedule for every baseline so that "
                "the comparison is not confounded by tuning effort. The per-pixel variance "
                "proxy is computed once per iteration from the rasteriser output, which "
                "costs less than two percent of the total iteration time.",
            ]
        )
    )

    # Page 5 — Experiments with a numeric table
    parts.append(
        "\n".join(
            [
                "V. Experiments",
                "A. Setup",
                "We set the learning rate = 1e-4 and the batch size = 4 for all models, and "
                "we fix iterations = 30000. The resolution is kept at 800 pixels on the "
                "long side. Baselines are re-run under the identical protocol; where a "
                "baseline publishes a different configuration we report both numbers and "
                "note the difference rather than silently using the stronger one.",
                "",
                "Table II",
                "Reconstruction quality on the three datasets. Values in dB.",
                "Dataset A 41.2 dB 38.7 dB 36.4 dB",
                "Dataset B 34.8 dB 33.1 dB 31.9 dB",
                "Dataset C 29.6 dB 27.4 dB 25.8 dB",
                "",
                para("the ablation over residual weighting variants", 14),
            ]
        )
    )

    # Page 6 — Limitations and conclusion
    parts.append(
        "\n".join(
            [
                "VI. Limitations",
                "We do not evaluate on real underwater sequences, so the claim that the "
                "weighting transfers to physical degradation remains untested. The "
                "variance proxy also assumes independence between neighbouring pixels, "
                "which is false near object boundaries.",
                "",
                "VII. Conclusion",
                para("what the results do and do not establish", 11),
            ]
        )
    )

    # Page 7 — References
    refs = "\n".join(
        "[%d] A. Author and B. Author. A cited work on reconstruction, number %d. "
        "In Proceedings of a Conference, 2024." % (i, i)
        for i in range(1, 21)
    )
    parts.append("References\n" + refs)

    return PAGE.join(parts)


def build_abstract_only():
    return "\n".join(
        [
            TITLE,
            "A. Author, B. Author, C. Author",
            "",
            "Abstract",
            "We present a dense reconstruction method for scenes observed under degraded "
            "imaging conditions. The central observation is that the weighting between "
            "photometric and geometric residuals should depend on the estimated "
            "reliability of each pixel rather than on a global constant. Experiments on "
            "three datasets show consistent improvement in the low-visibility regime "
            "while leaving the clean regime essentially unchanged.",
        ]
    )


def build_partial():
    """Real body, but too short and with no reference list — the 'three pages' case."""
    return PAGE.join(
        [
            "\n".join([TITLE, "", "Abstract", "Short abstract for the partial fixture."]),
            "\n".join(["I. Introduction", para("a narrow scope", 5)]),
            "\n".join(
                [
                    "II. Experiments",
                    "We set learning rate = 1e-3 and batch size = 2.",
                    "Table II",
                    "Accuracy in percent.",
                    "Method A 71.4 % 69.8 %",
                ]
            ),
        ]
    )


def main():
    here = pathlib.Path(__file__).parent
    fixtures = {
        "full_paper.txt": build_full(),
        "abstract_only.txt": build_abstract_only(),
        "partial_paper.txt": build_partial(),
    }
    for name, text in fixtures.items():
        path = here / name
        path.write_text(text, encoding="utf-8")
        print("%-20s %6d chars  %d page(s)" % (name, len(text), text.count(PAGE) + 1))


if __name__ == "__main__":
    main()
