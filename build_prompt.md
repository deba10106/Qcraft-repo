<!-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 | SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com> -->


---

<span>QCraft Technical Specification Document (TSD) & Product Requirements Document (PRD)</span>

1. Introduction & Purpose

1.1 Vision

QCraft is a desktop-based, adaptive quantum compiler and error correction platform. It transforms high-level logical circuits into hardware-executable, fault-tolerant circuits tailored to quantum processors’ specific constraints.

The system combines:

Reinforcement Learning (RL) and Graph Neural Networks (GNNs) to optimize mapping and patch selection.

Multi-family QEC support (Surface codes, qLDPC) with modular extension.

Privacy-preserving workflows, ensuring logical circuits remain local while only encoded, obfuscated circuits are exported.

PySide6 GUI frontend with YAML/JSON-configurable backend for extensibility and reproducibility.

1.2 Why QCraft?

Hardware-Aware: Bridges gap between logical circuit design and hardware-native constraints.

Fault-Tolerant: Provides systematic quantum error correction (QEC).

Adaptive: Learns optimal strategies through RL + feedback loops.

Extensible: Supports new QEC codes and hardware backends.

Privacy-Oriented: Circuits never leave the user’s desktop in logical form.

1.3 Target Audience

Quantum researchers and developers needing robust FT compilation.

Enterprises requiring privacy-preserving quantum workloads.

Hardware providers for benchmarking and co-optimization.

Academic and industrial labs interested in adaptive QEC techniques.

---

2. System Overview

2.1 Core Components

Circuit Editor (PySide6 GUI) – Logical circuit design.

Code Patch Optimizer – RL+GNN-based QEC code patch discovery.

Multi-Patch Mapper – Placement of multiple QEC patches (Surface, qLDPC).

Fault-Tolerant Circuit Builder – Encodes gates into FT equivalents.

Circuit Optimizer – Reduces depth, swaps, and T-count.

Decoder – Local, RL-assisted syndrome decoding.

Error Profiler – Builds empirical noise models.

Config Manager – YAML-driven control of pipeline, policies, schemas.

Execution Backend – Interfaces to simulators or hardware.

Results Manager – Logging, visualization, and export.

2.2 Architectural Design

flowchart LR
GUI\[PySide6 GUI\] --&gt; WB\[WorkflowBridge\]
WB --&gt; ORCH\[Orchestrator\]
ORCH --&gt; SCAPI\[SurfaceCodeAPI\]
ORCH --&gt; QLDPC\[QLDPCAPI\]
ORCH --&gt; FT\[Fault-Tolerant Circuit Builder\]
ORCH --&gt; OPT\[Circuit Optimization API\]
ORCH --&gt; CS\[CodeSwitcherAPI\]
ORCH --&gt; MAP\[MultiPatchMapper (RL+GNN)\]
ORCH --&gt; DEC\[SyndromeDecoder (RL)\]
ORCH --&gt; PRO\[ErrorProfiler\]
ORCH --&gt; EXE\[Execution Backend\]
ORCH --&gt; LOG\[Logging & Results Manager\]
CFG\[ConfigManager + Schemas\] --- ORCH
DEV\[Device Abstraction Layer\] --- ORCH
REG\[CodePatchRegistry\] --- ORCH

---

3. Functional Requirements

3.1 End-to-End Workflow

 1. User designs logical circuit in QCraft IDE.

 2. System preprocesses and analyzes circuit.

 3. Circuit is decomposed to hardware gate set OR encoded first.

 4. Code Patch Optimizer selects optimal QEC family + layout.

 5. Multi-Patch Mapper places patches onto qubit grid.

 6. Fault-Tolerant Circuit Builder encodes gates.

 7. Circuit Optimizer reduces depth, swaps, and error propagation.

 8. Decoder handles syndromes locally.

 9. Encoded, optimized circuit exported to backend API.

10. Execution results fed back into RL agents for improvement.

3.2 Use Cases

Single Patch Encoding (d=3 surface code).

Multi-Patch Mapping (multiple logical qubits on IBM/Rigetti devices).

Family Switching (Surface ↔ qLDPC) by config.

Privacy Execution (local obfuscation + decoding).

Curriculum RL Training (progressive patch complexity).

---

4. Non-Functional Requirements

Category	Requirement

Performance	Mapping time &lt; 5s for d=3 patches; training convergence within 10^5 steps.
Fidelity	Improvement from \~60–65% to \~80–85% on medium-depth circuits.
Privacy	No logical circuit exposure beyond local machine.
Scalability	Support up to \~20 logical qubits (multi-patch).
Compatibility	Works with IBM, IonQ, Rigetti, simulators.

---

5. Detailed Technical Specifications

5.1 Circuit Editor (GUI)

Built with PySide6.

Features: drag-drop gate design, fault-tolerant toggle view, code family selection.

Supports classical register manipulation.

