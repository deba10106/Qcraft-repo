import os
import yaml
import json
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from stable_baselines3 import PPO
from scode.heuristic_layer.config_loader import ConfigLoader
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from scode.graph_transformer.graph_transformer import ConnectivityAwareGraphTransformer
from scode.rl_agent.environment import SurfaceCodeEnvironment
from evaluation.evaluation_framework import EvaluationFramework

RESULTS_DIR = 'outputs/test_results'
os.makedirs(RESULTS_DIR, exist_ok=True)

# --- Enhanced Visualization Utilities ---
def plot_ideal_layout(surface_code, d, layout_type, grid_connectivity, save_path=None):
    G = nx.Graph()
    for q, pos in surface_code.qubit_layout.items():
        G.add_node(q, **pos)
    pos = {q: (v['x'], v['y']) for q, v in surface_code.qubit_layout.items()}
    plt.figure(figsize=(7, 7))
    nx.draw(G, pos, node_color='lightgray', edge_color='gray', node_size=400, alpha=0.3, with_labels=True)
    if 'X' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(G, pos, nodelist=surface_code.stabilizer_map['X'], node_color='pink', node_shape='o', label='X-stabilizer')
    if 'Z' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(G, pos, nodelist=surface_code.stabilizer_map['Z'], node_color='cornflowerblue', node_shape='s', label='Z-stabilizer')
    if 'X' in surface_code.logical_operators:
        nx.draw_networkx_nodes(G, pos, nodelist=surface_code.logical_operators['X'], node_color='orange', node_shape='*', label='X-logical', node_size=600)
    if 'Z' in surface_code.logical_operators:
        nx.draw_networkx_nodes(G, pos, nodelist=surface_code.logical_operators['Z'], node_color='green', node_shape='h', label='Z-logical', node_size=600)
    nx.draw_networkx_labels(G, pos)
    plt.title(f'Ideal Surface Code Layout (d={d}, {layout_type}, {grid_connectivity})')
    plt.legend(scatterpoints=1)
    if save_path:
        plt.savefig(save_path)
    plt.close()

def plot_device_connectivity(hardware, grid_connectivity, save_path=None):
    G = nx.Graph()
    connectivity = hardware.get('qubit_connectivity', {})
    for q, neighbors in connectivity.items():
        for n in neighbors:
            G.add_edge(int(q), int(n))
    pos = {q: (q % 10, -(q // 10)) for q in G.nodes}
    plt.figure(figsize=(7, 7))
    nx.draw(G, pos, node_color='lightblue', edge_color='black', node_size=400, with_labels=False)
    plt.title(f'Device Connectivity: {grid_connectivity}')
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path)
    plt.close()

def plot_mapping_overlay(surface_code, device, mapping, d, layout_type, grid_connectivity, ler=None, save_path=None):
    code_G = nx.Graph()
    for q, posn in surface_code.qubit_layout.items():
        code_G.add_node(q, **posn)
    code_pos = {q: (v['x'], v['y']) for q, v in surface_code.qubit_layout.items()}
    device_G = nx.Graph()
    connectivity = device.get('qubit_connectivity', {})
    for q, neighbors in connectivity.items():
        for n in neighbors:
            device_G.add_edge(int(q), int(n))
    dx = max([v['x'] for v in surface_code.qubit_layout.values()]) + 3
    device_pos = {q: (dx + (q % 10), -(q // 10)) for q in device_G.nodes}
    plt.figure(figsize=(14, 7))
    nx.draw(code_G, code_pos, node_color='lightgray', edge_color='gray', node_size=400, alpha=0.3, with_labels=True)
    if 'X' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.stabilizer_map['X'], node_color='pink', node_shape='o', label='X-stabilizer')
    if 'Z' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.stabilizer_map['Z'], node_color='cornflowerblue', node_shape='s', label='Z-stabilizer')
    if 'X' in surface_code.logical_operators:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.logical_operators['X'], node_color='orange', node_shape='*', label='X-logical', node_size=600)
    if 'Z' in surface_code.logical_operators:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.logical_operators['Z'], node_color='green', node_shape='h', label='Z-logical', node_size=600)
    nx.draw_networkx_labels(code_G, code_pos)
    nx.draw(device_G, device_pos, node_color='lightblue', edge_color='black', node_size=400, with_labels=True)
    for lq, pq in mapping.items():
        if lq in code_pos and pq in device_pos:
            plt.annotate('', xy=device_pos[pq], xytext=code_pos[lq],
                         arrowprops=dict(arrowstyle='->', color='purple', lw=2, alpha=0.7))
    title = f'Mapping Overlay (d={d}, {layout_type}, {grid_connectivity})'
    if ler is not None:
        title += f' | LER: {ler:.2e}'
    plt.title(title)
    plt.legend(scatterpoints=1)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path)
    plt.close()

