from __future__ import annotations
import json
import os
import shlex
import subprocess
import time
from typing import Dict, Optional
from .remote_trainer import RemoteTrainer, JobConfig, JobStatus

class SshDockerTrainer(RemoteTrainer):
    def __init__(self):
        self._jobs: Dict[str, JobConfig] = {}

    def _ssh_base(self, cfg: JobConfig) -> list[str]:
        args = ["ssh"]
        if cfg.remote_port:
            args += ["-p", str(cfg.remote_port)]
        if cfg.ssh_key_path:
            args += ["-i", cfg.ssh_key_path]
        args += [f"{cfg.remote_user}@{cfg.remote_host}"]
        return args

    def _scp_base(self, cfg: JobConfig) -> list[str]:
        args = ["scp", "-r"]
        if cfg.remote_port:
            args += ["-P", str(cfg.remote_port)]
        if cfg.ssh_key_path:
            args += ["-i", cfg.ssh_key_path]
        return args

    def submit_job(self, cfg: JobConfig) -> str:
        job_name = cfg.job_name or f"qcraft_ssh_{int(time.time())}"
        remote_base = cfg.remote_base_dir or "~/qcraft_remote"
        remote_configs = f"{remote_base}/configs"
        remote_artifacts = f"{remote_base}/artifacts/{job_name}"
        mkdir_cmd = f"mkdir -p {shlex.quote(remote_configs)} {shlex.quote(remote_artifacts)}"
        subprocess.run(self._ssh_base(cfg) + [mkdir_cmd], check=True)
        if cfg.local_config_dir and os.path.isdir(cfg.local_config_dir):
            src = os.path.join(cfg.local_config_dir, "")
            dst = f"{cfg.remote_user}@{cfg.remote_host}:{remote_configs}/"
            scp_cmd = self._scp_base(cfg) + [src, dst]
            subprocess.run(scp_cmd, check=True)
        image = cfg.image_uri
        if not image:
            raise ValueError("image_uri is required for SSH Docker trainer")
        args = [
            "python", "-m", "cloud.training_entrypoint",
            "--module", cfg.module,
            "--config_overrides", json.dumps(cfg.config_overrides or {}),
        ]
        if cfg.episodes:
            args += ["--episodes", str(int(cfg.episodes))]
        if cfg.vec_strategy:
            args += ["--vec_strategy", cfg.vec_strategy]
        if cfg.n_envs:
            args += ["--n_envs", str(int(cfg.n_envs))]
        if cfg.dataset_gcs_uri:
            args += ["--dataset_gcs_uri", cfg.dataset_gcs_uri]
        if cfg.procedural_cfg:
            args += ["--procedural_cfg", json.dumps(cfg.procedural_cfg)]
        docker_cmd = [
            "docker", "run", "-d", "--rm", "--gpus", "all",
            "--name", job_name,
            "-v", f"{remote_configs}:/workspace/qcraft/configs",
            "-v", f"{remote_artifacts}:/workspace/qcraft/outputs",
            image,
        ] + args
        remote_cmd = " ".join(shlex.quote(x) for x in docker_cmd)
        subprocess.run(self._ssh_base(cfg) + [remote_cmd], check=True)
        self._jobs[job_name] = cfg
        return job_name

    def get_status(self, job_id: str) -> JobStatus:
        cfg = self._jobs.get(job_id)
        if not cfg:
            return JobStatus(job_id=job_id, state="NOT_FOUND")
        inspect_cmd = ["docker", "inspect", "-f", "{{.State.Status}}", job_id]
        remote_cmd = " ".join(shlex.quote(x) for x in inspect_cmd)
        try:
            out = subprocess.check_output(self._ssh_base(cfg) + [remote_cmd], stderr=subprocess.STDOUT, text=True).strip()
            raw = (out or "").strip().lower()
            # Map docker states to generic states expected by UI
            if raw == "running":
                state = "RUNNING"
            elif raw == "exited":
                state = "SUCCEEDED"
            elif raw == "created":
                state = "SUBMITTED"
            elif raw in ("dead", "removing", "restarting"):
                state = "FAILED"
            else:
                state = raw.upper() or "UNKNOWN"
        except subprocess.CalledProcessError as e:
            msg = e.output.strip() if isinstance(e.output, str) else str(e)
            return JobStatus(job_id=job_id, state="NOT_FOUND", message=msg)
        remote_base = cfg.remote_base_dir or "~/qcraft_remote"
        artifacts_uri = f"ssh://{cfg.remote_user}@{cfg.remote_host}:{cfg.remote_port or 22}{remote_base}/artifacts/{job_id}"
        return JobStatus(job_id=job_id, state=state, artifacts_uri=artifacts_uri)

    def cancel_job(self, job_id: str) -> None:
        cfg = self._jobs.get(job_id)
        if not cfg:
            return
        stop_cmd = ["docker", "stop", job_id]
        remote_cmd = " ".join(shlex.quote(x) for x in stop_cmd)
        subprocess.run(self._ssh_base(cfg) + [remote_cmd], check=False)

    def download_artifacts(self, job_id: str, dest_path: str) -> Optional[str]:
        cfg = self._jobs.get(job_id)
        if not cfg:
            return None
        os.makedirs(dest_path, exist_ok=True)
        remote_base = cfg.remote_base_dir or "~/qcraft_remote"
        remote_path = f"{cfg.remote_user}@{cfg.remote_host}:{remote_base}/artifacts/{job_id}"
        scp_cmd = self._scp_base(cfg) + [remote_path, dest_path]
        subprocess.run(scp_cmd, check=True)
        return os.path.join(dest_path, job_id)

    def upload_configs(self, local_dir: str, cfg: JobConfig) -> None:
        if not local_dir or not os.path.isdir(local_dir):
            return
        remote_base = cfg.remote_base_dir or "~/qcraft_remote"
        remote_configs = f"{remote_base}/configs"
        mkdir_cmd = f"mkdir -p {shlex.quote(remote_configs)}"
        subprocess.run(self._ssh_base(cfg) + [mkdir_cmd], check=True)
        src = os.path.join(local_dir, "")
        dst = f"{cfg.remote_user}@{cfg.remote_host}:{remote_configs}/"
        scp_cmd = self._scp_base(cfg) + [src, dst]
        subprocess.run(scp_cmd, check=True)

    def download_configs(self, local_dir: str, cfg: JobConfig) -> Optional[str]:
        if not local_dir:
            return None
        os.makedirs(local_dir, exist_ok=True)
        remote_base = cfg.remote_base_dir or "~/qcraft_remote"
        remote_configs = f"{cfg.remote_user}@{cfg.remote_host}:{remote_base}/configs"
        scp_cmd = self._scp_base(cfg) + [remote_configs, local_dir]
        try:
            subprocess.run(scp_cmd, check=True)
            return os.path.join(local_dir, "configs")
        except subprocess.CalledProcessError:
            return None