5.2 Code Patch Optimizer (RL + GNN)

Inputs: circuit structure, hardware profile, YAML config.

Outputs: selected QEC family + patch layout.

RL Setup:

Agent: PPO baseline, curriculum learning enabled.

State: current mapping, patch validity, stabilizer score.

Actions: patch placement, family switch, code distance adjustment.

Reward: multi-objective (see below).

5.3 Multi-Patch Mapper

Handles mapping of multiple logical qubits.

Reward Function (Final Design):

reward = (
valid_mapping \* I\[all patches valid\]
\+ invalid_mapping \* I\[overlaps\]
\+ connectivity_bonus \* connectivity_score
\+ adjacency_bonus \* adjacency_score
\+ inter_patch_distance_penalty \* mean_distance
\+ resource_utilization_bonus \* hardware_utilization
\+ error_rate_bonus \* (1 - avg_error_rate)
\+ logical_operator_bonus \* logical_operator_score
\+ fully_mapped_bonus \* I\[all qubits mapped\]
\+ unmapped_qubit_penalty \* unmapped_qubits
)

Normalization: running_mean_std

Curriculum: staged (Structure Mastery → Hardware Adaptation → Noise-Aware Optimization).

Configurable: YAML-based weights, phase multipliers.

5.4 Circuit Optimizer

RL-based depth and gate count minimization.

Objectives: reduce SWAPs, penalize T-count, schedule for minimal decoherence.

5.5 Decoder

Local RL+GNN-based decoder.

Replaces cloud-based decoders, reducing latency.

5.6 Error Profiler

Builds empirical noise models from execution feedback.

Augments provider’s incomplete noise specs.

5.7 Config Manager

YAML/JSON schemas validate all configs.

No hardcoded values — everything configurable.

---

6. System Architecture & Workflow

6.1 End-to-End Workflow

flowchart TD
A\[Logical Circuit in IDE\]\
--&gt; B\[Preprocessing\]\
--&gt; C{Encode First or Decompose First?}\
C --&gt;|Decompose| D\[Hardware Gate Set Decomposition\]\
C --&gt;|Encode| E\[Fault-Tolerant Encoding\]\
D --&gt; F\[Code Patch Optimizer\]\
E --&gt; F\
F --&gt; G\[Multi-Patch Mapper\]\
G --&gt; H\[Fault-Tolerant Circuit Builder\]\
H --&gt; I\[Circuit Optimizer\]\
I --&gt; J\[Decoder + Conditional Logic\]\
J --&gt; K\[Execution Backend\]\
K --&gt; L\[Results + Logging\]\
L --&gt; M\[Error Profiler + RL Feedback\]\
M --&gt; F

---

7. Hardware & Software Requirements

7.1 Desktop Environment

OS: Linux, Windows, MacOS

Python: 3.9+

Dependencies: PySide6, Qiskit (optional), Stim, PyMatching, RLlib/Stable-Baselines3

GPU: optional for RL acceleration

7.2 Config Files

configs/multi_patch_rl_agent.yaml – RL agent + reward shaping

configs/code_families.yaml – Registry of families (Surface, qLDPC)

configs/hardware.json – Device abstraction

---

8. Testing & Validation

KPIs:

Logical Error Rate (LER) improvement

Resource efficiency (physical qubits, swaps)

RL training convergence rate

Hardware adaptability score

Evaluation Framework:

Built-in (evaluation_framework.py)

Metrics computed automatically (LER, error rates, mapping validity).

---

9. Deployment & Maintenance

Packaging: Python package (pip install qcraft).

GUI Launch: qcraft command.

Versioning: Semantic versioning, RL agent checkpoints stored in /outputs/runs.

Config-Driven: YAML schemas ensure reproducibility.

---

10. Future Extensions

Blind Quantum Computing integration.

FPGA/ASIC-based local decoders.

Distributed RL for faster training.

Advanced noise models (non-Markovian, correlated).

Plugin system for new QEC families.

---

11. Appendices

11.1 Example Reward Config (YAML)

reward_function:
valid_mapping: 10.0
invalid_mapping: -20.0
overlap_penalty: -5.0
connectivity_bonus: 2.0
adjacency_bonus: 1.0
inter_patch_distance_penalty: -1.0
resource_utilization_bonus: 0.5
error_rate_bonus: 1.0
logical_operator_bonus: 1.0
fully_mapped_bonus: 2.0
mapped_qubit_bonus: 0.1
unmapped_qubit_penalty: -0.05
normalization: running_mean_std
dynamic_weights: true
phase_multipliers:
hardware_adaptation_gate_error: 2.0
hardware_adaptation_swap: 2.0
noise_aware_logical_error: 2.5
structure_mastery_stabilizer: 3.0

11.2 Example Multi-Patch Config

multi_patch: num_patches: 2 patch_shapes: - rectangular - rectangular min_distance_between_patches: 1 layout_type: adjacent