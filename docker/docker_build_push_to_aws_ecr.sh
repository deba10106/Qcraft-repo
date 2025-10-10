#!/usr/bin/env bash
set -euo pipefail

# Build and push the QCraft GPU training image to AWS ECR.
# Usage: (from anywhere)
#   ./docker/docker_build_push_to_aws_ecr.sh [AWS_REGION] [REPO] [TAG]
# Examples:
#   ./docker/docker_build_push_to_aws_ecr.sh us-east-1 qcraft-gpu latest
#
# The resulting Image URI will be:
#   <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<REPO>:<TAG>
#
# Notes:
# - Requires AWS CLI v2, Docker, and permissions for ECR (Describe/Create repo, Login, Push).
# - Uses the same Dockerfile as GCP: docker/Dockerfile.gpu
# - The image entrypoint is handled by the SageMaker trainer (cloud.sagemaker_trainer.SageMakerTrainer).

# Allow CLI args or env overrides
AWS_REGION=${1:-${AWS_REGION:-us-east-1}}
REPO=${2:-${REPO:-qcraft-gpu}}
TAG=${3:-${TAG:-latest}}
# Optionally override CUDA base image used by Dockerfile
: "${BASE_IMAGE:=nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04}"
# Set SKIP_PUSH=1 to build without pushing
: "${SKIP_PUSH:=}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile.gpu"

if [[ ! -f "${DOCKERFILE}" ]]; then
  echo "[ERROR] Dockerfile not found at ${DOCKERFILE}" >&2
  exit 1
fi

if [[ ! -f "${REPO_ROOT}/requirements.txt" ]]; then
  echo "[WARN] ${REPO_ROOT}/requirements.txt not found. The Docker build may fail at the requirements step."
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "[ERROR] aws CLI not found. Install AWS CLI v2: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" >&2
  exit 127
fi

# Resolve account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO}:${TAG}"
LOCAL_TAG="${REPO}:${TAG}"

echo "[INFO] AWS Account: ${AWS_ACCOUNT_ID}"
echo "[INFO] AWS Region:  ${AWS_REGION}"
echo "[INFO] ECR URI:     ${ECR_URI}"
echo "[INFO] Dockerfile:  ${DOCKERFILE}"
echo "[INFO] Build ctx:   ${REPO_ROOT}"
echo "[INFO] BASE_IMAGE:  ${BASE_IMAGE}"

# Ensure ECR repo exists
if ! aws ecr describe-repositories --repository-names "${REPO}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "[INFO] Creating ECR repository: ${REPO}"
  aws ecr create-repository --repository-name "${REPO}" --region "${AWS_REGION}" >/dev/null
fi

echo "[INFO] Building Docker image locally: ${LOCAL_TAG}"
docker build --pull \
  --build-arg BASE_IMAGE="${BASE_IMAGE}" \
  -f "${DOCKERFILE}" -t "${LOCAL_TAG}" "${REPO_ROOT}"

if [[ -n "${SKIP_PUSH}" ]]; then
  echo "[INFO] SKIP_PUSH set. Skipping ECR login/push. Built image: ${LOCAL_TAG}"
  exit 0
fi

# Login to ECR
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Tag and push
echo "[INFO] Tagging ${LOCAL_TAG} as ${ECR_URI}"
docker tag "${LOCAL_TAG}" "${ECR_URI}"
echo "[INFO] Pushing ${ECR_URI}"
docker push "${ECR_URI}"

echo "[SUCCESS] Pushed ${ECR_URI}"