def plot_combined_figure(surface_code, hardware, mapping, d, layout_type, grid_connectivity, ler=None, save_path=None):
    fig, axs = plt.subplots(1, 3, figsize=(21, 7))
    code_G = nx.Graph()
    for q, posn in surface_code.qubit_layout.items():
        code_G.add_node(q, **posn)
    code_pos = {q: (v['x'], v['y']) for q, v in surface_code.qubit_layout.items()}
    nx.draw(code_G, code_pos, node_color='lightgray', edge_color='gray', node_size=400, alpha=0.3, with_labels=True, ax=axs[0])
    if 'X' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.stabilizer_map['X'], node_color='pink', node_shape='o', label='X-stabilizer', ax=axs[0])
    if 'Z' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.stabilizer_map['Z'], node_color='cornflowerblue', node_shape='s', label='Z-stabilizer', ax=axs[0])
    if 'X' in surface_code.logical_operators:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.logical_operators['X'], node_color='orange', node_shape='*', label='X-logical', node_size=600, ax=axs[0])
    if 'Z' in surface_code.logical_operators:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.logical_operators['Z'], node_color='green', node_shape='h', label='Z-logical', node_size=600, ax=axs[0])
    nx.draw_networkx_labels(code_G, code_pos, ax=axs[0])
    axs[0].set_title(f'Ideal Surface Code Layout (d={d}, {layout_type}, {grid_connectivity})')
    axs[0].legend(scatterpoints=1)
    device_G = nx.Graph()
    connectivity = hardware.get('qubit_connectivity', {})
    for q, neighbors in connectivity.items():
        for n in neighbors:
            device_G.add_edge(int(q), int(n))
    device_pos = {q: (q % 10, -(q // 10)) for q in device_G.nodes}
    nx.draw(device_G, device_pos, node_color='lightblue', edge_color='black', node_size=400, with_labels=False, ax=axs[1])
    axs[1].set_title(f'Device Connectivity: {grid_connectivity}')
    nx.draw(code_G, code_pos, node_color='lightgray', edge_color='gray', node_size=400, alpha=0.3, with_labels=True, ax=axs[2])
    if 'X' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.stabilizer_map['X'], node_color='pink', node_shape='o', label='X-stabilizer', ax=axs[2])
    if 'Z' in surface_code.stabilizer_map:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.stabilizer_map['Z'], node_color='cornflowerblue', node_shape='s', label='Z-stabilizer', ax=axs[2])
    if 'X' in surface_code.logical_operators:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.logical_operators['X'], node_color='orange', node_shape='*', label='X-logical', node_size=600, ax=axs[2])
    if 'Z' in surface_code.logical_operators:
        nx.draw_networkx_nodes(code_G, code_pos, nodelist=surface_code.logical_operators['Z'], node_color='green', node_shape='h', label='Z-logical', node_size=600, ax=axs[2])
    nx.draw_networkx_labels(code_G, code_pos, ax=axs[2])
    nx.draw(device_G, device_pos, node_color='lightblue', edge_color='black', node_size=400, with_labels=True, ax=axs[2])
    for lq, pq in mapping.items():
        if lq in code_pos and pq in device_pos:
            axs[2].annotate('', xy=device_pos[pq], xytext=code_pos[lq],
                         arrowprops=dict(arrowstyle='->', color='purple', lw=2, alpha=0.7))
    title = f'Mapping Overlay (d={d}, {layout_type}, {grid_connectivity})'
    if ler is not None:
        title += f' | LER: {ler:.2e}'
    axs[2].set_title(title)
    for ax in axs:
        ax.axis('off')
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path)
    plt.close()

