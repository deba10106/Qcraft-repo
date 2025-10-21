---

## Why Partner with Us vs. Build In‑House (Pilot)

- **Speed to capability**: A production‑grade adaptive QEC layer in 8–12 weeks vs. 12–18 months in‑house.
- **Focused specialization**: Our team is dedicated to adaptive QEC (RL/GNN) and reliability; Fujitsu teams span hardware, control, AI, and apps.
- **Neutral & modular**: Hardware‑agnostic adapters; integrates with Fujitsu’s open toolchain and A64FX simulators; no lock‑in.
- **Risk mitigation**: Pilot de‑risks approach with measurable KPIs, artifacts, and fallbacks (MWPM/BP) before allocating internal headcount.
- **Co‑development ready**: We align to FTQC (Fault‑Tolerant Quantum Computing) FY26+ milestones and hybrid AI objectives; joint roadmap and publications encouraged.

---

## Pilot Investment & Commercial Terms (Indicative)

- **Pilot duration**: 8–12 weeks (Tier 1). Team: 2–3 FTE from our side; 1–2 FTE liaisons from Fujitsu.
- **Commercials**: Fixed‑fee pilot (or 2‑week no‑cost feasibility + reduced pilot fee). Detailed quote on request.
- **IP framework**: Qcraft retains platform IP; Fujitsu retains device data and topology IP; co‑developed artifacts/benchmarks under joint ownership.
- **Deployment**: On‑prem or VPC; source‑available under pilot license; production license post‑pilot (options: annual subscription, support SLAs).
- **Post‑pilot paths**: (A) Platform license + support, (B) Co‑development agreement, (C) On‑prem perpetual with maintenance.

---

## Preliminary Results & Proof Points (Abridged)

- **Baselines**: We evaluate against MWPM (Minimum‑Weight Perfect Matching)/BP (Belief Propagation) on agreed code distances and noise models; report mean±CI, latency.
- **Simulation evidence (illustrative)**: On surface‑code simulations (d=5–7) with depolarizing p∈[1e‑3,1e‑2], adaptive RL decoders have demonstrated double‑digit logical error reductions vs. static baselines in literature; pilot will validate on Fujitsu profiles.
- **Platform maturity**: Qcraft modules (decoder studio, profiler, mapping) are available for simulator integration; an optional post‑processing error mitigation suite (ZNE, PEC, M3/readout mitigation, symmetry verification) is available for extended evaluations.
- **References**: Prior publications and open‑source contributions available on request; we propose co‑authoring a pilot whitepaper.
# QCRAFT × FUJITSU

Adaptive Quantum Error Correction for Hybrid Quantum–AI Systems

## Executive Summary

Fujitsu is building one of the world’s most complete quantum ecosystems: from a 256‑qubit superconducting platform (with 1,000 qubits targeted by FY26) to open toolchains, large‑scale simulation, and AI/LLM (large language model) infrastructure (e.g., Kozuchi, ABCI‑Q). As qubit counts scale, practical utility will be gated by reliability—specifically, robust, adaptive quantum error correction (QEC) and system‑level control.

Qcraft is an adaptable QEC platform and desktop application that delivers an AI‑driven reliability layer for superconducting (and other) modalities. Our approach blends reinforcement learning (RL) and graph neural networks (GNNs) with device‑aware modeling to:
- Learn and adapt decoders to the live noise environment.
- Optimize logical qubit yield and reduce logical error rates.
- Integrate cleanly with open toolchains and control stacks, without vendor lock‑in.

This pilot engagement outlines how Qcraft can be integrated into Fujitsu’s stack to de‑risk the path toward fault tolerance while enabling stable quantum acceleration for hybrid AI workloads (see Figure 1 for integration overview).

## Pilot at a Glance

