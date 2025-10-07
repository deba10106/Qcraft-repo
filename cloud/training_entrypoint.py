import argparse
import json
import os
import sys
import time
from typing import Optional, List, Dict, Any

from circuit_designer.workflow_bridge import QuantumWorkflowBridge
from hardware_abstraction.device_abstraction import DeviceAbstraction

try:
    from google.cloud import storage  # type: ignore
except Exception:
    storage = None


def log(msg: str):
    print(msg, flush=True)


def download_gcs_prefix(gcs_uri: str, local_dir: str):
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        return
    if storage is None:
        log("[WARN] google-cloud-storage not available; skipping dataset download")
        return
    os.makedirs(local_dir, exist_ok=True)
    client = storage.Client()
    path = gcs_uri[len("gs://"):]
    bucket_name, _, prefix = path.partition("/")
    bucket = client.bucket(bucket_name)
    blobs = client.list_blobs(bucket_name, prefix=prefix)
    for blob in blobs:
        rel = blob.name[len(prefix):].lstrip("/")
        if not rel:
            continue
        dst = os.path.join(local_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        blob.download_to_filename(dst)
        log(f"[INFO] downloaded {blob.name} -> {dst}")


def upload_dir_to_gcs(local_dir: str, gcs_uri: str):
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        return
    if storage is None:
        log("[WARN] google-cloud-storage not available; skipping artifact upload")
        return
    client = storage.Client()
    path = gcs_uri[len("gs://"):]
    bucket_name, _, prefix = path.partition("/")
    bucket = client.bucket(bucket_name)
    for root, _, files in os.walk(local_dir):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, local_dir)
            blob_name = f"{prefix.rstrip('/')}/{rel}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(full)
            log(f"[INFO] uploaded {full} -> gs://{bucket_name}/{blob_name}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--module", choices=["optimizer", "surface_code"], required=True)
    p.add_argument("--config_overrides", type=str, default="{}")
    p.add_argument("--episodes", type=int, default=1000)
    p.add_argument("--vec_strategy", type=str, default=None)
    p.add_argument("--n_envs", type=int, default=None)
    p.add_argument("--dataset_gcs_uri", type=str, default="")
    p.add_argument("--procedural_cfg", type=str, default="")
    p.add_argument("--artifacts_gcs_uri", type=str, default="")
    return p.parse_args()


def main():
    args = parse_args()
    overrides = json.loads(args.config_overrides or "{}")
    overrides.setdefault("rl_config", {})["num_episodes"] = int(args.episodes or 1000)
    if args.vec_strategy:
        overrides["rl_config"]["vec_strategy"] = args.vec_strategy
    if args.n_envs:
        overrides["rl_config"]["n_envs"] = int(args.n_envs)

    # Dataset handling
    dataset_local = "/opt/qcraft/dataset"
    if args.dataset_gcs_uri:
        download_gcs_prefix(args.dataset_gcs_uri, dataset_local)

    # Build training inputs
    bridge = QuantumWorkflowBridge()
    # Device info from hardware.json
    try:
        import json as _json
        with open(os.path.join(os.path.dirname(__file__), "../configs/hardware.json"), "r") as f:
            hw = _json.load(f)
        provider = hw.get("provider_name")
        device = hw.get("device_name")
    except Exception:
        # Fallback defaults
        provider, device = "ibm", "ibm_hummingbird"
    device_info = DeviceAbstraction.get_device_info(provider, device)

    # Circuits source
    circuits: Optional[List[Dict[str, Any]]] = None
    procedural = None
    circuit = {"gates": [], "qubits": list(range(2))}
    if args.dataset_gcs_uri:
        # Load JSON/YAML under dataset_local
        loaded: List[Dict[str, Any]] = []
        import glob
        import yaml
        import json as _json
        for path in glob.glob(os.path.join(dataset_local, "**/*"), recursive=True):
            if os.path.isdir(path):
                continue
            try:
                if path.lower().endswith(".json"):
                    with open(path, "r") as f:
                        data = _json.load(f)
                elif path.lower().endswith((".yaml", ".yml")):
                    with open(path, "r") as f:
                        data = yaml.safe_load(f)
                else:
                    continue
                if isinstance(data, dict) and "qubits" in data:
                    loaded.append(data)
                elif isinstance(data, list):
                    loaded.extend([d for d in data if isinstance(d, dict) and "qubits" in d])
            except Exception as e:
                log(f"[WARN] Failed to parse dataset file {path}: {e}")
        if loaded:
            circuits = loaded
            circuit = loaded[0]
    elif args.procedural_cfg:
        try:
            procedural = json.loads(args.procedural_cfg)
            circuit = {"gates": [], "qubits": list(range(max(1, int(procedural.get('qubits',{}).get('min', 2))))) }
        except Exception:
            pass

    bridge.set_agent_config(overrides)

    # Run training
    if args.module == "optimizer":
        policy_path = bridge.train_optimizer_agent(
            circuit=circuit,
            device_info=device_info,
            config_overrides=overrides,
            log_callback=lambda m, p: log(m),
            circuits=circuits,
            procedural=procedural,
        )
        log(f"[INFO] Training complete. Policy saved: {policy_path}")
    else:
        bridge.train_multi_patch_rl_agent(
            config_path=None,
            log_callback=lambda m, p=None: log(str(m)),
            config_overrides=overrides,
        )

    # Upload artifacts to GCS if requested
    artifacts_local = os.path.abspath(os.path.join("./outputs", "training_artifacts"))
    if os.path.isdir(artifacts_local) and args.artifacts_gcs_uri:
        upload_dir_to_gcs(artifacts_local, args.artifacts_gcs_uri)


if __name__ == "__main__":
    main()
