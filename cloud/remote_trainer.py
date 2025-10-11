# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class JobConfig:
    module: str  # 'optimizer' or 'surface_code'
    config_overrides: Dict[str, Any]
    episodes: Optional[int] = None
    vec_strategy: Optional[str] = None
    n_envs: Optional[int] = None
    project: Optional[str] = None
    region: Optional[str] = None
    bucket: Optional[str] = None
    image_uri: Optional[str] = None
    machine_type: Optional[str] = None
    accelerator_type: Optional[str] = None
    accelerator_count: Optional[int] = None
    dataset_gcs_uri: Optional[str] = None
    procedural_cfg: Optional[Dict[str, Any]] = None
    job_name: Optional[str] = None
    timeout_seconds: Optional[int] = None
    labels: Optional[Dict[str, str]] = None


@dataclass
class JobStatus:
    job_id: str
    state: str  # 'SUBMITTED','RUNNING','SUCCEEDED','FAILED','CANCELLED'
    progress: Optional[float] = None
    artifacts_uri: Optional[str] = None
    logs_uri: Optional[str] = None
    message: Optional[str] = None


class RemoteTrainer:
    """Abstract interface for remote training backends."""
    def submit_job(self, cfg: JobConfig) -> str:
        raise NotImplementedError

    def get_status(self, job_id: str) -> JobStatus:
        raise NotImplementedError

    def cancel_job(self, job_id: str) -> None:
        raise NotImplementedError

    def download_artifacts(self, job_id: str, dest_path: str) -> Optional[str]:
        raise NotImplementedError