- **[Objective]** Improve reliability and stability of hybrid AI workloads via adaptive QEC + post‑processing error mitigation.
- **[Outcomes]** Target ≥20–40% LER reduction vs MWPM/BP, 15–25% variance reduction on selected workloads, inference path <1 ms (GPU) / <5 ms (CPU). See Table 1 for a simulated illustration.
- **[Timeline]** 8–12 weeks (Tier 1).
- **[Ownership]** Qcraft (RL/QEC integration, tooling); Fujitsu (toolchain access, simulator profiles).
- **[Deliverables]** Integrated decoder layer, artifacts (checkpoints, dashboards), benchmarks, SOW deliverables below.
- **[Next Steps]** 90‑min scoping; access to simulators/profiles; kickoff in ≤2 weeks.

### Key KPIs (Targets)

| KPI | Baseline | Target | Measurement | Owner |
|---|---|---|---|---|
| Logical error rate (LER) | MWPM/BP | ≥20–40% reduction | Stim (stabilizer simulator) + PyMatching (MWPM) on Fujitsu profiles | Qcraft |
| Variance (CI width) | Current | 15–25% reduction | Repeated runs on selected kernels | Joint |
| Inference latency | Current | < 1 ms (GPU) / < 5 ms (CPU) | Decoder inference path on GPU/CPU | Qcraft |
| Stability under drift | N/A | Sustained over 8–24h | Rolling syndrome buffers; online adaption | Joint |

### Illustrative Result (Simulated example)

Conditions: surface code d=5–7; depolarizing p∈[1e‑3, 1e‑2]; Stim+PyMatching baselines; 100k shots.

Table 1. Simulated illustrative result (for discussion)

| Method | LER (mean±CI) | Variance (CI width) | Overhead |
|---|---|---|---|
| Baseline MWPM | 1.00× (ref) | 1.00× | 1.0× |
| Adaptive RL decoder | 0.72×–0.85× | 0.8×–0.9× | 1.0× |
| RL + ZNE (mitigation) | 0.60×–0.75× | 0.8×–0.9× | 3–6× shots |

Note: Values are illustrative from simulated settings; pilot will validate on Fujitsu profiles and finalize targets.

---

## As‑Is vs To‑Be Snapshot

| Category | As‑Is (typical) | To‑Be (post‑pilot target) |
|---|---|---|
| Reliability (LER) | Static MWPM/BP decoders; limited adaptation | Adaptive decoder with ≥20–40% LER reduction vs MWPM/BP |
| Variance in hybrid pipelines | High CI width; unstable throughput | 15–25% CI width reduction on selected kernels |
| Latency | Uncharacterized decoder path | <1 ms (GPU) / <5 ms (CPU) decoder inference |
| Error mitigation | Ad‑hoc or none | Structured ZNE/M3/PEC with automated sweeps and dashboards |
| Process & artifacts | Siloed, non‑reproducible | Reproducible runs; checkpoints, dashboards, KPI dossier |
| Lock‑in risk | Tightly coupled stacks | Open adapters; neutral layer; clear licensing paths |

---

## Product Suite (Clarity)

- **Qcraft (focus of this pilot)**: Adaptive QEC platform/desktop app providing decoders, noise profiling, logical mapping, and operator tooling. Integrates with open toolchains and simulators; hardware‑agnostic.
- **Post‑Processing Error Mitigation Suite (optional extension)**: Zero‑noise extrapolation (ZNE), probabilistic error cancellation (PEC), measurement/readout mitigation (M3), symmetry verification, and Clifford data regression; integrates with orchestration for automated mitigation benchmarking; not required for the QEC pilot.

## Error Mitigation Workflow (Figure 2)

Figure 2. Orchestrated error‑mitigation flow with automated sweeps
```mermaid
flowchart LR
  O[Orchestrator] --> S{Mitigation Selector}
  S -->|ZNE| ZNE[Zero-Noise Extrapolation]
  S -->|M3| M3[Readout/Measurement Mitigation]
  S -->|PEC| PEC[Probabilistic Error Cancellation]
  ZNE --> SW[Parameter Sweeper]
  M3 --> SW
  PEC --> SW
  SW --> EXE[Executor (shots/jobs)]
  EXE --> AGG[Aggregator]
  AGG --> MET[Metrics & CI]
  MET --> DB[(Dashboards)]
```

## Pilot Objectives

