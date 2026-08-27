# Dense validation manuscript scaffold

This folder contains a LaTeX scaffold for the dense paddock-scale validation
report.  It is intended as a sister document to:

`/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel/paper/paper.pdf`

Compile from this folder:

```bash
latexmk -pdf dense_validation_report.tex
```

The document currently pulls figures from:

`../../analyses/unified_dense_validation/figures/`

It uses two BibTeX sources:

- the companion model paper bibliography:
  `../../../../DownscalingMoistureModel/paper/references.bib`
- local dense-validation additions:
  `references_dense_validation.bib`

The main analysis tables live under:

`../../../outputs/unified_dense_validation/`

Important source tables:

- Stage 1 overall metrics: `../../../outputs/unified_dense_validation/stage1_independent_validation/metrics_overall_by_site_model.csv`
- Stage 1 seasonal metrics: `../../../outputs/unified_dense_validation/stage1_independent_validation/metrics_by_site_model_season.csv`
- Stage 1 paired comparison: `../../../outputs/unified_dense_validation/stage1_independent_validation/paired_model_comparison_overall.csv`
- Stage 1 terrain strata: `../../../outputs/unified_dense_validation/stage1_independent_validation/notable_terrain_error_strata.csv`
- Stage 2 local calibration summary: `../../../outputs/unified_dense_validation/stage2_local_spiking/local_calibration_summary.csv`
- Stage 2 process/statistical response: `../../../outputs/unified_dense_validation/stage2_local_spiking/process_vs_statistical_responsiveness.csv`

Before publishing, resolve all LaTeX `TODO` and `Caution` markers.
