# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from __future__ import annotations

from typing import Optional, Dict, Any
import os
import uuid

try:
    import boto3  # type: ignore
except Exception:
    boto3 = None

from .remote_trainer import RemoteTrainer, JobConfig, JobStatus


class SageMakerTrainer(RemoteTrainer):
    """RemoteTrainer implementation using AWS SageMaker Training Jobs.

    This is an initial minimal implementation meant to align with the
    existing Vertex AI workflow. It expects a training container image
    compatible with QCraft's `cloud/training_entrypoint.py` (you may
    need a separate Dockerfile if running in AWS).
    """

    def __init__(self, region: str, role_arn: str, s3_bucket: Optional[str] = None):
        if boto3 is None:
            raise RuntimeError("boto3 not installed. Please install boto3 to use SageMakerTrainer.")
        self.region = region
        self.role_arn = role_arn
        self.s3_bucket = s3_bucket
        self.sm = boto3.client("sagemaker", region_name=region)
        self.s3 = boto3.client("s3", region_name=region)

    def submit_job(self, cfg: JobConfig) -> str:
        job_name = cfg.job_name or f"qcraft-train-{uuid.uuid4().hex[:8]}"
        # Build container arguments
        args = [
            "--module", cfg.module,
            "--config_overrides", self._json_dumps(cfg.config_overrides or {}),
        ]
        if cfg.episodes:
            args += ["--episodes", str(cfg.episodes)]
        if cfg.vec_strategy:
            args += ["--vec_strategy", str(cfg.vec_strategy)]
        if cfg.n_envs:
            args += ["--n_envs", str(cfg.n_envs)]
        if cfg.dataset_gcs_uri:
            # Reuse field for S3 as well; accept s3:// URIs too
            args += ["--dataset_gcs_uri", cfg.dataset_gcs_uri]
        if cfg.procedural_cfg:
            args += ["--procedural_cfg", self._json_dumps(cfg.procedural_cfg)]
        # Artifacts path in S3 (reusing naming)
        artifacts_s3 = self._default_artifacts_s3_uri(cfg, job_name)
        args += ["--artifacts_gcs_uri", artifacts_s3]

        resource_config = {
            "InstanceType": cfg.machine_type or "ml.g5.xlarge",
            "InstanceCount": 1,
            "VolumeSizeInGB": 50,
        }

        input_mode = "File"
        hyperparameters = {"dummy": "1"}  # not used; args passed via command

        self.sm.create_training_job(
            TrainingJobName=job_name,
            RoleArn=self.role_arn,
            AlgorithmSpecification={
                "TrainingImage": cfg.image_uri,
                "TrainingInputMode": input_mode,
                "ContainerEntrypoint": [
                    "python", "-m", "cloud.training_entrypoint"
                ],
                "ContainerArguments": args,
            },
            OutputDataConfig={
                "S3OutputPath": artifacts_s3,
            },
            ResourceConfig=resource_config,
            StoppingCondition={
                "MaxRuntimeInSeconds": int(cfg.timeout_seconds or 86400),
            },
            Tags=[{"Key": k, "Value": v} for k, v in (cfg.labels or {}).items()],
            EnableManagedSpotTraining=False,
        )
        return job_name

    def get_status(self, job_id: str) -> JobStatus:
        try:
            resp = self.sm.describe_training_job(TrainingJobName=job_id)
        except Exception:
            return JobStatus(job_id=job_id, state="NOT_FOUND", message="Job not found")
        state = resp.get("TrainingJobStatus", "UNKNOWN")
        artifacts_uri = None
        model_artifacts = resp.get("ModelArtifacts", {})
        if model_artifacts.get("S3ModelArtifacts"):
            artifacts_uri = model_artifacts["S3ModelArtifacts"]
        else:
            # Use OutputDataConfig
            artifacts_uri = resp.get("OutputDataConfig", {}).get("S3OutputPath")
        return JobStatus(job_id=job_id, state=state, artifacts_uri=artifacts_uri)

    def cancel_job(self, job_id: str) -> None:
        try:
            self.sm.stop_training_job(TrainingJobName=job_id)
        except Exception:
            pass

    def download_artifacts(self, job_id: str, dest_path: str) -> Optional[str]:
        # Resolve artifacts location
        st = self.get_status(job_id)
        uri = st.artifacts_uri
        if not uri or not uri.startswith("s3://"):
            return None
        bucket, prefix = self._split_s3_uri(uri)
        os.makedirs(dest_path, exist_ok=True)
        paginator = self.s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                rel = key[len(prefix):].lstrip('/')
                if not rel:
                    continue
                local = os.path.join(dest_path, rel)
                os.makedirs(os.path.dirname(local), exist_ok=True)
                self.s3.download_file(bucket, key, local)
        return dest_path

    # --- Helpers ---
    def _split_s3_uri(self, uri: str) -> tuple[str, str]:
        assert uri.startswith("s3://")
        path = uri[len("s3://"):]
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] + ("/" if not parts[1].endswith("/") else "") if len(parts) > 1 else ""
        return bucket, prefix

    def _default_artifacts_s3_uri(self, cfg: JobConfig, job_name: str) -> str:
        base = cfg.bucket or self.s3_bucket
        if base and not base.startswith("s3://"):
            base = f"s3://{base}"
        if not base:
            raise ValueError("S3 bucket is required for SageMaker artifacts")
        return f"{base.rstrip('/')}/artifacts/{job_name}"

    def _json_dumps(self, obj: Any) -> str:
        import json
        return json.dumps(obj)