- **Seamless QEC integration**: Deploy an adaptive QEC layer atop Fujitsu’s superconducting stack (and simulators) to improve logical fidelity and stability.
- **Hybrid AI enablement**: Demonstrate reliable quantum subroutines for AI/optimization workloads relevant to Kozuchi/ABCI‑Q pipelines.
- **Open, modular fit**: Prove interoperability with Fujitsu’s open quantum operations toolchain and simulator ecosystem.
- **Evidence & roadmap**: Produce benchmarks, tooling, and a co‑authored roadmap toward mid‑scale FTQC.

---

## Pilot Scope and Tiers

- **Tier 1 (Core Pilot, 8–12 weeks)**
  - Integrate Qcraft decoder layer with Fujitsu simulators/open toolchain.
  - Train/evaluate RL/GNN decoder vs. MWPM/BP baselines on Fujitsu noise/topology profiles.
  - Deliver KPIs, artifacts, and roadmap. This proposal focuses on Tier 1.
- **Tier 2 (Extensions, optional)**
  - Hybrid AI demo (reliability‑hardened kernels into Kozuchi/ABCI‑Q).
  - Channel toolkit (tomography + capacity dashboards).
- **Tier 3 (Future phases)**
  - DI‑QKD feasibility, PQC migration, expanded post‑processing error‑mitigation workflows (ZNE/PEC/M3/symmetry) and calibration‑aware pipelines.

## Statement of Work (SOW)

### Scope
- **In-scope**: Adaptive decoder integration, simulator bring-up, data schemas, benchmarking, error-mitigation experiments (optional), KPI report, roadmap.
- **Out-of-scope**: Hardware control changes, firmware, new simulator development, production SLAs (beyond pilot), proprietary Fujitsu IP changes.

### Deliverables
- Integrated decoder layer with adapters to Fujitsu open toolchain and A64FX simulators.
- Artifacts: decoder checkpoints, dashboards, notebooks, benchmark dossier (PDF), container image URIs.
- Optional: Post‑processing error mitigation benchmarking pack (ZNE/PEC/M3/symmetry/CDR).

### Milestones & Acceptance
- M1 (Wk 2): Environment bring‑up; schema and adapter smoke tests passed.
- M2 (Wk 6): RL/GNN decoder trained; baseline vs MWPM/BP report (draft) with interim KPIs.
- M3 (Wk 8): Hybrid AI demo and latency/variance characterization.
- M4 (Wk 10–12): Final KPIs, robustness tests, and roadmap readout.
Acceptance for each milestone: joint review, KPI deltas vs baselines, reproducibility checks.

### RACI (abridged)

| Workstream | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Decoder design & training | Qcraft | Qcraft | Fujitsu Research/Hardware | Fujitsu Sponsors |
| Toolchain integration & adapters | Qcraft | Qcraft | Fujitsu Open Toolchain Team | Stakeholders |
| Data access & noise/topology profiles | Fujitsu | Fujitsu | Qcraft | Qcraft |
| KPI selection & acceptance reviews | Joint | Joint | Stakeholders | Sponsors |

### Assumptions & Dependencies
- Access to simulators and representative noise/topology data under NDA.
- Compute budget available for training/evaluation runs (CPU/GPU on A64FX or equivalent).
- Change control for requirements after kickoff.

## Commercials & Payment Terms (Indicative)

- **Fixed-fee pilot**: $150,000 covering 8–12 weeks, team 2–3 FTE (Qcraft) + 1–2 FTE (Fujitsu liaisons).
- **Payment milestones** (mapped to SOW):
  - M1 (Wk 2) — 20% on environment bring‑up acceptance.
  - M2 (Wk 6) — 30% on interim KPIs and baseline report.
  - M3 (Wk 8) — 30% on hybrid AI demo acceptance.
  - M4 (Wk 10–12) — 20% on final KPI dossier and roadmap readout.
- **Licensing options post‑pilot**:
  - Pilot license (source‑available; non‑commercial use; for evaluation within Fujitsu).
  - Production subscription (annual) with support SLAs.
  - On‑prem/perpetual license with maintenance and support.

## License & Support Matrix (Indicative)

