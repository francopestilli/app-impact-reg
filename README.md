# impact-reg

<!-- brainlife-app:begin (generated from the App manifest; edit the manifest, not this block) -->

> **Registers a moving volume to a fixed volume (NIfTI or OME-Zarr, e.g. microscopy) with impact-reg-konfai using FireANTs SyN, ConvexAdam or elastix presets, on GPU or CPU, and outputs the displacement field and moved image.**

Wraps the impact-reg-konfai CLI (IMPACT multimodal registration): the engine selects a preset from the VBoussot/ImpactReg Hugging Face repository (FireANTs_SyN rigid+affine+SyN, ConvexAdam_Composite with MIND features, or elastix Generic_Rigid_BSpline), or preset_override names any other preset. Optional fixed and moving masks restrict the similarity metric. Use it for pairwise, possibly multimodal, registration of large volumes; give exactly one format (NIfTI or OME-Zarr) per volume. Presets are downloaded at run time, so the compute node needs internet access.

| | |
|---|---|
| 📥 **Inputs** | `neuro/microscopy/nifti` (optional) ×2 · `neuro/ome-zarr` (optional) ×4 · `neuro/mask` (optional) ×2 |
| 📤 **Outputs** | `neuro/transform/nifti` |
| 🐳 **Container** | `gamorosino/app-impact-reg:0.1` |
| ⚙️ **Resources** | 4 GB memory · 5 h walltime |
| 🔗 **Run it** | [doi.org/10.25663/brainlife.app.975](https://doi.org/10.25663/brainlife.app.975) |

#### 📥 Inputs

| Input | Datatype | Required | Description |
|---|---|---|---|
| `fixed_nifti` | `neuro/microscopy/nifti` | no | Fixed/reference volume as NIfTI (alternative to fixed_ome_zarr). |
| `fixed_ome_zarr` | `neuro/ome-zarr` | no | Fixed/reference volume as an OME-Zarr store (alternative to fixed_nifti). |
| `moving_nifti` | `neuro/microscopy/nifti` | no | Moving volume as NIfTI (alternative to moving_ome_zarr). |
| `moving_ome_zarr` | `neuro/ome-zarr` | no | Moving volume as an OME-Zarr store (alternative to moving_nifti). |
| `fixed_mask_nifti` | `neuro/mask` | no | Optional fixed-space mask restricting the metric region, as NIfTI (alternative to fixed_mask_ome_zarr). Whole-image mask used if none given. |
| `fixed_mask_ome_zarr` | `neuro/ome-zarr` | no | Optional fixed-space mask as an OME-Zarr store (alternative to fixed_mask_nifti). |
| `moving_mask_nifti` | `neuro/mask` | no | Optional moving-space mask, as NIfTI (alternative to moving_mask_ome_zarr). Whole-image mask used if none given. |
| `moving_mask_ome_zarr` | `neuro/ome-zarr` | no | Optional moving-space mask as an OME-Zarr store (alternative to moving_mask_nifti). |

#### 📤 Outputs

| Output | Datatype | Description |
|---|---|---|
| `warp` | `neuro/transform/nifti` | Displacement field (moving -> fixed) as a NIfTI vector image, plus the moved image and the raw ITK Transform.h5 as extra files. |

<details>
<summary><b>⚙️ Parameters</b> (6)</summary>

| Parameter | Type | Default | Description |
|---|---|---|---|
| `engine` | string | `fireants` | Registration engine/preset: fireants (FireANTs_SyN, GPU-capable diffeomorphic SyN), convexadam (ConvexAdam_Composite, MIND features), or elastix (Generic_Rigid_BSpline). |
| `preset_override` | string |  | Exact preset app name from the VBoussot/ImpactReg Hugging Face repo (e.g. FireANTs_Affine, ConvexAdam_Coarse, MR_CT_TS), overriding the engine mapping. Empty uses the engine's default preset. |
| `gpu` | boolean | `true` | Use a GPU if one is visible to torch. Disable to force CPU even when a GPU is present. |
| `require_cuda` | boolean | `false` | Fail instead of silently falling back to CPU when no GPU is visible. |
| `fields_only` | boolean | `false` | Write the displacement field only; skip computing the moved image. |
| `extra_set` | string |  | Comma-separated NAME=VALUE pairs, each forwarded as a separate --set to impact-reg-konfai (e.g. to tune iterations or patch size). Empty means none. |

</details>

<!-- brainlife-app:end -->

Multimodal pairwise image registration via
[impact-reg-konfai](https://github.com/vboussot/ImpactLoss) (Apache-2.0),
the reusable CLI behind
[fideus-labs/impact-reg-ooc-demo](https://github.com/fideus-labs/impact-reg-ooc-demo).
Runs with or without a GPU: falls back to CPU automatically unless
`require_cuda` is set.

## Engines

`engine` selects one of three generic presets from the default
`VBoussot/ImpactReg` Hugging Face repo (auto-downloaded on first use, not
baked into the container):

- `fireants` -> `FireANTs_SyN` -- Rigid+Affine+SyN diffeomorphic, GPU-capable.
  FireANTs is licensed under the FireANTs License v1.0 (see the preset's own
  `NOTICE`).
- `convexadam` -> `ConvexAdam_Composite` -- coarse+fine ConvexAdam chained in
  one app, IMPACT/MIND features.
- `elastix` -> `Generic_Rigid_BSpline` -- rigid + BSpline via elastix.

`preset_override` (advanced) takes any other exact preset name from that
repo (e.g. `FireANTs_Affine`, `ConvexAdam_Coarse`, `MR_CT_TS`), bypassing the
`engine` mapping.

## Inputs

Provide exactly one input per volume -- whichever format it actually is:

- `fixed_nifti` / `fixed_ome_zarr` -- fixed/reference volume.
- `moving_nifti` / `moving_ome_zarr` -- moving volume.
- `fixed_mask_nifti` / `fixed_mask_ome_zarr` -- optional, restricts the
  metric region (whole-image mask used if none given).
- `moving_mask_nifti` / `moving_mask_ome_zarr` -- optional.

`impact-reg-konfai`'s own `-f`/`-m`/mask arguments read NIfTI and OME-Zarr
paths directly (confirmed by reading `impact_reg_konfai/impact_reg.py`'s
format dispatch) -- this app does not convert between them.

## Outputs

- `warp` (neuro/transform/nifti) -- `warp.nii.gz`, the displacement field
  (moving -> fixed) as a NIfTI vector image, on the fixed image's grid. Also
  includes `moved.*` (the moving image resampled onto the fixed grid, unless
  `fields_only` is set) and the raw ITK `Transform.h5` as extra files.

## Why two venvs

elastix's binary is built against LibTorch 2.8/cu128; FireANTs and
ConvexAdam need torch 2.12/cu129. These can't share one Python environment
(same reason `impact-reg-ooc-demo`'s own `pixi.toml` keeps two pixi
environments). The container has `/opt/venv-default` (FireANTs, ConvexAdam)
and `/opt/venv-elastix` (elastix); `main.py` picks the right one based on
`engine`.

## Usage

Brainlife.io: run via `braise-app-run`/`braise-app-pipeline` (once registered
with `braise-app-create`), or the web UI.

Locally (outside brainlife): copy `config.json.example` to `config.json`,
fill in real file paths, then run `./main` from this directory. `main` pulls
its own container (`singularity exec --nv docker://...`) -- no local install
needed, only Singularity itself. The `--nv` flag is a no-op when no NVIDIA
driver is present, so the same container runs CPU-only too.

Entrypoint: `main.py`

## Authors

- Gabriele Amorosino <ga24643@eid.utexas.edu>

## License

MIT, see `LICENSE`, for this app's own code (`main.py`). It orchestrates
`impact-reg-konfai` (Apache-2.0) and, depending on the chosen preset,
FireANTs (FireANTs License v1.0) or elastix -- both fetched, not vendored,
so their own licenses apply to what actually runs a given registration.
