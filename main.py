#!/usr/bin/env python3
"""brainlife.io entrypoint: multimodal registration via impact-reg-konfai.

Reads config.json directly. Resolves engine -> preset name and which venv's
impact-reg-konfai console script to invoke (elastix's LibTorch build and
FireANTs/ConvexAdam's torch 2.12 build cannot share one Python environment
-- see /opt/venv-default and /opt/venv-elastix), runs the registration, and
writes the displacement field as a NIfTI warp (neuro/transform/nifti),
alongside the moved image and the raw ITK transform.

Run under /opt/venv-default/bin/python3 (see `main`): that venv has
SimpleITK/ngff-zarr for the transform conversion below regardless of which
engine's venv the registration subprocess itself runs in.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk

VENV_BY_ENGINE = {
    "fireants": "/opt/venv-default",
    "convexadam": "/opt/venv-default",
    "elastix": "/opt/venv-elastix",
}
PRESET_BY_ENGINE = {
    "fireants": "FireANTs_SyN",
    "convexadam": "ConvexAdam_Composite",
    "elastix": "Generic_Rigid_BSpline",
}
FORMATS = ("nifti", "ome_zarr")
OUTPUT_DIR = Path("warp")
SCRATCH_DIR = Path("register_out")


def _one_of(config: dict, prefix: str) -> str:
    set_paths = [config.get(f"{prefix}_{fmt}") for fmt in FORMATS if config.get(f"{prefix}_{fmt}")]
    if len(set_paths) != 1:
        names = ", ".join(f"{prefix}_{fmt}" for fmt in FORMATS)
        raise ValueError(f"give exactly one of {names}, got {len(set_paths)}")
    return set_paths[0]


def _optional_one_of(config: dict, prefix: str) -> str | None:
    set_paths = [config.get(f"{prefix}_{fmt}") for fmt in FORMATS if config.get(f"{prefix}_{fmt}")]
    if len(set_paths) > 1:
        names = ", ".join(f"{prefix}_{fmt}" for fmt in FORMATS)
        raise ValueError(f"give at most one of {names}, got {len(set_paths)}")
    return set_paths[0] if set_paths else None


def _gpu_visible() -> bool:
    import torch

    return bool(torch.cuda.is_available())


def _copy_path(src: Path, dst: Path) -> None:
    """shutil.copy, but for a directory output (e.g. an .ome.zarr store)."""
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy(src, dst)


def _parse_extra_set(raw: str) -> list[str]:
    raw = raw.strip()
    return [token.strip() for token in raw.split(",") if token.strip()]


def _read_reference(path: str) -> sitk.Image:
    """A path (NIfTI, OME-Zarr, or anything else ITK reads) as a scalar sitk.Image."""
    p = Path(path)
    if p.is_dir() or path.endswith((".ome.zarr", ".zarr")):
        import ngff_zarr

        image = ngff_zarr.from_ngff_zarr(str(p)).images[0]
        dims = list(image.dims)
        data = np.asarray(image.data)
        for axis in [d for d in dims if d not in ("z", "y", "x")]:
            index = dims.index(axis)
            data = np.take(data, 0, axis=index)
            dims.pop(index)
        out = sitk.GetImageFromArray(data.astype(np.float32))
        out.SetSpacing([float(image.scale[a]) for a in ("x", "y", "z")])
        out.SetOrigin([float(image.translation[a]) for a in ("x", "y", "z")])
        return out
    return sitk.ReadImage(path)


def main() -> None:
    with open("config.json") as f:
        config = json.load(f)

    fixed = _one_of(config, "fixed")
    moving = _one_of(config, "moving")
    fixed_mask = _optional_one_of(config, "fixed_mask")
    moving_mask = _optional_one_of(config, "moving_mask")

    engine = str(config.get("engine", "fireants"))
    if engine not in VENV_BY_ENGINE:
        raise ValueError(f"unsupported engine {engine!r}, expected one of {sorted(VENV_BY_ENGINE)}")
    preset = str(config.get("preset_override") or "").strip() or PRESET_BY_ENGINE[engine]
    venv_bin = f"{VENV_BY_ENGINE[engine]}/bin"
    binary = f"{venv_bin}/impact-reg-konfai"
    # impact-reg-konfai shells out to `konfai-apps` by bare name (not its own
    # absolute path), so that venv's bin/ must be on PATH for the subprocess.
    env = dict(os.environ, PATH=f"{venv_bin}:{os.environ.get('PATH', '')}")

    has_gpu = _gpu_visible()
    require_cuda = bool(config.get("require_cuda", False))
    if require_cuda and not has_gpu:
        raise RuntimeError("require_cuda is set but no GPU is visible to torch")
    use_gpu = bool(config.get("gpu", True)) and has_gpu

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [binary, "register", preset, "-f", fixed, "-m", moving, "-o", str(SCRATCH_DIR)]
    if fixed_mask:
        cmd += ["--fixed-mask", fixed_mask]
    if moving_mask:
        cmd += ["--moving-mask", moving_mask]
    cmd += ["--gpu", "0"] if use_gpu else ["--cpu", str(os.cpu_count() or 1)]
    if bool(config.get("fields_only", False)):
        cmd.append("--fields-only")
    for entry in _parse_extra_set(str(config.get("extra_set", ""))):
        cmd += ["--set", entry]

    print("+ " + " ".join(shlex.quote(c) for c in cmd), flush=True)
    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        sys.exit(result.returncode)

    case_dirs = sorted(SCRATCH_DIR.glob("P*"))
    if not case_dirs:
        sys.exit(f"no case output directory (P***) found under {SCRATCH_DIR}")
    case_dir = case_dirs[0]

    transform_candidates = sorted(case_dir.glob("Transform.*"))
    if not transform_candidates:
        sys.exit(f"no Transform.* found under {case_dir}")
    transform_path = transform_candidates[0]
    _copy_path(transform_path, OUTPUT_DIR / transform_path.name)

    moved_candidates = sorted(case_dir.glob("Moved.*"))
    if moved_candidates:
        suffix = "".join(moved_candidates[0].suffixes)  # .suffix alone drops ".nii" from ".nii.gz"
        _copy_path(moved_candidates[0], OUTPUT_DIR / f"moved{suffix}")

    transform = sitk.ReadTransform(str(transform_path))
    if transform.GetName() == "DisplacementFieldTransform":
        field = sitk.DisplacementFieldTransform(transform).GetDisplacementField()
    else:
        reference = _read_reference(fixed)
        field = sitk.TransformToDisplacementField(
            transform, sitk.sitkVectorFloat64,
            reference.GetSize(), reference.GetOrigin(),
            reference.GetSpacing(), reference.GetDirection(),
        )
    sitk.WriteImage(field, str(OUTPUT_DIR / "warp.nii.gz"))


if __name__ == "__main__":
    main()