| Option | Scope | Source | Use | Support & SLAs | Notes |
|---|---|---|---|---|---|
| Pilot License | Pilot evaluation in Fujitsu environment | Source‑available | Non‑commercial, internal evaluation | Email support; best‑effort bug fixes | Expires at pilot end; convertible |
| Production Subscription | Production deployments | Binaries + source escrow (option) | Commercial | SLAs (e.g., P1: 4h resp, 24h workaround; P2: 1bd) | Annual term |
| On‑prem/Perpetual | On‑prem production | Source‑available | Commercial | Maintenance + support contract | Perpetual license; annual maintenance |

---

## Why Qcraft for Fujitsu (Themes)

- **Seamless QEC for scalable acceleration**: Adaptive decoders + policy learning to track noise drift, improving logical qubit yield and time‑to‑solution as hardware scales from 256→1,000+ qubits.
- **Plug‑in modularity & interoperability**: Hardware‑agnostic APIs; integrates with open toolchains, orchestration layers, and A64FX‑backed simulators without lock‑in.
- **Stable quantum for AI workloads**: RL‑tuned QEC reduces variability for sampling, kernel methods, and combinatorial optimization—key to hybrid pipelines.
- **Risk de‑risking & collaborative roadmap**: Joint benchmarking, stress tests, and co‑designed decoders aligned to Fujitsu’s architecture and FTQC milestones.

---

## Fujitsu Context and Alignment (Tailored)

- **Hardware scaling**: 256‑qubit SC system targeting 1,000 qubits by FY26, longer‑term 10k+ horizon. Our focus: reliability layer that improves logical yield under realistic T1/T2 and crosstalk.
- **Open toolchain and simulators**: We integrate via adapters to your open orchestration stack and A64FX‑backed simulators for rapid validation before hardware enablement.
- **Hybrid AI strategy (Kozuchi, ABCI‑Q)**: We target stability for sampling/kernels/optimization subroutines to improve throughput and variance in hybrid pipelines.
- **Partnership posture**: We position as a neutral, modular add‑on complementary to existing collaborations (e.g., QuTech) and internal efforts.

## Value Mapping to Fujitsu Programs

| Deliverable | Fujitsu Stakeholder | Business Objective | Metric | Integration Point |
|---|---|---|---|---|
| Decoder layer integration | Open Toolchain Team | Reliability layer for scaling | LER reduction vs baseline | Open orchestration + simulators (A64FX) |
| Benchmark dossier | Research/Hardware Teams | Evidence for FTQC roadmap | KPI table with CI | Internal reviews; FTQC FY26 alignment |
| Hybrid AI demo | Kozuchi/ABCI‑Q | Stable subroutines for AI workloads | Variance/throughput | Hybrid pipelines |
| Error mitigation pack (opt.) | Research/Apps | Mitigation under realistic overheads | Δ metric with overhead | Orchestration sweeps |

## Technical Fit & Integration (High‑Level)

Figure 1. High‑level integration of Qcraft with Fujitsu stack
```mermaid
flowchart LR

  %% Trust boundary (on‑prem/VPC)
  subgraph TB[On‑Prem / VPC Trust Boundary]
    %% Fujitsu stack
    subgraph FJ[Fujitsu Stack]
      HW[Fujitsu HW & Control]
      OT[Open Toolchain / Orchestration]
      SIM[A64FX Simulators]
      HW --> OT
      OT <--> SIM
    end

    %% Qcraft layer
    subgraph QC[Qcraft QEC Layer]
      ORCH[Orchestrator]
      DEC[Decoder Engines\n(RL/GNN, MWPM, BP)]
      PROF[Noise Profiler & Telemetry]
      MAP[Logical Circuit Mapper]
      MIT[Post-Processing Mitigation\n(ZNE/M3/PEC)]
      LOG[(Dashboards & KPIs)]
      ART[(Artifacts: checkpoints,\nbenchmarks, images)]
      OBS[(Observability / Logs)]
      RBAC[[RBAC / Access Control]]
      SLA((Latency SLA\n<1ms GPU / <5ms CPU))
      DATALAKE[(Telemetry Lake)]
      ADPT[Adapters\n(gRPC / Python / C++)]

      %% Internal flows
      PROF --> ORCH
      ORCH --> DEC
      ORCH --> MAP
      DEC --> ORCH
      MAP --> ORCH
      ORCH --> MIT
      MIT --> ORCH
      ORCH --> LOG
      ORCH --> ART
      ORCH --> OBS
      RBAC --- ORCH
      SLA --- DEC
      DATALAKE --- PROF
    end

    %% Cross-layer integrations within boundary
    OT <--> ADPT
    SIM <--> ADPT
    ADPT <--> ORCH
  end

  %% Apps / pipelines (consumers)
  subgraph APP[Apps & Hybrid AI Pipelines]
    APPS[Kozuchi / ABCI‑Q / Workloads]
  end
  ORCH --> APPS

  %% Telemetry & syndrome ingestion (dashed)
  HW -. telemetry/calibration .-> PROF
  SIM -. syndromes/shots .-> PROF
```

