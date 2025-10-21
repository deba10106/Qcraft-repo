# QCRAFT × FUJITSU — Adaptive QEC Pilot
QCRAFT × FUJITSU — Adaptive QEC Pilot

To build and integrate the world’s most intelligent, privacy-preserving, and hardware-agnostic platform for fault-tolerant quantum computing — anywhere it’s run.

We’re building the first AI-powered software that adapts to each quantum device, fixes its errors in real-time, and protects sensitive quantum circuits.



---

# Main Slides

---

# Agenda
- Why partner vs build
- Pilot at a glance
- KPIs and illustrative results
- Architecture fit (Figures 1–2)
- SOW, milestones, RACI
- Risk, data & security
- Value mapping to Fujitsu
- Commercials & license options
- Team & next steps

---

# Why Partner vs Build (Pilot)
- **Speed to capability**: Adaptive QEC in 8–12 wks vs 12–18 mos in‑house
- **Focused specialization**: QEC (RL/GNN) & reliability focus
- **Neutral & modular**: Open toolchain + A64FX simulators; no lock‑in
- **Risk mitigation**: KPIs, artifacts, MWPM/BP fallback
- **FTQC alignment**: Milestones toward FY26+ targets

---

# Pilot at a Glance
- **Objective**: Stabilize hybrid AI workloads via adaptive QEC + post‑processing mitigation
- **Outcomes**: ≥20–40% LER reduction; 15–25% variance reduction; inference <1 ms (GPU) / <5 ms (CPU)
- **Timeline**: 8–12 weeks (Tier 1)
- **Ownership**: Qcraft (RL/QEC integration); Fujitsu (toolchain, simulators)
- **Deliverables**: Integrated decoder layer, checkpoints/dashboards, benchmark dossier, roadmap
- **Next steps**: 60–90 min scoping; simulator/toolchain access; kickoff ≤2 wks

---

# Key KPIs (Targets)
| KPI | Baseline | Target | Measurement |
|---|---|---|---|
| Logical error rate (LER) | MWPM/BP | ≥20–40% reduction | Stim + PyMatching on Fujitsu profiles |
| Variance (CI width) | Current | 15–25% reduction | Repeated runs on selected kernels |
| Inference latency | Current | <1 ms GPU / <5 ms CPU | Decoder inference path |
| Stability under drift | N/A | Sustained over 8–24 h | Rolling syndromes + online adaptation |

---

# Illustrative Result (Simulated) — Table 1
Conditions: d=5–7, depolarizing p∈[1e‑3,1e‑2], Stim+PyMatching, 100k shots

| Method | LER (mean±CI) | Variance (CI width) | Overhead |
|---|---|---|---|
| Baseline MWPM | 1.00× (ref) | 1.00× | 1.0× |
| Adaptive RL decoder | 0.72×–0.85× | 0.8×–0.9× | 1.0× |
| RL + ZNE | 0.60×–0.75× | 0.8×–0.9× | 3–6× shots |

Note: For discussion; pilot will validate on Fujitsu profiles.

---

# As‑Is → To‑Be
| Category | As‑Is | To‑Be |
|---|---|---|
| Reliability | Static MWPM/BP | Adaptive decoder; ≥20–40% LER reduction |
| Variance | High CI width | 15–25% CI width reduction |
| Latency | Uncharacterized | <1 ms GPU / <5 ms CPU |
| Mitigation | Ad‑hoc / none | Structured ZNE/M3/PEC sweeps |
| Process | Siloed | Reproducible runs, dashboards, KPIs |
| Lock‑in | Tightly coupled | Open adapters; neutral layer |

---

# Product Suite
- **Qcraft (pilot focus)**: Decoders, noise profiler, logical mapping, operator tooling
- **Post‑Processing Mitigation (opt.)**: ZNE, M3, PEC, symmetry checks, CDR

---

# Figure 1 — Architecture Fit (High‑Level)
Figure 1. High‑level integration of Qcraft with Fujitsu stack
```mermaid
flowchart LR

  subgraph TB[On‑Prem / VPC Trust Boundary]
    subgraph FJ[Fujitsu Stack]
      HW[Fujitsu HW & Control]
      OT[Open Toolchain / Orchestration]
      SIM[A64FX Simulators]
      HW --> OT
      OT <--> SIM
    end

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

    OT <--> ADPT
    SIM <--> ADPT
    ADPT <--> ORCH
  end

  subgraph APP[Apps & Hybrid AI Pipelines]
    APPS[Kozuchi / ABCI‑Q / Workloads]
  end
  ORCH --> APPS

  HW -. telemetry/calibration .-> PROF
  SIM -. syndromes/shots .-> PROF
```

