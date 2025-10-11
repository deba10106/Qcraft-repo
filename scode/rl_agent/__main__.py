# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import sys
raise SystemExit(
    "This entrypoint is deprecated. Launch training via the GUI or use scode/api.py::SurfaceCodeAPI.train_surface_code_agent() "
    "from your application."
)

# Utility for deep merging dicts (API > config)
def deep_merge(base: dict, override: dict) -> dict:
    return base

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
        code_family=env_cfg.get('code_family', 'surface'),
        layout_type=env_cfg['layout_type'],
        code_distance=env_cfg['code_distance'],
        patch_count=env_cfg['patch_count'],
        curriculum_stage=curriculum_stage,
        timestamp=timestamp
    )

def main():
    return

if __name__ == "__main__":
    main() 