# --- Main Test Script ---
def main():
    # Load config and hardware profile
    config = ConfigLoader.load_yaml('configs/surface_code_config.yaml')
    device = config['device']
    h_layer = HeuristicInitializationLayer(config, device)
    transformer = ConnectivityAwareGraphTransformer(
        config=config,
        hardware_graph=device,
        native_gates=device['native_gates'],
        gate_error_rates=device['gate_error_rates'],
        qubit_error_rates={q: device['qubit_properties'][q]['readout_error'] for q in device['qubit_properties']}
    )
    evaluation_framework = EvaluationFramework(config)
    # Find SB3 PPO checkpoint
    output_dir = 'outputs'
    artifacts_dir = os.path.join(output_dir, 'training_artifacts')
    provider = device.get('provider_name', 'provider').lower()
    dev_name = device.get('device_name', 'device').lower()
    layout_type = config['surface_code']['layout_type']
    code_distance = config['surface_code']['code_distance']
    model_name = f"{provider}_{dev_name}_{layout_type}_d{code_distance}_sb3_ppo_surface_code.zip"
    model_path = os.path.join(artifacts_dir, model_name)
    if not os.path.exists(model_path) or os.path.getsize(model_path) == 0:
        print("Trained model not found or is empty. Continue to training phase.")
        return
    try:
        model = PPO.load(model_path)
    except Exception as e:
        print(f"Failed to load model: {e}. Deleting invalid model file and continue to training phase.")
        try:
            os.remove(model_path)
        except Exception as rm_e:
            print(f"Could not delete invalid model file: {rm_e}")
        return
    code_distances = [3, 5, 7, 9]
    grid_connectivity = device.get('topology_type', 'unknown')
    for d in code_distances:
        # Generate the ideal surface code to count required qubits (data + ancilla)
        surface_code = h_layer.generate_surface_code(
            code_distance=d,
            layout_type=config['surface_code']['layout_type'],
            visualize=False
        )
        required_qubits = len(surface_code.qubit_layout)
        device_qubits = len(device['qubit_connectivity'])
        if device_qubits < required_qubits:
            print(f"[WARNING] Device has only {device_qubits} qubits, but code distance {d} ({config['surface_code']['layout_type']}) requires at least {required_qubits}. Skipping.")
            continue
        # 1. Map to hardware (initial, for env setup)
        result = transformer.transform(surface_code)
        # 3. Create RL environment
        env = SurfaceCodeEnvironment(
            transformed_layout=result,
            hardware_specs=device,
            error_profile=device['qubit_properties'],
            config=config
        )
        obs, _ = env.reset()
        done = False
        last_ler = None
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, truncated, info = env.step(action)
            done = done or truncated
            if 'logical_error_rate' in info:
                last_ler = info['logical_error_rate']
        if last_ler is None and hasattr(env, '_last_ler'):
            last_ler = env._last_ler
        final_mapping = result['transformed_layout']  # Placeholder: update if env provides better
        # 5. Visualize and save
        plot_ideal_layout(surface_code, d, layout_type, grid_connectivity, save_path=f'{RESULTS_DIR}/ideal_layout_d{d}_best.png')
        plot_device_connectivity(device, grid_connectivity, save_path=f'{RESULTS_DIR}/device_connectivity_d{d}_best.png')
        plot_mapping_overlay(surface_code, device, final_mapping, d, layout_type, grid_connectivity, ler=last_ler, save_path=f'{RESULTS_DIR}/mapping_overlay_d{d}_best.png')
        plot_combined_figure(surface_code, device, final_mapping, d, layout_type, grid_connectivity, ler=last_ler, save_path=f'{RESULTS_DIR}/combined_d{d}_best.png')
        # Save data
        data = {
            'distance': d,
            'stabilizers': surface_code.stabilizer_map,
            'logical_operators': surface_code.logical_operators,
            'mapped_stabilizers': result['hardware_stabilizer_map'],
            'layout': {q: dict(pos) for q, pos in surface_code.qubit_layout.items()}
        }
        with open(f'{RESULTS_DIR}/layout_data_d{d}_best.json', 'w') as f:
            json.dump(data, f, indent=2)
        # After evaluation, print and save gate error metrics
        metrics = evaluation_framework.evaluate_resource_efficiency(result)
        wsq_err = metrics.get('weighted_single_qubit_gate_error', None)
        wtq_err = metrics.get('weighted_two_qubit_gate_error', None)
        print(f"d={d}: weighted_single_qubit_gate_error={wsq_err}, weighted_two_qubit_gate_error={wtq_err}")
        # Save to file
        with open(f"outputs/metrics_d{d}.json", "w") as f:
            json.dump(metrics, f, indent=2)
        # Save all KPIs
        ler = evaluation_framework.evaluate_logical_error_rate(result, device, device.get('noise_model', {}))
        resource_eff = evaluation_framework.evaluate_resource_efficiency(result)
        kpi = {
            'distance': d,
            'ler': ler,
            'resource_efficiency': resource_eff,
        }
        with open(f"outputs/kpi_d{d}.json", "w") as f:
            json.dump(kpi, f, indent=2)
    print(f"Enhanced test results saved in {RESULTS_DIR}")

if __name__ == "__main__":
    main() 