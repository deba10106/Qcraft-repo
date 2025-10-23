# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import copy
from typing import List, Dict, Any, Optional, Callable
from scode.heuristic_layer.surface_code_object import SurfaceCodeObject
import networkx as nx
import numpy as np
import random
import pprint
from scode.utils.decoder_interface import DecoderInterface
import traceback
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from scode.rl_agent.reward_engine import MultiPatchRewardEngine
import glob
import os
import logging

logger = logging.getLogger(__name__)


def merge_configs(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge two config dicts, with override taking precedence over base.
    Deep merge for nested dicts.
    """
    if override is None:
        return copy.deepcopy(base)
    result = copy.deepcopy(base)
    for k, v in override.items():
        if (
            k in result
            and isinstance(result[k], dict)
            and isinstance(v, dict)
        ):
            result[k] = merge_configs(result[k], v)
        else:
            result[k] = v
    return result


def _enforce_constraints(hw_nodes, qubit_errors, constraints):
    """
    Filter hardware nodes based on exclusion zones and error thresholds.
    """
    exclude = set(constraints.get('exclude_qubits', []))
    max_error = constraints.get('max_error_rate', None)
    filtered = []
    for q in hw_nodes:
        if int(q) in exclude:
            continue
        if max_error is not None:
            err = qubit_errors.get(int(q), {}).get('readout_error', 0.0)
            if err > max_error:
                continue
        filtered.append(q)
    return filtered


class MultiPatchMapper:
    """
    Maps multiple surface code patches onto a hardware device, optimizing for connectivity, resource allocation, and constraints.
    Args:
        config: Configuration dict (YAML/JSON-driven). Should include 'advanced_constraints' and 'mapping_heuristic' fields.
        hardware_graph: Hardware device graph (from device config)
    
    Constraints (e.g., exclude_qubits, max_error_rate) and mapping_heuristic can be set in the config file or passed as API parameters to map_patches().
    API parameters always override config file values.
    """
    # Heuristic registry for extensibility
    _heuristics: Dict[str, Callable] = {}

    def __init__(self, config: Dict[str, Any], hardware_graph: Dict[str, Any]):
        self.config = config
        self.hardware_graph = hardware_graph
        # Register heuristics
        self._register_heuristics()

    def _register_heuristics(self):
        self._heuristics = {
            'greedy': self._greedy_mapping,
            'simulated_annealing': self._simulated_annealing_mapping,
            'genetic_algorithm': self._genetic_algorithm_mapping
        }

    def map_patches(
        self,
        surface_code_objects: List[SurfaceCodeObject],
        mapping_constraints: Optional[Dict[str, Any]] = None,
        use_rl_agent: bool = False,
        rl_policy_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Map logical patches to hardware, using merged config (API params override config file).
        Supports selectable mapping heuristics and advanced metrics.
        If use_rl_agent is True, use the RL agent to generate the mapping for each patch.
        Constraints (e.g., exclude_qubits, max_error_rate) and mapping_heuristic can be set in the config file or passed as API parameters to map_patches().
        API parameters always override config file values.
        """
        if not use_rl_agent:
            raise RuntimeError("Only RL agent mapping is allowed. Set use_rl_agent=True and provide a valid RL policy.")
        # Ensure mapping_constraints is a dict
        mapping_constraints = mapping_constraints or {}
        merged_config = merge_configs(self.config, mapping_constraints)
        num_patches = merged_config.get('num_patches', len(surface_code_objects))
        layout_type = merged_config.get('layout_type', 'adjacent')
        min_distance = merged_config.get('min_distance_between_patches', 1)
        patch_shapes = merged_config.get('patch_shapes', None) if merged_config else None
        if not patch_shapes or len(patch_shapes) < num_patches:
            default_shape = 'rectangular'
            patch_shapes = (patch_shapes or []) + [default_shape] * (num_patches - len(patch_shapes or []))
        if len(patch_shapes) != num_patches:
            logger.error("patch_shapes length %s does not match num_patches %s", len(patch_shapes), num_patches)
            logger.error("patch_shapes: %s", patch_shapes)
            logger.error("mapping_constraints: %s", mapping_constraints)
            logger.error("surface_code_objects: %s", surface_code_objects)
            raise RuntimeError("patch_shapes and num_patches mismatch")
        logger.debug("Final patch_shapes used for mapping: %s", patch_shapes)
        heuristic = merged_config.get('mapping_heuristic', 'greedy')
        advanced_constraints = merged_config.get('advanced_constraints', {})
        multi_patch_layout = {}
        resource_allocation = {}
        used_qubits = set()
        # --- Patch placement ---
        for i, patch in enumerate(surface_code_objects):
            if not hasattr(patch, 'qubit_layout') or not patch.qubit_layout:
                logger.debug("Patch %s has empty or missing qubit_layout! Skipping placement for this patch.", i)
                continue
            # Debug: print types and values of x/y
            for q, pos in patch.qubit_layout.items():
                x, y = pos['x'], pos['y']
                logger.debug("Patch %s qubit %s: x=%s (%s), y=%s (%s)", i, q, x, type(x), y, type(y))
                if not isinstance(x, (int, float)):
                    logger.warning("Patch %s qubit %s: x is not numeric! Value: %s", i, q, x)
                if not isinstance(y, (int, float)):
                    logger.warning("Patch %s qubit %s: y is not numeric! Value: %s", i, q, y)
            # Defensive conversion
            offset = i * (max(float(pos['x']) for pos in patch.qubit_layout.values()) + min_distance)
            patch_layout = {}
            for q, pos in patch.qubit_layout.items():
                new_x = float(pos['x']) + offset if layout_type == 'adjacent' else float(pos['x'])
                new_y = float(pos['y'])
                # Preserve type info for frontend
                patch_layout[q] = {'x': new_x, 'y': new_y, 'type': pos.get('type', 'data'), 'error_rate': pos.get('error_rate', 0.0)}
            try:
                multi_patch_layout[i] = {'layout': patch_layout, 'shape': patch_shapes[i]}
            except Exception as e:
                logger.error("Exception during patch placement for patch %s: %s", i, e)
                import traceback; traceback.print_exc()
                logger.debug("Patch %s state: %s", i, patch.__dict__)
                continue
        logger.debug("MultiPatchMapper: multi_patch_layout has %s patches. Keys: %s", len(multi_patch_layout), list(multi_patch_layout.keys()))
        inter_patch_connectivity = self._compute_inter_patch_connectivity(multi_patch_layout, min_distance)
        # --- RL agent mapping (all patches at once) ---
        from scode.rl_agent.environment import SurfaceCodeEnvironment
        import os
        logical_to_physical = {}
        # --- Create generator and reward engine once ---
        surface_code_generator = HeuristicInitializationLayer(self.config, self.hardware_graph)
        reward_engine = MultiPatchRewardEngine(self.config)
        try:
            patch_count = len(surface_code_objects)
            # Use code_distance/layout_type from first patch or config
            code_distance = getattr(surface_code_objects[0], 'code_distance', mapping_constraints.get('code_distance', 3))
            layout_type_patch = getattr(surface_code_objects[0], 'layout_type', mapping_constraints.get('layout_type', 'rotated'))
            # Update config for all patches
            env_config = copy.deepcopy(self.config)
            if 'surface_code' not in env_config:
                env_config['surface_code'] = {}
            env_config['surface_code']['patch_count'] = patch_count
            env_config['surface_code']['code_distance'] = code_distance
            env_config['surface_code']['layout_type'] = layout_type_patch
            # Add debug log for RL environment config
            logger.debug("Creating RL env with patch_count=%s, code_distance=%s, layout_type=%s", patch_count, code_distance, layout_type_patch)
            # --- Set patch_count and disable curriculum for inference ---
            if 'environment' in env_config:
                env_config['environment']['patch_count'] = patch_count
            else:
                env_config['patch_count'] = patch_count
            # Disable curriculum for inference
            if 'curriculum_learning' in env_config:
                env_config['curriculum_learning']['enabled'] = False
            if 'curriculum' in env_config:
                env_config['curriculum']['enabled'] = False
            # Also set in multi_patch_rl_agent.environment if present
            if 'multi_patch_rl_agent' in env_config and 'environment' in env_config['multi_patch_rl_agent']:
                env_config['multi_patch_rl_agent']['environment']['patch_count'] = patch_count
            # Create environment ONCE
            env = SurfaceCodeEnvironment(
                env_config,
                self.hardware_graph,
                surface_code_generator=surface_code_generator,
                reward_engine=reward_engine
            )
            logger.debug("RL env.surface_code_config: %s", env.surface_code_config)
            env.surface_code_config['patch_count'] = patch_count
            env.surface_code_config['code_distance'] = code_distance
            env.surface_code_config['layout_type'] = layout_type_patch
            obs, _ = env.reset()
            # Defensive assertion
            if env.patch_count != patch_count or len(env.current_mappings) != patch_count:
                logger.error("RL env patch_count mismatch after reset! env.patch_count=%s, expected=%s, len(current_mappings)=%s", env.patch_count, patch_count, len(env.current_mappings))
                logger.error("Config passed to env: %s", env_config)
                raise RuntimeError(f"RL environment patch_count mismatch: env.patch_count={env.patch_count}, expected={patch_count}")
            # --- Find the correct policy file for the multi-patch config ---
            provider = self.hardware_graph.get('provider_name', 'provider').lower()
            dev_name = self.hardware_graph.get('device_name', 'device').lower()
            # Prefer nested path in multi_patch_rl_agent.training_artifacts with fallback to top-level
            training_artifacts_cfg = (
                self.config.get('multi_patch_rl_agent', {}).get('training_artifacts', {})
                or self.config.get('training_artifacts', {})
            )
            artifact_dir = os.path.abspath(training_artifacts_cfg.get('output_dir', './outputs/training_artifacts'))
            # Match artifacts with or without an optional code_family token before layout_type.
            # Examples we need to match:
            #   provider_device_rotated_d3_patches2_stage1_sb3_ppo_surface_code_*.zip
            #   provider_device_surface_rotated_d3_patches2_stage1_sb3_ppo_surface_code_*.zip
            artifact_pattern = f"{provider}_{dev_name}_*{layout_type_patch}_d{code_distance}_patches{patch_count}_stage*_sb3_ppo_surface_code*.zip"
            search_pattern = os.path.join(artifact_dir, artifact_pattern)
            artifact_files = glob.glob(search_pattern)
            if artifact_files:
                artifact_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
                policy_path = artifact_files[0]
                if len(artifact_files) > 1:
                    logger.warning("Multiple artifacts found for pattern %s. Using most recent: %s", artifact_pattern, policy_path)
                logger.info("Loading RL policy: %s", policy_path)
            else:
                # Fallback: try to match the old pattern without stage/timestamp
                fallback_pattern = f"{provider}_{dev_name}_{layout_type_patch}_d{code_distance}_patches{patch_count}_sb3_ppo_surface_code*.zip"
                fallback_search = os.path.join(artifact_dir, fallback_pattern)
                fallback_files = glob.glob(fallback_search)
                if fallback_files:
                    fallback_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
                    policy_path = fallback_files[0]
                    logger.warning("No stage/timestamp artifact found, using fallback: %s", policy_path)
                    logger.info("Loading RL policy: %s", policy_path)
                else:
                    logger.error("No trained RL agent found for code_distance=%s, patch_count=%s, layout_type=%s. Expected at: %s", code_distance, patch_count, layout_type_patch, search_pattern)
                    return {
                        'multi_patch_layout': multi_patch_layout,
                        'inter_patch_connectivity': inter_patch_connectivity,
                        'resource_allocation': resource_allocation,
                        'optimization_metrics': {},
                        'logical_to_physical': {},
                        'has_overlap': False
                    }
            from stable_baselines3 import PPO
            model = PPO.load(policy_path, env=env)
            done = False
            step_count = 0
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, done, truncated, info = env.step(action)
                step_count += 1
                # Print only LER and reward concisely
                ler = info.get('ler', info.get('logical_error_rate', None))
                if (ler is not None) or (reward is not None):
                    logger.info("RL inference step %s: reward=%s, LER=%s", step_count, reward, ler)
            # Debug: print RL agent output mapping length and content
            logger.debug("RL agent env.current_mappings length: %s", len(getattr(env, 'current_mappings', [])))
            logger.debug("RL agent env.current_mappings: %s", getattr(env, 'current_mappings', None))
            # Strict overlap check after RL mapping
            all_hw = []
            for mapping in getattr(env, 'current_mappings', []):
                all_hw.extend(list(mapping.values()))
            if len(set(all_hw)) < len(all_hw):
                raise RuntimeError("Illegal mapping: Physical qubit overlap detected across patches in RL mapping. Mapping halted.")
            if len(getattr(env, 'current_mappings', [])) != patch_count:
                logger.error("RL agent produced %s mappings, expected %s", len(getattr(env, 'current_mappings', [])), patch_count)
                logger.error("env config: %s", env_config)
                logger.error("surface_code_objects: %s", surface_code_objects)
                logger.error("mapping_constraints: %s", mapping_constraints)
                raise RuntimeError("RL agent did not produce mapping for all patches")
            # Merge mapping for all patches, robust to missing mappings
            for i in range(patch_count):
                if hasattr(env, 'current_mappings') and i < len(env.current_mappings):
                    logical_to_physical[i] = dict(env.current_mappings[i])
                else:
                    logger.warning("No mapping for logical qubit/patch %s (only %s mappings found)", i, len(getattr(env, 'current_mappings', [])))
                    logical_to_physical[i] = {}  # or handle as appropriate
            # Check for overlap across all patches
            all_hw = []
            for patch_map in logical_to_physical.values():
                all_hw.extend(list(patch_map.values()))
            has_overlap = len(set(all_hw)) < len(all_hw)
            if has_overlap:
                logger.warning("Overlap detected: the same physical qubit is mapped to multiple logical qubits across patches!")
        except Exception as e:
            logger.error("Exception during RL agent mapping for all patches: %s", e)
            import traceback; traceback.print_exc()
        optimization_metrics = self._compute_optimization_metrics(
            multi_patch_layout, inter_patch_connectivity, logical_to_physical, advanced_constraints
        )
        logger.debug("MultiPatchMapper.map_patches (RL agent):")
        logger.debug("  Number of logical qubits: %s", sum(len(patch.qubit_layout) for patch in surface_code_objects))
        logger.debug("  Number of hardware qubits: %s", len(self.hardware_graph.get('qubit_connectivity', {})))
        logger.debug("  logical_to_physical mapping: %s", pprint.pformat(logical_to_physical))
        return {
            'multi_patch_layout': multi_patch_layout,
            'inter_patch_connectivity': inter_patch_connectivity,
            'resource_allocation': resource_allocation,
            'optimization_metrics': optimization_metrics,
            'logical_to_physical': logical_to_physical,
            'has_overlap': has_overlap
        }

    def _greedy_mapping(self, surface_code_objects: List[SurfaceCodeObject], constraints: Dict[str, Any]) -> Dict[Any, int]:
        """
        Greedy mapping: assign logical data qubits to hardware qubits with lowest error, minimizing neighbor distance.
        Enforces exclusion zones and error thresholds.
        """
        hw_graph = nx.Graph()
        hw_connectivity = self.hardware_graph.get('qubit_connectivity', {})
        for q, neighbors in hw_connectivity.items():
            for n in neighbors:
                hw_graph.add_edge(int(q), int(n))
        qubit_errors = self.hardware_graph.get('qubit_properties', {})
        hw_nodes = set(hw_connectivity.keys())
        hw_nodes = _enforce_constraints(hw_nodes, qubit_errors, constraints)
        def get_error(q):
            return qubit_errors.get(int(q), {}).get('readout_error', 0.0)
        logical_to_physical = {}
        used_hw = set()
        all_logical = []
        logical_neighbors = {}
        for patch in surface_code_objects:
            for lq, info in patch.qubit_layout.items():
                # Map all qubit types: data, ancilla_X, ancilla_Z
                all_logical.append(lq)
                if hasattr(patch, 'adjacency_matrix') and patch.adjacency_matrix is not None:
                    if isinstance(patch.adjacency_matrix, dict):
                        logical_neighbors[lq] = patch.adjacency_matrix.get(lq, [])
                    elif hasattr(patch.adjacency_matrix, 'neighbors'):
                        logical_neighbors[lq] = list(patch.adjacency_matrix.neighbors(lq))
                    else:
                        logical_neighbors[lq] = []
                else:
                    logical_neighbors[lq] = []
                    
        # Debug logging
        logger.debug("_greedy_mapping: Found %s logical qubits to map", len(all_logical))
        logger.debug("_greedy_mapping: Available hardware qubits: %s", len(hw_nodes))
        logger.debug("_greedy_mapping: hw_nodes types: %s", [type(q) for q in hw_nodes])
        logger.debug("_greedy_mapping: all_logical types: %s", [type(q) for q in all_logical])
        # Check for non-numeric types in hw_nodes and all_logical
        for q in hw_nodes:
            if not isinstance(q, (int, float)):
                logger.warning("_greedy_mapping: hw_node is not numeric! Value: %s (%s)", q, type(q))
        for q in all_logical:
            if not isinstance(q, (int, float)):
                logger.warning("_greedy_mapping: logical qubit is not numeric! Value: %s (%s)", q, type(q))
                    
        sorted_hw = sorted(hw_nodes, key=get_error)
        
        # Extra check to avoid empty mappings
        if not sorted_hw:
            logger.error("No hardware qubits available after applying constraints")
            return {}
            
        if all_logical and sorted_hw:
            # Map first logical qubit to best hardware qubit
            logical_to_physical[all_logical[0]] = int(sorted_hw[0])
            used_hw.add(int(sorted_hw[0]))
            
            # Map remaining qubits greedily
        for lq in all_logical[1:]:
                best_hw, best_score = None, float('inf')
                neighbors = logical_neighbors.get(lq, [])
                
                # Priority: map to neighbors of already mapped logical neighbors
                mapped_neighbors = [logical_to_physical.get(n) for n in neighbors if n in logical_to_physical]
                
                # Find hardware qubits that are adjacent to the mapped neighbors
                candidate_hw = set()
                for n in mapped_neighbors:
                    if n is not None:
                        candidate_hw.update(hw_graph.neighbors(n))
                
                # Filter out already used hardware qubits
                candidate_hw = candidate_hw - used_hw
                
                # If no candidates from adjacency, use all remaining hardware qubits
                if not candidate_hw:
                    candidate_hw = set(sorted_hw) - used_hw
                
                if candidate_hw:
                    # Choose the hardware qubit with lowest error rate
                    best_hw = min(candidate_hw, key=get_error)
                    logical_to_physical[lq] = int(best_hw)
                    used_hw.add(int(best_hw))
                else:
                    # All hardware qubits are used, can't map more logical qubits
                    logger.warning("Not enough hardware qubits to map all logical qubits. Mapped %s/%s", len(logical_to_physical), len(all_logical))
                    break
                    
        # Final mapping check
        if not logical_to_physical:
            logger.error("Failed to create any mappings in greedy algorithm")
            
        return logical_to_physical

    def _simulated_annealing_mapping(self, surface_code_objects: List[SurfaceCodeObject], constraints: Dict[str, Any]) -> Dict[Any, int]:
        """
        Simulated annealing mapping: advanced, production-ready implementation for mapping logical to physical qubits.
        Enforces exclusion zones and error thresholds.
        """
        hw_connectivity = self.hardware_graph.get('qubit_connectivity', {})
        qubit_errors = self.hardware_graph.get('qubit_properties', {})
        hw_nodes = list(map(int, hw_connectivity.keys()))
        hw_nodes = list(map(int, _enforce_constraints(hw_nodes, qubit_errors, constraints)))
        def get_error(q):
            return qubit_errors.get(int(q), {}).get('readout_error', 0.0)
        all_logical = []
        logical_neighbors = {}
        for patch in surface_code_objects:
            for lq in patch.qubit_layout:
                all_logical.append(lq)
                if hasattr(patch, 'adjacency_matrix') and patch.adjacency_matrix is not None:
                    if isinstance(patch.adjacency_matrix, dict):
                        logical_neighbors[lq] = patch.adjacency_matrix.get(lq, [])
                    elif hasattr(patch.adjacency_matrix, 'neighbors'):
                        logical_neighbors[lq] = list(patch.adjacency_matrix.neighbors(lq))
                    else:
                        logical_neighbors[lq] = []
                else:
                    logical_neighbors[lq] = []
        # Initial random assignment
        if len(hw_nodes) < len(all_logical):
            raise ValueError("Not enough hardware qubits for mapping (after constraints)")
        current = {lq: hw for lq, hw in zip(all_logical, hw_nodes[:len(all_logical)])}
        def cost(mapping):
            total = 0.0
            for lq, hw in mapping.items():
                for ln in logical_neighbors.get(lq, []):
                    if ln in mapping:
                        total += abs(hw - mapping[ln])
                total += 10 * get_error(hw)
            return total
        T = 1.0
        T_min = 1e-3
        alpha = 0.95
        best = current.copy()
        best_cost = cost(current)
        while T > T_min:
            for _ in range(100):
                lq1, lq2 = random.sample(all_logical, 2)
                new = current.copy()
                new[lq1], new[lq2] = new[lq2], new[lq1]
                new_cost = cost(new)
                if new_cost < best_cost or random.random() < np.exp((best_cost - new_cost) / T):
                    current = new
                    if new_cost < best_cost:
                        best = new
                        best_cost = new_cost
            T *= alpha
        return best

    def _genetic_algorithm_mapping(self, surface_code_objects: List[SurfaceCodeObject], constraints: Dict[str, Any]) -> Dict[Any, int]:
        """
        Genetic algorithm mapping: production-ready, real implementation.
        Enforces exclusion zones and error thresholds.
        """
        hw_connectivity = self.hardware_graph.get('qubit_connectivity', {})
        qubit_errors = self.hardware_graph.get('qubit_properties', {})
        hw_nodes = list(map(int, hw_connectivity.keys()))
        hw_nodes = list(map(int, _enforce_constraints(hw_nodes, qubit_errors, constraints)))
        all_logical = []
        logical_neighbors = {}
        for patch in surface_code_objects:
            for lq, info in patch.qubit_layout.items():
                # Map all qubit types: data, ancilla_X, ancilla_Z
                all_logical.append(lq)
                if hasattr(patch, 'adjacency_matrix') and patch.adjacency_matrix is not None:
                    if isinstance(patch.adjacency_matrix, dict):
                        logical_neighbors[lq] = patch.adjacency_matrix.get(lq, [])
                    elif hasattr(patch.adjacency_matrix, 'neighbors'):
                        logical_neighbors[lq] = list(patch.adjacency_matrix.neighbors(lq))
                    else:
                        logical_neighbors[lq] = []
                else:
                    logical_neighbors[lq] = []
        if len(hw_nodes) < len(all_logical):
            raise ValueError("Not enough hardware qubits for mapping (after constraints)")
        pop_size = 30
        generations = 50
        mutation_rate = 0.2
        def get_error(q):
            return qubit_errors.get(int(q), {}).get('readout_error', 0.0)
        def cost(mapping):
            total = 0.0
            for lq, hw in mapping.items():
                for ln in logical_neighbors.get(lq, []):
                    if ln in mapping:
                        total += abs(hw - mapping[ln])
                total += 10 * get_error(hw)
            return total
        # Population: list of dicts
        population = []
        for _ in range(pop_size):
            assignment = random.sample(hw_nodes, len(all_logical))
            mapping = {lq: hw for lq, hw in zip(all_logical, assignment)}
            population.append(mapping)
        for _ in range(generations):
            # Evaluate
            scored = sorted(population, key=cost)
            survivors = scored[:pop_size // 2]
            # Crossover
            children = []
            while len(children) < pop_size - len(survivors):
                p1, p2 = random.sample(survivors, 2)
                cut = random.randint(1, len(all_logical) - 1)
                child_assignment = list(p1.values())[:cut] + list(p2.values())[cut:]
                # Ensure uniqueness
                if len(set(child_assignment)) < len(child_assignment):
                    # Repair: fill with unused
                    used = set(child_assignment)
                    unused = [q for q in hw_nodes if q not in used]
                    for i in range(len(child_assignment)):
                        if child_assignment.count(child_assignment[i]) > 1:
                            child_assignment[i] = unused.pop()
                child = {lq: hw for lq, hw in zip(all_logical, child_assignment)}
                children.append(child)
            # Mutation
            for child in children:
                if random.random() < mutation_rate:
                    idx1, idx2 = random.sample(range(len(all_logical)), 2)
                    lq1, lq2 = all_logical[idx1], all_logical[idx2]
                    child[lq1], child[lq2] = child[lq2], child[lq1]
            population = survivors + children
        best = min(population, key=cost)
        return best

    def _compute_inter_patch_connectivity(self, multi_patch_layout: Dict[int, Any], min_distance: int) -> Dict[str, Any]:
        # Compute inter-patch connectivity based on minimum distance
        connectivity = {}
        patch_positions = {
            i: [
                (float(pos['x']), float(pos['y']))
                for pos in patch['layout'].values()
                if 'x' in pos and 'y' in pos
            ]
            for i, patch in multi_patch_layout.items()
        }
        for i in patch_positions:
            for j in patch_positions:
                if i < j:
                    min_dist = np.min([
                        np.linalg.norm(np.array(p1) - np.array(p2))
                        for p1 in patch_positions[i] for p2 in patch_positions[j]
                    ])
                    if min_dist <= min_distance:
                        connectivity[(i, j)] = {'distance': min_dist}
        return connectivity

    def _compute_optimization_metrics(
        self,
        multi_patch_layout: Dict[int, Any],
        inter_patch_connectivity: Dict[str, Any],
        logical_to_physical: Dict[Any, int],
        constraints: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute advanced metrics: total swaps, average/max/median error rate, resource utilization, inter-logical distances, constraint violations, etc.
        """
        qubit_errors = self.hardware_graph.get('qubit_properties', {})
        # Flatten all mapped hardware qubit indices from all patches
        used_hw = set()
        logical_positions = []
        for patch_map in logical_to_physical.values():
            if isinstance(patch_map, dict):
                used_hw.update(patch_map.values())
                logical_positions.extend(patch_map.values())
        total_hw = len(self.hardware_graph.get('qubit_connectivity', {}))
        resource_utilization = len(used_hw) / total_hw if total_hw else 0.0
        inter_patch_links = len(inter_patch_connectivity)
        # Error rates
        error_rates = [qubit_errors.get(hw, {}).get('readout_error', 0.0) for hw in logical_positions]
        if error_rates:
            avg_error_rate = np.mean(error_rates)
            max_error_rate = np.max(error_rates)
            median_error_rate = np.median(error_rates)
        else:
            avg_error_rate = max_error_rate = median_error_rate = 0.0
        # Inter-logical distances
        if len(logical_positions) > 1:
            dists = [abs(a - b) for i, a in enumerate(logical_positions) for b in logical_positions[i+1:]]
            min_dist = np.min(dists)
            max_dist = np.max(dists)
            avg_dist = np.mean(dists)
        else:
            min_dist = max_dist = avg_dist = 0.0
        # Constraint violations
        violations = 0
        exclude = set(constraints.get('exclude_qubits', []))
        max_error = constraints.get('max_error_rate', None)
        for hw in logical_positions:
            if int(hw) in exclude:
                violations += 1
            if max_error is not None and qubit_errors.get(hw, {}).get('readout_error', 0.0) > max_error:
                violations += 1
        return {
            'avg_error_rate': avg_error_rate,
            'max_error_rate': max_error_rate,
            'median_error_rate': median_error_rate,
            'resource_utilization': resource_utilization,
            'inter_patch_links': inter_patch_links,
            'min_inter_logical_distance': min_dist,
            'max_inter_logical_distance': max_dist,
            'avg_inter_logical_distance': avg_dist,
            'constraint_violations': violations
        } 