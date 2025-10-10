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

AWS_REGION=${1:-us-east-1}
REPO=${2:-qcraft-gpu}
TAG=${3:-latest}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Resolve account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO}:${TAG}"

echo "[INFO] AWS Account: ${AWS_ACCOUNT_ID}"
echo "[INFO] AWS Region:  ${AWS_REGION}"
echo "[INFO] ECR URI:     ${ECR_URI}"

# Ensure ECR repo exists
if ! aws ecr describe-repositories --repository-names "${REPO}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "[INFO] Creating ECR repository: ${REPO}"
  aws ecr create-repository --repository-name "${REPO}" --region "${AWS_REGION}" >/dev/null
fi

# Login to ECR
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# Build
echo "[INFO] Building Docker image: ${REPO}:${TAG}"
cd "$SCRIPT_DIR"
docker build -f Dockerfile.gpu -t "${REPO}:${TAG}" .

# Tag and push
echo "[INFO] Tagging ${REPO}:${TAG} as ${ECR_URI}"
docker tag "${REPO}:${TAG}" "${ECR_URI}"
echo "[INFO] Pushing ${ECR_URI}"
docker push "${ECR_URI}"

echo "[SUCCESS] Pushed ${ECR_URI}"
