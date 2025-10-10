#!/usr/bin/env bash
set -euo pipefail

# ==== Config (override via env) ====
: "${PROJECT_ID:=qcraft-474513}"
: "${REGION:=us-central1}"
: "${REPO:=qcraft}"
: "${IMAGE:=qcraft-gpu:latest}"
# Optionally override CUDA base image used by Dockerfile (must match torch CUDA index url)
: "${BASE_IMAGE:=nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04}"
# Set SKIP_PUSH=1 to build without pushing
: "${SKIP_PUSH:=}"

# ==== Paths ====
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile.gpu"
REGISTRY="${REGION}-docker.pkg.dev"
FULL_IMAGE="${REGISTRY}/${PROJECT_ID}/${REPO}/${IMAGE}"

echo "[INFO] Using PROJECT_ID=${PROJECT_ID} REGION=${REGION} REPO=${REPO} IMAGE=${IMAGE}"
echo "[INFO] Dockerfile: ${DOCKERFILE}"
echo "[INFO] Build context: ${REPO_ROOT}"
echo "[INFO] Full image: ${FULL_IMAGE}"

if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "[ERROR] Dockerfile not found at ${DOCKERFILE}" >&2
  exit 1
fi

# helpful hint if requirements.txt is missing (Dockerfile expects it at repo root)
if [[ ! -f "${REPO_ROOT}/requirements.txt" ]]; then
  echo "[WARN] ${REPO_ROOT}/requirements.txt not found. The Docker build may fail at the requirements step."
fi

echo "[INFO] Building image (BASE_IMAGE=${BASE_IMAGE})..."
docker build --pull \
  --build-arg BASE_IMAGE="${BASE_IMAGE}" \
  -f "${DOCKERFILE}" -t "${FULL_IMAGE}" "${REPO_ROOT}"

if [[ -n "${SKIP_PUSH}" ]]; then
  echo "[INFO] SKIP_PUSH is set. Skipping push. Built image tag: ${FULL_IMAGE}"
  exit 0
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "[ERROR] gcloud command not found. Install the Google Cloud CLI or set SKIP_PUSH=1 to skip pushing." >&2
  echo "        https://cloud.google.com/sdk/docs/install" >&2
  exit 127
fi

echo "[INFO] Configuring Docker to use Artifact Registry: ${REGISTRY}"
gcloud auth configure-docker "${REGISTRY}" -q

echo "[INFO] Pushing image to Artifact Registry..."
docker push "${FULL_IMAGE}"
echo "[INFO] Push complete: ${FULL_IMAGE}"