- **Decoder engines**: RL/GNN‑based learned decoders; baselines (MWPM, BP) for A/B testing.
- **Noise profiler**: Online drift tracking; syndrome statistics; device telemetry ingestion.
- **Logical mapper**: Patch/cell layouts, lattice surgery planning, and resource‑aware scheduling.
- **Adapters/APIs**: gRPC/Python/C++ adapters bridging open toolchain and simulators to `Qcraft`; Qiskit/Open toolchain support.
- **Observability & CI/CD**: Centralized logs/metrics into dashboards; artifacts feed CI/CD pipelines for releases.
- **Security & RBAC**: Role‑based access inside on‑prem/VPC trust boundary; NDA/governance separation for data and platform IP.
- **Telemetry lake**: Time‑series syndromes and calibrations retained for profiling and drift analysis.
- **Latency SLA**: Decoder inference target <1 ms (GPU) / <5 ms (CPU) for pilot workloads.

---

## Workstreams & Deliverables (8–12 weeks)

1) **Integration & Environment Bring‑up (Weeks 1–2)**
- Adapter to Fujitsu open toolchain and state‑vector/noise simulators (A64FX cluster).
- Data schema for syndromes, shots, calibration logs; secure ingestion.

2) **Adaptive Decoder MVP (Weeks 3–6)**
- RL/GNN decoder training on Fujitsu noise/topology profiles.
- Baseline comparison vs MWPM/BP; early logical error‑rate reduction reports.

3) **Hybrid AI Pilot (Weeks 5–8)**
- Stable quantum subroutine demo: sampling/kernels/optimization with QEC on.
- Latency/variance characterization for AI pipelines (Kozuchi/ABCI‑Q alignment).

4) **Benchmarking & Roadmap (Weeks 8–12)**
- Stress tests across drift scenarios, duty cycles, and qubit scales.
- Final pilot report: KPIs, architecture notes, and scale‑up plan to mid‑scale FTQC.

**Pilot Deliverables**
- Running Qcraft instance integrated with Fujitsu toolchain/sim.
- Decoder artifacts (checkpoints), telemetry dashboards, and reproducible notebooks.
- Benchmark dossier (PDF) + co‑presented readout to Fujitsu stakeholders.

---

## Success Metrics (KPIs)

- **Logical reliability**: Target ≥20–40% reduction in logical error rate vs. baseline MWPM/BP on agreed code distance and Fujitsu noise models; conservative ≥10–20%.
- **Yield & overhead**: Improved logical yield at fixed physical budget; T‑count/T‑depth and 2q‑counts within agreed thresholds.
- **Stability under drift**: Sustained performance across calibration windows (e.g., 8–24h) with online adaptation.
- **Hybrid AI throughput**: Reduced variance and improved time‑to‑solution for selected kernels; report mean±CI and latency.
- **Integration quality**: Clean API fit; CI + artifacts; zero lock‑in. All KPIs to be baselined and co‑signed at kickoff.

---

- **Academic RL decoders**: Demonstrate promise but rarely production‑integrated into toolchains; limited ops hardening.
- **Open decoders (PyMatching/Stim)**: Excellent baselines (MWPM) but static. Our differentiation: adaptive RL/GNN with production APIs and open integration.
---

