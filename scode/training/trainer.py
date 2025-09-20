import os
from stable_baselines3 import PPO
from stable_baselines3.common.base_algorithm import BaseAlgorithm

class Trainer:
    def __init__(self, config, env, verbose=True):
        self.config = config
        self.env = env
        self.verbose = verbose

    def save_model(self, model: BaseAlgorithm, stage: int) -> str:
        """
        Save the trained model with proper naming convention.
        """
        # Get config values
        output_dir = self.config.training_artifacts.output_dir
        naming_pattern = self.config.training_artifacts.naming_pattern
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Format filename using config pattern
        filename = naming_pattern.format(
            provider=self.config.hardware.provider,
            device=self.config.hardware.device,
            layout_type=self.config.surface_code.layout_type,
            code_distance=self.config.surface_code.code_distance,
            patch_count=self.config.surface_code.patch_count,
            stage=stage
        )
        
        # Full path for saving
        save_path = os.path.join(output_dir, filename)
        
        # Save the model
        model.save(save_path)
        
        if self.verbose:
            print(f"[TRAINER] Saved model to {save_path}")
        
        return save_path

    def train(self) -> BaseAlgorithm:
        """
        Train the RL agent using curriculum learning.
        """
        model = None
        
        # Get curriculum stages from config
        stages = self.config.curriculum.stages
        
        for stage in range(1, stages + 1):
            if self.verbose:
                print(f"[TRAINER] Starting curriculum stage {stage}/{stages}")
            
            # Update environment with stage-specific settings
            self.env.set_curriculum_stage(stage)
            
            # Create or load model
            if model is None:
                model = PPO(
                    policy="MlpPolicy",
                    env=self.env,
                    verbose=1 if self.verbose else 0,
                    **self.config.algorithm.ppo_params
                )
            
            # Train for this stage
            model.learn(
                total_timesteps=self.config.curriculum.timesteps_per_stage,
                reset_num_timesteps=False  # Continue counting timesteps across stages
            )
            
            # Save after each stage
            save_path = self.save_model(model, stage)
            
            if self.verbose:
                print(f"[TRAINER] Completed stage {stage}, model saved to {save_path}")
        
        return model 