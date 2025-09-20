import os
from configuration_management.config_manager import ConfigManager
from hardware_abstraction.device_abstraction import DeviceAbstraction
from scode.heuristic_layer.heuristic_initialization_layer import HeuristicInitializationLayer
from scode.graph_transformer.graph_transformer import ConnectivityAwareGraphTransformer
from .environment import SurfaceCodeEnvironment

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv
import time
from stable_baselines3.common.callbacks import BaseCallback
import sys
import yaml
from scode.rl_agent.reward_engine import MultiPatchRewardEngine
from scode.rl_agent.progress import ProgressReporter
from logging_results import LoggingResultsManager

# Utility for deep merging dicts (API > config)
def deep_merge(base: dict, override: dict) -> dict:
    if not override:
        return base.copy()
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

# Always use configs directory for all config files
ConfigManager.load_registry()
CONFIG_DIR = os.path.dirname(ConfigManager.config_registry['hardware'])
SURFACE_CODE_CONFIG = ConfigManager.config_registry['surface_code']

# --- Load config to get output_dir ---
base_config = ConfigManager.get_config('multi_patch_rl_agent')
output_dir = base_config.get('system', {}).get('output_dir', './outputs')
TRAINING_ARTIFACTS_DIR = os.path.abspath(os.path.join(output_dir, 'training_artifacts'))
os.makedirs(TRAINING_ARTIFACTS_DIR, exist_ok=True)

def make_env(config, device, reward_engine):
    h_layer = HeuristicInitializationLayer(config, device)
    return lambda: SurfaceCodeEnvironment(
        config=config,
        hardware_graph=device,
        surface_code_generator=h_layer,
        reward_engine=reward_engine
    )

def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_artifact_name(config, curriculum_stage):
    env_cfg = config['multi_patch_rl_agent']['environment']
    naming = config['multi_patch_rl_agent']['training_artifacts']['artifact_naming']
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    return naming.format(
        provider=env_cfg['provider'],
        device=env_cfg['device'],
        layout_type=env_cfg['layout_type'],
        code_distance=env_cfg['code_distance'],
        patch_count=env_cfg['patch_count'],
        curriculum_stage=curriculum_stage,
        timestamp=timestamp
    )

def main():
    config_path = os.environ.get('MULTI_PATCH_RL_CONFIG', 'configs/multi_patch_rl_agent.yaml')
    config = load_config(config_path)
    env_cfg = config['multi_patch_rl_agent']['environment']
    agent_cfg = config['multi_patch_rl_agent']['agent']
    curriculum_cfg = config['multi_patch_rl_agent']['curriculum_learning']
    artifact_dir = config['multi_patch_rl_agent']['training_artifacts']['output_dir']
    os.makedirs(artifact_dir, exist_ok=True)
    logger = LoggingResultsManager()
    run_id = f"rl_agent_{time.strftime('%Y%m%d_%H%M%S')}"
    logger.log_event('run_started', {'run_id': run_id, 'config_path': config_path, 'artifact_dir': artifact_dir}, level='INFO')
    # Curriculum learning
    stages = curriculum_cfg['stages'] if curriculum_cfg['enabled'] else [{'patch_count': env_cfg['patch_count']}]
    for stage_idx, stage in enumerate(stages):
        logger.log_event('curriculum_stage_started', {'run_id': run_id, 'stage_idx': stage_idx+1, 'stage': stage}, level='INFO')
        print(f"[INFO] Curriculum stage {stage_idx+1}/{len(stages)}: {stage}")
        # Update config for this stage
        env_cfg_stage = env_cfg.copy()
        env_cfg_stage['patch_count'] = stage['patch_count']
        config['multi_patch_rl_agent']['environment'] = env_cfg_stage
        # Initialize environment
        env = SurfaceCodeEnvironment(config['multi_patch_rl_agent'], {}, reward_engine=MultiPatchRewardEngine(config['multi_patch_rl_agent']))
        env.current_phase = stage_idx  # Ensure correct curriculum stage is used
        # Initialize agent
        policy = agent_cfg['policy']
        model = PPO(policy, env, **{k: v for k, v in agent_cfg.items() if k not in ['policy', 'resume_from_checkpoint', 'save_interval']})
        # Resume from checkpoint if specified
        if agent_cfg.get('resume_from_checkpoint'):
            print(f"[INFO] Resuming from checkpoint: {agent_cfg['resume_from_checkpoint']}")
            model = PPO.load(agent_cfg['resume_from_checkpoint'], env=env)
        # Train
        total_timesteps = stage.get('total_timesteps', agent_cfg['total_timesteps'])
        save_interval = agent_cfg.get('save_interval', 10000)
        from scode.rl_agent.progress import ProgressBarCallback
        progress_callback = ProgressBarCallback(
            total_steps=total_timesteps,
            bar_length=40,
            print_freq=2.0,
            callback=None,  # Set to a function if GUI callback is needed
            mode='both',
            logger=logger,
            run_id=run_id
        )
        for t in range(0, total_timesteps, save_interval):
            model.learn(total_timesteps=save_interval, reset_num_timesteps=False, callback=progress_callback)
            artifact_name = get_artifact_name(config, curriculum_stage=stage_idx+1)
            artifact_path = os.path.join(artifact_dir, artifact_name)
            print(f"[INFO] Saving checkpoint: {artifact_path}")
            model.save(artifact_path)
            logger.log_event('checkpoint_saved', {'run_id': run_id, 'artifact_path': artifact_path, 'step': t+save_interval}, level='INFO')
        reporter.finish()
        logger.log_event('curriculum_stage_completed', {'run_id': run_id, 'stage_idx': stage_idx+1}, level='INFO')
        print(f"[INFO] Finished stage {stage_idx+1}")
    logger.log_event('run_completed', {'run_id': run_id, 'artifact_dir': artifact_dir}, level='INFO')
    logger.store_result(run_id, {'artifact_dir': artifact_dir, 'config_path': config_path, 'status': 'completed'})
    print("[INFO] Multi-patch RL agent training complete.")

if __name__ == "__main__":
    main() 