## Custom Software Stacks We Can Build With Fujitsu

- **Adaptive QEC SDK**: Libraries and operators for decoders, profilers, and logical mapping; Python/C++ APIs.
- **Hybrid AI Orchestrator**: Scheduling across quantum/AI nodes (Kozuchi, ABCI‑Q) with reliability‑aware routing.
- **Open Toolchain Adapters**: First‑class connectors for Fujitsu’s open operations toolchain; CI/CD recipes.
- **Device Telemetry Lake**: Time‑series syndromes, calibrations, health metrics with privacy‑preserving analytics.
- **QEC‑aware Compilers**: Passes for logical tiling, patch compaction, and surface‑code‑aware optimization.
- **Benchmarking Harness**: Reproducible suites for logical error, throughput, and hybrid workload KPIs.

---

## How We’re Different

- **Adaptive, data‑driven QEC**: RL/GNN decoders tailored to the live device; not just static MWPM.
- **Modular & open**: Clean APIs; no lock‑in; integrates with existing open toolchains and simulators.
- **Hybrid‑ready**: Built for AI+quantum co‑design—reliability as a first‑class concern for pipelines.
- **Scientific rigor + engineering polish**: Curriculum learning for decoders, confidence‑aware objectives (CVaR = Conditional Value at Risk; LCB = Lower Confidence Bound), dynamic shots.

---

## Team & Governance

- **Core team**: Quantum algorithms/QEC, control, ML/RL, systems engineering; prior experience across [academia/industry].
- **Composition**: The team consists of two PhDs with more than 7 years of post‑doctoral research and development experience.
- **Credentials (abridged)**: Publications in QEC/ML; open‑source contributions (Qiskit/Cirq/Stim‑ecosystem where applicable); advisors available on request.
- **Engagement model**: Weekly stand‑ups, milestone reviews, secure repo access, and co‑authored reports.

---

## Next Steps

1. Joint scoping call (60–90 min) to select pilot workloads and co‑sign KPIs/baselines by [target date].
2. Access to simulator/toolchain endpoints and representative noise/topology profiles; NDA execution.
3. Kickoff by [target date + 2 weeks]; complete Tier 1 pilot in 8–12 weeks; options for extension to Tier 2.

### Numbers to Confirm (with Fujitsu)

- **Latency target**: <1 ms (GPU) / <5 ms (CPU) for decoder inference path.
- **ZNE overhead**: 3–6× shot multiplier schedules for selected workloads.
- **Fallback threshold**: >15% degradation vs baseline triggers MWPM/BP fallback.
- **KPIs per workload**: Final list of hybrid kernels (sampling/kernels/optimization) and their measurement cadence.
- **Compute budgets**: GPU/CPU hours and scheduling windows on A64FX/cluster resources.

**Call to Action**: Please propose 2–3 time slots this/next week for the scoping call. We can provide a 2‑week feasibility check (no‑cost) to validate integration before full pilot.

Contact: Dr. Debasis Mondal <deba10106@gmail.com>

---

## Technical Appendix (Merged)

- **RL Decoder Environment**: State = syndrome graph + telemetry features; Action = correction proposals; Reward = reduction in logical error proxy with regularization for latency/overhead.
- **GNN Architecture**: Message‑passing on Tanner/stabilizer graph; node/edge features for defect locations, correlations; residual blocks; optional attention.
- **Training Protocol**: Offline pre‑training on simulated noise; online fine‑tuning with Fujitsu profiles; early stopping on validation logical error.
- **Data Requirements**: Syndrome streams, calibration logs, topology maps; privacy‑preserving ingestion; CI‑width targets for sampling budgets.
- **Baselines & Evaluation**: MWPM/BP as baselines; report logical error vs. distance and noise parameters; include mean±CI and latency distributions.

