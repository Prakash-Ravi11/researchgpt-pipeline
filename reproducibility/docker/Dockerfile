# =============================================================================
#  UNTESTED / NEVER BUILT
#
#  This Dockerfile has never been executed. Neither Docker nor WSL2 is installed
#  on the development machine:
#      docker --version  ->  command not found
#      wsl --status      ->  "The Windows Subsystem for Linux is not installed."
#  It has never been built, run, or parsed by a daemon. No layer here has been
#  observed to work.
#
#  It is a starting point, not a supported reproduction path. The supported path
#  is the manual one in reproducibility/README.md §4, which HAS been run end to
#  end from a clean clone.
#
#  NO GPU SUPPORT IS CLAIMED. This image is CPU-only by construction. GPU
#  passthrough via nvidia-container-toolkit was never exercised here; see the
#  "GPU-dependent runs" note at the bottom for the manual path.
# =============================================================================

# Not digest-pinned. The frozen runs used CPython 3.10.18; this tag floats within
# 3.10.x, so the patch version may differ. That does not affect what this image
# runs: the deterministic probes are stdlib-only (see below). Pin to a digest
# yourself if you need the base layer fixed too.
FROM python:3.10-slim

# --- what this image is for --------------------------------------------------
# ONLY the deterministic probes:
#     reproducibility/verify_deterministic.py   -- the 36 EXACT checks
# and, if you have the inputs for it, the test suites.
#
# It does NOT reproduce anything downstream of generation (Table 2 matrices,
# Table 3 RAGAS scores, Table 5b field coverage). Those need Ollama, qwen2.5:7b,
# a CUDA torch and a GPU. None of that is installed here.

WORKDIR /repo

# --- dependencies ------------------------------------------------------------
# verify_deterministic.py and manifests/build_manifests.py import only json, re,
# sys, hashlib and pathlib. Verified on the host under a venv created with
# `python -m venv --without-pip`: they need NOTHING from PyPI.
#
# The wheels below are for the two TEST SUITES only (15 tests + 63 unit tests).
# They are the exact set the clean-checkout test established as sufficient; the
# torch / sentence-transformers / chromadb entries in
# environment/requirements-repro.txt are NOT needed for the deterministic path
# and are deliberately not installed here.
#
# Drop this whole RUN layer if you only want the verifier.
RUN pip install --no-cache-dir \
        requests==2.34.2 \
        pymupdf==1.28.2 \
        pyyaml==6.0.3 \
        tqdm==4.70.0 \
        numpy==2.2.6 \
        pytest

# --- source ------------------------------------------------------------------
# Copy the working tree. Note what CANNOT be in it:
#   * experiments/document_evidence_pipeline/runs/  is gitignored (528 MB) and
#     absent from a clean clone. Six files under it, 97 KB total, feed 24 of the
#     36 checks. Without them the verifier reports "12 passed, 0 failed" AND
#     EXITS 0 -- a silent pass at one third coverage. See README §3.
#   * configs/config.yaml is gitignored; it holds the live API key. It must not
#     be baked into an image. Nothing in the deterministic path reads it.
COPY . /repo

# --- default: run the verifier ----------------------------------------------
# Exit code 0 is NOT sufficient evidence. Require 36 passed / 0 failed. The
# python -c line below turns the silent-pass case into a non-zero exit.
CMD ["sh", "-c", "python reproducibility/verify_deterministic.py && python -c \"import json,sys;d=json.load(open('reproducibility/verify_results.json'));print('passed',d['passed'],'failed',d['failed']);sys.exit(0 if d['passed']==36 and d['failed']==0 else 1)\""]

# =============================================================================
#  USAGE  (all of it UNVERIFIED -- no command below has ever been run)
# =============================================================================
#
#  Build:
#      docker build -f reproducibility/docker/Dockerfile -t rgp-repro .
#      # build context is the REPO ROOT, not this directory
#
#  Run the deterministic probes. Expect 12/12 and a FAILING wrapper exit, because
#  the six run artifacts are gitignored and therefore not in the image:
#      docker run --rm rgp-repro
#
#  Full 36/36 requires mounting the run artifacts from a host copy of the
#  authors' archive:
#      docker run --rm \
#        -v /host/path/to/runs:/repo/experiments/document_evidence_pipeline/runs:ro \
#        rgp-repro
#
#  Test suites:
#      docker run --rm rgp-repro sh -c "python -m pytest tests/test_pipeline.py tests/test_anchors.py -q"
#          expect: 15 passed
#      docker run --rm -w /repo/experiments/document_evidence_pipeline rgp-repro \
#        python -m tests.test_pipeline_units
#          expect: 62 passed, 1 failed  -- the failing test is
#          "content_validate accepts a big synthetic pdf (no cached pdf present)",
#          which needs a real >=20 KB PDF in pipeline/cache/ (gitignored). Mount
#          one there for 63/63. README §4.
#
#  DO NOT run reproducibility/manifests/build_manifests.py in this container. Its
#  inputs are gitignored, it exits 0 anyway, and it overwrites the shipped
#  manifests with a degraded set. README §3.
#
# =============================================================================
#  GPU-DEPENDENT RUNS -- MANUAL PATH ONLY, NO CONTAINER
# =============================================================================
#
#  The APPROXIMATE items (Table 2 matrices A/B/C, Table 3 RAGAS scores, Table 5b
#  field coverage) all pass through qwen2.5:7b. Reproducing them needs, on the
#  HOST, outside this image:
#
#    1. Ollama serving qwen2.5:7b, digest
#         845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e
#       (Q4_K_M).  ollama pull qwen2.5:7b, then compare the digest.
#    2. BAAI/bge-m3 at revision 5617a9f61b028005a4858fdac845db406aefb181,
#       passed EXPLICITLY -- the frozen harnesses resolved refs/main at run time.
#    3. torch==2.11.0+cu128 and a working CUDA driver.
#    4. pip install -r reproducibility/environment/requirements-repro.txt
#       and, for Table 3 ONLY and in a SEPARATE venv,
#       pip install -r reproducibility/environment/requirements-table3.txt
#
#  The 6 GB VRAM assumption is load-bearing, not a footnote: qwen loads at ~5.0 GB
#  and spills to CPU under contention. See README §2.4 before interpreting any
#  wall-clock or coverage number from a re-run.
#
#  Containerising that stack would mean nvidia-container-toolkit and
#  `--gpus all`. That combination has never been tried in this project, so no
#  instructions for it are given here. Adding a line that looks plausible and has
#  not been run would be worse than its absence.
# =============================================================================
