from __future__ import annotations

import os
import uuid
import json
from typing import Optional, Dict, Any

from google.cloud import aiplatform
from google.api_core.exceptions import NotFound

from .remote_trainer import RemoteTrainer, JobConfig, JobStatus


class VertexAITrainer(RemoteTrainer):
    """RemoteTrainer implementation using Google Cloud Vertex AI Custom Jobs.

    Assumes a custom container image is available in Container Registry/Artifact Registry.
    Exposes a simplified API for the GUI to submit jobs and poll status.
    """

    def __init__(self, project: str, region: str, staging_bucket: Optional[str] = None):
        self.project = project
        self.region = region
        self.staging_bucket = staging_bucket
        aiplatform.init(project=project, location=region, staging_bucket=staging_bucket)

    def submit_job(self, cfg: JobConfig) -> str:
        # Build args for the container entrypoint
        args = [
            "--module", cfg.module,
            "--config_overrides", json.dumps(cfg.config_overrides or {}),
        ]
        if cfg.episodes:
            args += ["--episodes", str(cfg.episodes)]
        if cfg.vec_strategy:
            args += ["--vec_strategy", str(cfg.vec_strategy)]
        if cfg.n_envs:
            args += ["--n_envs", str(cfg.n_envs)]
        if cfg.dataset_gcs_uri:
            args += ["--dataset_gcs_uri", cfg.dataset_gcs_uri]
        if cfg.procedural_cfg:
            args += ["--procedural_cfg", json.dumps(cfg.procedural_cfg)]
        # Provide an artifacts GCS URI where the entrypoint should upload outputs
        artifacts_uri = self._default_artifacts_uri(cfg)
        args += ["--artifacts_gcs_uri", artifacts_uri]

        job_name = cfg.job_name or f"qcraft-train-{uuid.uuid4().hex[:8]}"

        worker_pool_specs = [{
            "containerSpec": {
                "imageUri": cfg.image_uri,
                "args": args,
            },
            "machineSpec": {
                "machineType": cfg.machine_type or "n1-standard-8",
                **({
                    "acceleratorType": cfg.accelerator_type or "NVIDIA_TESLA_T4",
                    "acceleratorCount": int(cfg.accelerator_count or 1),
                } if cfg.accelerator_type else {})
            },
            "replicaCount": 1,
        }]

        custom_job = aiplatform.CustomJob(
            display_name=job_name,
            worker_pool_specs=worker_pool_specs,
            base_output_dir=artifacts_uri if artifacts_uri.startswith("gs://") else None,
        )
        custom_job.run(sync=False)
        return custom_job.resource_name  # projects/../locations/../customJobs/..,

    def get_status(self, job_id: str) -> JobStatus:
        try:
            job = aiplatform.CustomJob(job_id)
            job.refresh()
        except NotFound:
            return JobStatus(job_id=job_id, state="NOT_FOUND", message="Job not found")
        state = getattr(job._gca_resource.state, "name", str(job._gca_resource.state))
        # Progress is not directly exposed; leave None or infer later from logs.
        artifacts_uri = None
        if job._gca_resource.job_detail and job._gca_resource.job_detail.events:
            # Not reliable; prefer known base_output_dir if any.
            pass
        return JobStatus(job_id=job_id, state=state, artifacts_uri=self._infer_artifacts_uri(job))

    def cancel_job(self, job_id: str) -> None:
        job = aiplatform.CustomJob(job_id)
        job.cancel()

    def download_artifacts(self, job_id: str, dest_path: str) -> Optional[str]:
        artifacts_uri = self._infer_artifacts_uri(aiplatform.CustomJob(job_id))
        if not artifacts_uri or not artifacts_uri.startswith("gs://"):
            return None
        bucket, prefix = self._split_gs_uri(artifacts_uri)
        from google.cloud import storage
        storage_client = storage.Client(project=self.project)
        b = storage_client.bucket(bucket)
        blobs = list(storage_client.list_blobs(bucket, prefix=prefix))
        os.makedirs(dest_path, exist_ok=True)
        for blob in blobs:
            rel = blob.name[len(prefix):].lstrip("/")
            local = os.path.join(dest_path, rel)
            os.makedirs(os.path.dirname(local), exist_ok=True)
            blob.download_to_filename(local)
        return dest_path

    # --- Helpers ---
    def _split_gs_uri(self, uri: str) -> tuple[str, str]:
        assert uri.startswith("gs://")
        path = uri[len("gs://"):]
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] + ("/" if not parts[1].endswith("/") else "") if len(parts) > 1 else ""
        return bucket, prefix

    def _default_artifacts_uri(self, cfg: JobConfig) -> str:
        base = cfg.bucket or self.staging_bucket
        if base and not base.startswith("gs://"):
            base = f"gs://{base}"
        if not base:
            # Fallback: Vertex AI will create a default; we may not be able to infer it
            return ""
        name = cfg.job_name or f"qcraft-train-{uuid.uuid4().hex[:8]}"
        return f"{base.rstrip('/')}/artifacts/{name}"

    def _infer_artifacts_uri(self, job: aiplatform.CustomJob) -> Optional[str]:
        # Use baseOutputDirectory if present
        try:
            bod = job._gca_resource.job_spec.base_output_directory
            if bod and bod.output_uri_prefix:
                return bod.output_uri_prefix
        except Exception:
            pass
        return None
