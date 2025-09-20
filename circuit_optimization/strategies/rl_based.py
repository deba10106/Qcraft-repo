import os
try:
    from stable_baselines3 import PPO
except ImportError:
    PPO = None
from circuit_optimization.rl_env import CircuitOptimizationEnvironment
from circuit_optimization.reward_engine import CircuitOptimizationRewardEngine
import yaml
import json

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
        # Use the RL environment's reset method to encode the circuit and device info
        obs = env.reset(circuit=circuit, device_info=device_info)
        return obs

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
        # Dynamically select provider and device from hardware.json
        with open('./configs/hardware.json', 'r') as f:
            hw = json.load(f)
        provider = hw['provider_name'].lower()
        device_name = hw['device_name']
        devices_yaml = f'./configs/{provider}_devices.yaml'
        device_info = load_device_info('./configs/hardware.json', devices_yaml)
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
                device_info=device_info,
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
        obs = self._circuit_to_obs(circuit, device_info, env)
        done = False
        while not done:
            action, _ = self.agent.predict(obs, deterministic=True)
            obs, reward, done, info = env.step(action)
            done = done[0] if isinstance(done, (list, tuple)) else done
        optimized_circuit = self._obs_to_circuit(obs, env)
        # Always convert to device native gates
        optimized_circuit = self._normalize_and_filter_gates(optimized_circuit, device_info)
        return optimized_circuit


    def train(self, *args, **kwargs):
        import time
        artifacts_dir = self._get_artifacts_dir()
        os.makedirs(artifacts_dir, exist_ok=True)
        # Dynamic artifact naming
        with open('./configs/hardware.json', 'r') as f:
            hw = json.load(f)
        provider = hw['provider_name'].lower()
        device_name = hw['device_name']
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        model_path = os.path.join(artifacts_dir, f'rl_optimizer_{provider}_{device_name}_{timestamp}.zip')
        # RL training loop with reward normalization and curriculum learning
        rl_env_conf = self.config.get('rl_config', {})
        reward_weights = rl_env_conf.get('reward_weights', None)
        normalize_reward = rl_env_conf.get('normalize_reward', False)
        curriculum = rl_env_conf.get('curriculum', None)
        # Only pass curriculum if enabled
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
        n_envs = rl_env_conf.get('n_envs', 1)
        if n_envs > 1:
            from stable_baselines3.common.vec_env import SubprocVecEnv
            env = SubprocVecEnv([make_env for _ in range(n_envs)])
        else:
            env = make_env()
        # PPO agent
        if PPO is None:
            raise ImportError("stable-baselines3 is required for RL-based optimization. Please install it.")
        agent = PPO('MlpPolicy', env, verbose=1, learning_rate=rl_env_conf.get('learning_rate', 0.0001))
        agent.learn(total_timesteps=rl_env_conf.get('num_episodes', 1000))
        agent.save(model_path)
        self.agent = agent
        print(f"[RLBasedOptimizer] Model saved to {model_path}")

    def load(self, *args, **kwargs):
        # ...
        artifacts_dir = self._get_artifacts_dir()
        model_path = os.path.join(artifacts_dir, 'optimizer_agent.zip')
        # model.load(model_path)
        # ... 