---

# Figure 2 — Error Mitigation Workflow
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

---

# Team & Governance
- Core: Quantum algorithms/QEC, control, ML/RL, systems engineering
- Composition: Two PhDs with 7+ years post‑doctoral R&D experience
- Credentials: Publications in QEC/ML; open‑source (Qiskit/Cirq/Stim)
- Governance: Weekly stand‑ups; milestones; secure repo; co‑authored reports

---

# Next Steps & Contacts
- 60–90 min scoping to finalize workloads and KPI baselines
- Provide simulator/toolchain access and representative profiles; NDA
- Kickoff ≤2 weeks; Tier 1 in 8–12 weeks; Tier 2 optional

Contact: Dr. Debasis Mondal <deba10106@gmail.com>

---

# Appendix

---

# Statement of Work (SOW)
- **In-scope**: Adaptive decoder integration, simulators, data schemas, benchmarking, optional mitigation pack, KPI report, roadmap
- **Out-of-scope**: Hardware control changes, firmware, new simulator dev, production SLAs beyond pilot
- **Deliverables**: Decoder layer + adapters; checkpoints, dashboards, notebooks; benchmark dossier; image URIs

---

# Milestones & Acceptance
- **M1 (Wk2)**: Env bring‑up, schemas, adapter smoke tests → 20%
- **M2 (Wk6)**: RL/GNN decoder + baseline report (draft) → 30%
- **M3 (Wk8)**: Hybrid AI demo; latency/variance characterization → 30%
- **M4 (Wk10–12)**: Final KPIs, robustness tests, roadmap → 20%
- Acceptance: joint reviews, KPI deltas, reproducibility checks

---

# RACI (Abridged)
| Workstream | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Decoder design & training | Qcraft | Qcraft | Fujitsu Research/Hardware | Sponsors |
| Toolchain adapters | Qcraft | Qcraft | Fujitsu Open Toolchain | Stakeholders |
| Data & profiles | Fujitsu | Fujitsu | Qcraft | Qcraft |
| KPIs & acceptance | Joint | Joint | Stakeholders | Sponsors |

---

# Risk Register (Key)
| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Noise non‑stationarity | Med | High | Online adaptation; retraining; fallback to MWPM/BP if RL degrades >15% |
| Latency constraints | Low–Med | Med | Optimize path; sparsification; hybrid decoder | 
| Integration friction | Med | Med | Simulator‑first; gRPC adapter; service mode |
| Data/compliance | Low | High | NDA, on‑prem/VPC; clear data separation |

---

# Data & Security
- Time‑stamped JSON/Parquet for syndromes/shots/calibrations
- Retention windows; immutable logs for audit
- Role‑based access; least‑privilege
- SBOM, dependency scanning, CVE remediation SLA

---

# Value Mapping to Fujitsu
| Deliverable | Stakeholder | Objective | Metric | Integration |
|---|---|---|---|---|
| Decoder layer | Open Toolchain | Reliability layer | LER vs baseline | Orchestration + A64FX |
| Benchmark dossier | Research/Hardware | FTQC roadmap evidence | KPI table with CI | Reviews, FY26 align |
| Hybrid AI demo | Kozuchi/ABCI‑Q | Stable subroutines | Variance/throughput | Hybrid pipelines |
| Mitigation pack (opt.) | Research/Apps | Realistic overheads | Δ metric with overhead | Orchestration sweeps |

---

# Commercials & Licensing
- **Fixed‑fee pilot**: $150,000 (8–12 wks; 2–3 FTE Qcraft + 1–2 FTE Fujitsu liaison)
- **Payment**: M1 20% · M2 30% · M3 30% · M4 20%
- **License matrix**:
  - Pilot (source‑available; non‑commercial)
  - Production subscription (annual; SLAs)
  - On‑prem/perpetual (maintenance + support)

---

# References
- Varsamopoulos et al., IEEE TC 2019 (arXiv:1811.12456)
- Baireuther et al., Quantum 2018 (ML‑assisted correction)
- Stim (stabilizer simulator), PyMatching (MWPM)
- Mitiq ZNE documentation
