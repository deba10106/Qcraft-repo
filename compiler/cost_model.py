# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

"""
Dual-Path cost model for QCraft compiler layer.

Provides estimates for two strategies:
  A) decompose → encode → map
  B) encode → synthesize → decompose → map

Estimates expected error and latency using device error rates, connectivity, and circuit structure.
No external service required; integrates directly with Orchestrator/WorkflowBridge.
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple
import math

from hardware_abstraction.device_abstraction import DeviceAbstraction
from configuration_management.config_manager import ConfigManager

class DualPathCostModel:
    """Enterprise-grade heuristic-analytic dual-path cost model.

    Uses device profile and circuit features to estimate expected error and latency
    for the two principal compilation strategies. Designed to be deterministic and reproducible
    given fixed inputs.
    """
    def __init__(self, device_profile: Dict[str, Any] | None = None):
        # Load compiler defaults from YAML (configurable)
        ConfigManager.load_registry()
        # Validate schema if available; non-fatal on failure
        try:
            ConfigManager.validate_config('compiler')
        except Exception:
            pass
        compiler_cfg = ConfigManager.get_config('compiler') or {}
        cm_defaults = (compiler_cfg.get('cost_model') or {})
        def_err = cm_defaults.get('default_error_rates', {})
        def_lat = cm_defaults.get('latency_ns', {})

        self.device_profile = device_profile or {}
        # Extract basic error rates; prefer device profile, else YAML, else conservative fallback
        self.cx_error = self._get_nested(self.device_profile, ["gate_error_rates", "cx"], default=float(def_err.get('cx', 0.01)))
        self.single_error = self._get_nested(self.device_profile, ["gate_error_rates", "x"], default=float(def_err.get('single', 0.001)))
        # YAML default for readout error is used if device doesn't provide a mean
        self.readout_error = self._infer_readout_error(self.device_profile) if self._infer_readout_error(self.device_profile) is not None else float(def_err.get('readout', 0.02))
        self.max_qubits = int(self.device_profile.get("max_qubits", 0))
        self.connectivity = self.device_profile.get("qubit_connectivity") or self.device_profile.get("connectivity") or {}
        # Latency parameters (ns per layer)
        self.twoq_layer_ns = int(def_lat.get('twoq_layer', 200))
        self.oneq_layer_ns = int(def_lat.get('oneq_layer', 20))

    def _get_nested(self, d: Dict[str, Any], path: List[str], default=None):
        cur = d
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def _infer_readout_error(self, device: Dict[str, Any]) -> float | None:
        qp = device.get("qubit_properties", {})
        if isinstance(qp, dict) and qp:
            vals = []
            for v in qp.values():
                if isinstance(v, dict) and "readout_error" in v:
                    vals.append(float(v["readout_error"]))
            if vals:
                return sum(vals) / len(vals)
        return None

    def _circuit_features(self, circuit: Dict[str, Any]) -> Dict[str, int]:
        twoq = 0
        oneq = 0
        measure = 0
        depth_proxy = 0
        last_layer_for = {}
        for gate in circuit.get("gates", []):
            name = gate.get("name","").upper()
            qs = gate.get("qubits", [])
            if len(qs) >= 2:
                twoq += 1
            elif len(qs) == 1:
                if name == "MEASURE":
                    measure += 1
                else:
                    oneq += 1
            # naive depth proxy
            cur_layer = 0
            for q in qs:
                cur_layer = max(cur_layer, last_layer_for.get(q, 0))
            cur_layer += 1
            for q in qs:
                last_layer_for[q] = cur_layer
            depth_proxy = max(depth_proxy, cur_layer)
        return {"twoq": twoq, "oneq": oneq, "measure": measure, "depth": depth_proxy}

    def _avg_shortest_path(self, logical_qubits: int) -> float:
        # If connectivity is empty, assume dense (path length ~1)
        if not isinstance(self.connectivity, dict) or not self.connectivity:
            return 1.0
        # crude average of shortest paths among first N qubits
        # (enterprise-grade would use full graph APSP; this is acceptable and deterministic)
        nodes = sorted(list(self.connectivity.keys()))
        nodes = [n for n in nodes if isinstance(n, int)]
        if len(nodes) <= 1:
            return 1.0
        import collections
        def sp(src: int, dst: int) -> int:
            if src == dst:
                return 0
            q = collections.deque([(src,0)])
            seen = {src}
            while q:
                cur,d = q.popleft()
                for nb in self.connectivity.get(cur, []):
                    if nb == dst:
                        return d+1
                    if nb not in seen:
                        seen.add(nb)
                        q.append((nb,d+1))
            return max(len(nodes)//2, 1)
        m = min(len(nodes), max(logical_qubits, 2))
        total = 0
        cnt = 0
        for i in range(m):
            for j in range(i+1, m):
                total += sp(nodes[i], nodes[j])
                cnt += 1
        return (total / cnt) if cnt else 1.0

    def _swap_overhead(self, twoq_gates: int, logical_qubits: int) -> int:
        # estimate swaps = twoq_gates * (avg path length - 1)
        spl = self._avg_shortest_path(logical_qubits)
        overhead = max(0.0, spl - 1.0)
        return int(round(twoq_gates * overhead))

    def _expected_error(self, feats: Dict[str,int], swaps: int) -> float:
        # basic multiplicative error model aggregated to 1 - prod(1-e)
        total_twoq = feats["twoq"] + swaps
        total_oneq = feats["oneq"] + swaps  # swaps add 1q overhead too (routing)
        p_no_error = (1 - self.cx_error) ** max(total_twoq, 0) * (1 - self.single_error) ** max(total_oneq, 0) * (1 - self.readout_error) ** max(feats["measure"], 0)
        return 1.0 - p_no_error

    def _latency_ns(self, feats: Dict[str,int], swaps: int) -> int:
        # YAML-configurable latency; swaps add 2 layers worth of two-qubit latency
        return int(self.twoq_layer_ns * (feats["depth"] + 2 * max(swaps,0)) + self.oneq_layer_ns * feats["oneq"]) 

    def estimate_path_A(self, circuit: Dict[str, Any]) -> Dict[str, Any]:
        """decompose→encode→map"""
        feats = self._circuit_features(circuit)
        logical_qubits = len(circuit.get("qubits", [])) or 1
        swaps = self._swap_overhead(feats["twoq"], logical_qubits)
        exp_err = self._expected_error(feats, swaps)
        lat = self._latency_ns(feats, swaps)
        return {"strategy":"A","expected_error": exp_err, "latency_ns": lat, "est_swaps": swaps, "features": feats}

    def estimate_path_B(self, circuit: Dict[str, Any]) -> Dict[str, Any]:
        """encode→synthesize→decompose→map"""
        feats = self._circuit_features(circuit)
        logical_qubits = len(circuit.get("qubits", [])) or 1
        # encoded gates change structure: increase twoq by 30%, depth by 25%
        enc_twoq = int(round(feats["twoq"] * 1.3))
        enc_depth = int(round(feats["depth"] * 1.25))
        enc_feats = {**feats, "twoq": enc_twoq, "depth": enc_depth}
        swaps = self._swap_overhead(enc_twoq, logical_qubits)
        exp_err = self._expected_error(enc_feats, swaps)
        lat = self._latency_ns(enc_feats, swaps)
        return {"strategy":"B","expected_error": exp_err, "latency_ns": lat, "est_swaps": swaps, "features": enc_feats}
