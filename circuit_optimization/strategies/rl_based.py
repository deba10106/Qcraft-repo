# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import os
try:
    from stable_baselines3 import PPO
except ImportError:
    PPO = None
from circuit_optimization.rl_env import CircuitOptimizationEnvironment
from circuit_optimization.reward_engine import CircuitOptimizationRewardEngine
import yaml
import json
from scode.rl_agent.progress import ProgressBarCallback

def load_device_info(hardware_json_path, devices_yaml_path):
    with open(hardware_json_path, 'r') as f:
        hw = json.load(f)
    device_name = hw['device_name']
    provider = hw['provider_name'].lower()
    with open(devices_yaml_path, 'r') as f:
        devices = yaml.safe_load(f)
    key = f"{provider}_devices"
    device_list = devices.get(key, [])
    for d in device_list:
        if d['device_name'] == device_name:
            return d
    raise ValueError(f"Device {device_name} not found in {devices_yaml_path}")

class RLBasedOptimizer:
    """
    RL-based circuit optimizer. Uses a trained RL agent (e.g., PPO) to optimize the circuit.
    Config-driven model loading and agent selection.
    """
    def _get_artifacts_dir(self):
        output_dir = self.config.get('system', {}).get('output_dir', './outputs')
        return os.path.abspath(os.path.join(output_dir, 'training_artifacts'))

    def _resolve_model_path(self, model_path):
        if os.path.isabs(model_path):
            return model_path
        artifacts_dir = self._get_artifacts_dir()
        return os.path.join(artifacts_dir, model_path)

    def __init__(self, config=None):
        self.config = config or {}
        self.model_path = self.config.get('rl_config', {}).get('model_path', None)
        self.agent = None
        if self.model_path:
            resolved_path = self._resolve_model_path(self.model_path)
            if os.path.exists(resolved_path):
                self._load_agent(resolved_path)

    def _load_agent(self, path):
        if PPO is None:
            raise ImportError("stable-baselines3 is required for RL-based optimization. Please install it.")
        self.agent = PPO.load(path)

    def _circuit_to_obs(self, circuit, device_info, env):
        """
        Reset env and return initial observation.
        - For Gymnasium Env: reset() -> (obs, info)
        - For VecEnv: reset() -> obs
        Do not pass kwargs to VecEnv.reset.
        """
        try:
            out = env.reset()
        except TypeError:
            # Fallback to no-args if kwargs not supported
            out = env.reset()
        if isinstance(out, tuple) and len(out) >= 1:
            return out[0]
        return out

    def _obs_to_circuit(self, obs, env):
        # Use the RL environment's method to decode observation to circuit
        return env.get_circuit_from_obs(obs)

    def _normalize_and_filter_gates(self, circuit: dict, device_info: dict) -> dict:
        # Normalize gate names: lowercase, cnot->cx
        for gate in circuit.get('gates', []):
            name = gate.get('name', '').lower()
            if name == 'cnot':
                name = 'cx'
            gate['name'] = name
        # Decompose all non-native gates to native set
        from circuit_optimization.utils import decompose_to_native_gates
        native_gates = set(device_info.get('native_gates', []))
        circuit = decompose_to_native_gates(circuit, native_gates)
        return circuit


    def optimize(self, circuit: dict, device_info: dict) -> dict:
        if self.agent is None:
            raise RuntimeError("RL agent not loaded. Please provide a valid model path.")
        # Use provided device_info if available; otherwise resolve via ConfigManager + DeviceAbstraction
        dev_info = device_info
        if not dev_info:
            try:
                from configuration_management.config_manager import ConfigManager
                hw = ConfigManager.load_hardware_json()
                provider = hw['provider_name']
                device_name = str(hw['device_name']).lower()
                from hardware_abstraction.device_abstraction import DeviceAbstraction
                dev_info = DeviceAbstraction.get_device_info(provider, device_name)
            except Exception:
                # Final fallback: keep original device_info (may be None) and proceed
                dev_info = device_info
        # RL environment config
        rl_env_conf = self.config.get('rl_config', {})
        reward_weights = rl_env_conf.get('reward_weights', None)
        normalize_reward = rl_env_conf.get('normalize_reward', False)
        curriculum = rl_env_conf.get('curriculum', None)
        # Only pass curriculum if enabled
        curriculum_cfg = curriculum if curriculum and curriculum.get('enabled', False) else None
        def make_env():
            return CircuitOptimizationEnvironment(
                circuit=circuit,
                device_info=dev_info,
                action_space_size=rl_env_conf.get('action_space_size', 8),
                reward_weights=reward_weights,
                normalize_reward=normalize_reward,
                curriculum=curriculum_cfg
            )
        n_envs = rl_env_conf.get('n_envs', 1)
        if n_envs > 1:
            from stable_baselines3.common.vec_env import SubprocVecEnv
            env = SubprocVecEnv([make_env for _ in range(n_envs)])
        else:
            env = make_env()
        import numpy as np
        obs = self._circuit_to_obs(circuit, dev_info, env)
        done_flag = False
        while not done_flag:
            action, _ = self.agent.predict(obs, deterministic=True)
            step_out = env.step(action)
            # Handle VecEnv (obs, rewards, dones, infos)
            if isinstance(step_out, tuple) and len(step_out) == 4:
                obs, rewards, dones, infos = step_out
                done_flag = bool(np.any(dones))
            # Handle Gymnasium Env (obs, reward, terminated, truncated, info)
            elif isinstance(step_out, tuple) and len(step_out) == 5:
                obs, reward, terminated, truncated, info = step_out
                done_flag = bool(terminated or truncated)
            else:
                # Fallback: try classic gym (obs, reward, done, info)
                try:
                    obs, reward, done, info = step_out
                    done_flag = bool(done)
                except Exception:
                    # If format is unknown, break to avoid infinite loop
                    break
        optimized_circuit = self._obs_to_circuit(obs, env)
        # Always convert to device native gates
        optimized_circuit = self._normalize_and_filter_gates(optimized_circuit, dev_info)
        return optimized_circuit


    def train(self, *args, **kwargs):
        import time
        artifacts_dir = self._get_artifacts_dir()
        os.makedirs(artifacts_dir, exist_ok=True)
        # Dynamic artifact naming from hardware.json
        try:
            from configuration_management.config_manager import ConfigManager
            hw = ConfigManager.load_hardware_json()
        except Exception:
            with open('./configs/hardware.json', 'r') as f:
                hw = json.load(f)
        provider = hw['provider_name'].lower()
        device_name = hw['device_name']
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        model_path = os.path.join(artifacts_dir, f'rl_optimizer_{provider}_{device_name}_{timestamp}.zip')
        # RL training setup
        rl_env_conf = self.config.get('rl_config', {})
        reward_weights = rl_env_conf.get('reward_weights', None)
        normalize_reward = rl_env_conf.get('normalize_reward', False)
        curriculum = rl_env_conf.get('curriculum', None)
        curriculum_cfg = curriculum if curriculum and curriculum.get('enabled', False) else None
        def make_env():
            return CircuitOptimizationEnvironment(
                circuit=kwargs.get('circuit'),
                device_info=kwargs.get('device_info'),
                action_space_size=rl_env_conf.get('action_space_size', 8),
                reward_weights=reward_weights,
                normalize_reward=normalize_reward,
                curriculum=curriculum_cfg
            )
        n_envs = int(rl_env_conf.get('n_envs', 1))
        if n_envs > 1:
            from stable_baselines3.common.vec_env import SubprocVecEnv
            env = SubprocVecEnv([make_env for _ in range(n_envs)])
        else:
            env = make_env()
        # PPO agent honoring config n_steps/batch_size
        if PPO is None:
            raise ImportError("stable-baselines3 is required for RL-based optimization. Please install it.")
        n_steps = int(rl_env_conf.get('n_steps', 2048))
        batch_size = int(rl_env_conf.get('batch_size', 64))
        torch_device = rl_env_conf.get('torch_device', 'auto')
        agent = PPO('MlpPolicy', env, verbose=1, learning_rate=rl_env_conf.get('learning_rate', 0.0001), n_steps=n_steps, batch_size=batch_size, device=torch_device)
        # Align total timesteps to rollout size and add progress reporting with early stop
        total_timesteps = int(rl_env_conf.get('total_timesteps', rl_env_conf.get('num_episodes', 1000)))
        rollout_size = max(1, n_steps * n_envs)
        adjusted = (total_timesteps // rollout_size) * rollout_size
        if adjusted <= 0:
            adjusted = rollout_size
        reporter = ProgressBarCallback(adjusted, mode='terminal')
        reporter._on_training_start()
        def progress_cb(locals_, globals_):
            n = locals_['self'].num_timesteps
            rewards = locals_.get('rewards', [])
            avg_reward = sum(rewards) / len(rewards) if rewards else None
            reporter.update(min(n, adjusted), reward=avg_reward, ler=None)
            # Early stop to avoid overshoot beyond adjusted
            if n >= adjusted:
                reporter.finish()
                return False
            return True
        agent.learn(total_timesteps=adjusted, callback=progress_cb)
        reporter.finish()
        agent.save(model_path)
        self.agent = agent
        print(f"[RLBasedOptimizer] Model saved to {model_path}")

    def load(self, *args, **kwargs):
        # ...
        artifacts_dir = self._get_artifacts_dir()
        model_path = os.path.join(artifacts_dir, 'optimizer_agent.zip')
        # model.load(model_path)
        # ... 