### Error‑Mitigation Methodology (Optional)
- **ZNE**: Extrapolate to zero noise via gate‑folding; typical shot multipliers 3–9×.
- **PEC**: Requires noise models; overhead depends on quasi‑probabilities; 5–20× typical for small circuits.
- **M3/Readout**: Calibration matrices; modest runtime overhead; recommended recalibration cadence per drift.
- **Symmetry/Zero‑penalty checks**: Project to symmetry subspace; low overhead, problem‑dependent.
- **CDR**: Train on easy Clifford instances; apply regression to target; small extra runs required.

### Decoder Design and Training
- RL environment/state/action/reward; curriculum; uncertainty diagnostics.
- GNN message‑passing on Tanner/stabilizer graphs; residual/attention.
- Training: simulated noise pre‑train + online fine‑tune with Fujitsu profiles.

### Data & Integration
- Schemas for syndromes/calibration/topology; adapters for open toolchain; CI harness for reproducibility.

### Hybrid AI Pilot Details
- Workloads: sampling, kernels, optimization; metrics: throughput, variance, latency; pipelines aligned to Kozuchi/ABCI‑Q.

### Channel Toolkit (Optional Extension)
- GST/channel tomography, spectroscopy, non‑Markovianity diagnostics, capacity estimators; dashboards with CI‑width targets.

### Cryptography Bench (Optional Extension)
- BB84/E91 with finite‑key; DI‑QKD via CHSH; side‑channel/implementation audits; PQC migration playbooks.

---

## Additional Offerings Beyond QEC (Quantum Computing, Channels, Cryptography, and ML/RL)

### Quantum Computing Services
- **Algorithm Co‑Design & Benchmarking**: Co‑develop NISQ/FT algorithms (VQE/QAOA/QSVT/QSP, amplitude estimation, Hamiltonian simulation) with hardware‑aware constraints; provide standardized benchmarks and baselines.
- **Resource Estimation & Compilation**: Logical resource modeling (T‑count/T‑depth, 2‑qubit counts), surface‑code budgets, and compiler passes for layout/routing on Fujitsu topologies.
- **Pulse‑Level Control & Calibration**: Optimal control (GRAPE/CRAB), DRAG parameter tuning, calibration scheduling with closed‑loop ML.
- **Transpilation Optimization**: Device‑native synthesis, pattern extraction, ZX/e‑graph rewrites integrated with Fujitsu’s open toolchain.

### Quantum Channels
- **Channel Modeling & Tomography**: Gate‑set/channel tomography, noise spectroscopy, non‑Markovianity diagnostics; confidence‑aware estimators.
- **Capacity & Performance Bounds**: Estimation/bounding of classical, quantum, and private capacities; channel discrimination experiments for control policies.
- **Entanglement Management**: Distillation protocols, heralded entanglement workflows; robust Bell tests for DI scenarios.
- **Error Mitigation**: Probabilistic error cancellation, zero‑noise extrapolation, symmetry verification—integrated with scheduling/orchestration.
- **Channel Simulation Library**: Pluggable Pauli/Clifford/general CPTP noise models matched to Fujitsu hardware telemetry.

### Quantum Cryptography
- **QKD Stacks**: BB84/E91 simulations, parameter estimation, finite‑key analysis; integration with Fujitsu orchestration and telemetry.
- **Device‑Independent & Semi‑DI Protocols**: CHSH‑based DI‑QKD feasibility studies, randomness certification, and loophole analyses.
- **Quantum‑Safe Migration**: PQC readiness assessments (lattice/code‑based), hybrid protocols (classical PQC + QKD), HSM/PKI integration, compliance guidance.
- **Side‑Channel & Implementation Security**: Leakage modeling, countermeasure design, auditing for lab/field deployments.

### ML/RL for Quantum Systems
- **Adaptive Control & Decoding**: RL for decoder selection, syndrome‑to‑action policies, and calibration controllers; Bayesian optimization for fast tuning.
- **Hybrid Workflow Optimization**: Scheduling/placement for AI+quantum pipelines (Kozuchi/ABCI‑Q), reliability‑aware routing, and cost models.
- **Predictive Maintenance**: GNN/time‑series models for drift prediction, qubit health scoring, and proactive recalibration.
- **Active Learning for Tomography**: Sample‑efficient experiment design with confidence‑driven acquisition.
- **Post‑Processing Error Mitigation Suite**: ZNE, PEC, M3/readout mitigation, symmetry checks, and CDR; integrated with scheduling/orchestration and evaluation harnesses.

