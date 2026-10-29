#!/usr/bin/env python3
r"""
Helper script to organise the dataset folder and run Preprocess.py
for the NPC-TraceGuard project.

All your data files live in e:\NPC-TraceGaurd\dataset\, but Preprocess.py
expects three separate directories (kaggle emails, RBA logins, FireHOL lists).

This script:
  1. Creates temp sub-folders with symlinks (no files are copied or moved).
  2. Runs Preprocess.py with the correct flags.
  3. Outputs go to e:\NPC-TraceGaurd\dataset\processed\

Usage:
    cd e:\NPC-TraceGaurd\dataset
    python run_preprocess.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
DATASET_DIR = Path(__file__).resolve().parent          # e:\NPC-TraceGaurd\dataset
STAGING     = DATASET_DIR / "_staging"                 # temp symlink folders
OUT_DIR     = DATASET_DIR / "processed"                # final output

KAGGLE_DIR  = STAGING / "kaggle"
RBA_DIR     = STAGING / "rba"
FIREHOL_DIR = STAGING / "firehol"

# Which files belong where
EMAIL_FILES   = [
    "CEAS_08.csv", "Enron.csv", "Ling.csv",
    "Nazario.csv", "Nigerian_Fraud.csv", "SpamAssasin.csv",
    "phishing_email.csv",
]
RBA_FILES     = ["rba_synthetic_100.csv"]
FIREHOL_FILES = ["firehol_level1.netset", "firehol_level2.netset"]


def link_or_copy(src: Path, dst: Path):
    """Create a symlink if possible, else fall back to a hard link or copy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        dst.symlink_to(src)
    except OSError:
        # Symlinks may need admin on Windows; fall back to copy
        shutil.copy2(src, dst)


def setup_staging():
    """Create staging subdirectories with links to the real files."""
    # Clean previous staging
    if STAGING.exists():
        shutil.rmtree(STAGING)

    for name, target_dir in [
        (EMAIL_FILES, KAGGLE_DIR),
        (RBA_FILES, RBA_DIR),
        (FIREHOL_FILES, FIREHOL_DIR),
    ]:
        for fname in name:
            src = DATASET_DIR / fname
            if src.exists():
                link_or_copy(src, target_dir / fname)
                print(f"  Linked: {fname} -> {target_dir.name}/")
            else:
                print(f"  WARNING: {fname} not found in {DATASET_DIR}")


def run_preprocess():
    """Run Preprocess.py with the correct arguments."""
    script = DATASET_DIR / "Preprocess.py"
    cmd = [
        sys.executable, str(script),
        "--kaggle-dir",     str(KAGGLE_DIR),
        "--rba-dir",        str(RBA_DIR),
        "--firehol-dir",    str(FIREHOL_DIR),
        "--out",            str(OUT_DIR),
        "--holdout-source", "SpamAssasin",
        "--steps",          "firehol,emails,rba",
    ]
    print(f"\n{'='*60}")
    print("Running Preprocess.py ...")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=str(DATASET_DIR))
    return result.returncode


def main():
    print("="*60)
    print("NPC-TraceGuard  –  Dataset Preprocessing Runner")
    print("="*60)
    print(f"\nDataset dir : {DATASET_DIR}")
    print(f"Output dir  : {OUT_DIR}\n")

    print("Step 1: Setting up staging directories ...")
    setup_staging()

    print("\nStep 2: Running preprocessing pipeline ...")
    rc = run_preprocess()

    # Cleanup staging
    if STAGING.exists():
        shutil.rmtree(STAGING)
        print("\nCleaned up staging directory.")

    if rc == 0:
        print(f"\n{'='*60}")
        print("SUCCESS! All outputs are in:")
        print(f"  {OUT_DIR.resolve()}")
        print(f"{'='*60}")
        print("\nGenerated files:")
        if OUT_DIR.exists():
            for f in sorted(OUT_DIR.iterdir()):
                size_kb = f.stat().st_size / 1024
                print(f"  {f.name:40s} {size_kb:>10.1f} KB")
    else:
        print(f"\nPreprocess.py exited with code {rc}. Check errors above.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