---

## Suggested Pilot Extensions (Menu)
- **Error Mitigation Suite**: Integrate and benchmark ZNE, PEC, M3/readout mitigation, symmetry verification, and CDR on Fujitsu profiles; automated selection and parameter sweeps.
- **Channel Toolkit**: Deliver a channel tomography + capacity‑estimation toolkit with CI‑width targets and dashboards.
- **Crypto Bench**: DI‑QKD/CHSH test bench on simulators with finite‑key analysis; roadmap to lab integration.
- **Hybrid AI Demo**: Reliability‑hardened optimization/sampling kernels wired into Kozuchi/ABCI‑Q; throughput/variance gains.
- **Telemetry Lake**: Secure data schemas and ingestion for syndromes/calibrations; privacy‑preserving analytics and alerts.

---

## Integration & Differentiation Notes
- **Open & Modular**: Clean APIs, adapters to Fujitsu’s open toolchain; avoids lock‑in, supports joint development.
- **Standards‑Aligned**: QASM/QIR where useful, reproducible pipelines, CI artefacts.
- **Co‑Research Ready**: We co‑author benchmarks and whitepapers; align to FTQC FY26+ milestones and ABCI‑Q hybrid strategy.

---

## Export & Sharing

- **PDF export (Pandoc)**
  ```bash
  # Install pandoc and a PDF engine (e.g., wkhtmltopdf)
  pandoc -s pilot.md -o pilot.pdf \
    --from gfm --pdf-engine=wkhtmltopdf \
    --metadata title="QCRAFT × FUJITSU Pilot"
  ```
  - Mermaid diagrams may require pre-rendering or a filter; for a quick export, consider replacing Mermaid with rendered PNGs.

- **VS Code (Markdown PDF extension)**
  - Open `pilot.md` and use Command Palette: “Markdown PDF: Export (pdf)”.

- **Image assets**
  - If sharing outside GitHub, render Mermaid diagrams to PNG/SVG and embed them in place of code blocks for consistent rendering.

---

## References (Selected)

- Varsamopoulos, S., Bertels, K., Almudever, C. G. (2019). Comparing Neural Network Based Decoders for the Surface Code. IEEE Transactions on Computers; arXiv:1811.12456.
- Baireuther, P., O’Brien, T. E., Tarasinski, B., Beenakker, C. W. J. (2018). Machine‑learning‑assisted correction of correlated qubit errors in a topological code. Quantum 2, 48.
- PyMatching: MWPM decoder library. https://github.com/Quantum-Computing-PFA/PyMatching
- Stim: Fast stabilizer circuit simulator. https://github.com/quantumlib/Stim
- Mitiq documentation: Zero‑Noise Extrapolation guide. https://mitiq.readthedocs.io/en/stable/guide/zne.html

## Acronym Glossary

- **MWPM**: Minimum‑Weight Perfect Matching (decoder baseline)
- **BP**: Belief Propagation (decoder baseline)
- **ZNE**: Zero‑Noise Extrapolation (error mitigation)
- **PEC**: Probabilistic Error Cancellation (error mitigation)
- **M3**: Measurement/Readout Mitigation (matrix‑based)
- **CDR**: Clifford Data Regression (error mitigation)
- **CI**: Confidence Interval
- **CVaR**: Conditional Value at Risk
- **LCB**: Lower Confidence Bound
- **GNN**: Graph Neural Network
- **RL**: Reinforcement Learning
- **FTQC**: Fault‑Tolerant Quantum Computing
- **QKD / DI‑QKD**: Quantum Key Distribution / Device‑Independent QKD
- **PQC**: Post‑Quantum Cryptography
- **CPTP**: Completely Positive Trace‑Preserving (maps)
- **A64FX**: Fujitsu Arm‑based HPC CPU platform
- **ABCI‑Q / Kozuchi**: Fujitsu hybrid AI/quantum programs/infrastructure
- **QASM / QIR**: Quantum Assembly / Quantum Intermediate Representation
