import os
from scode.heuristic_layer.config_loader import ConfigLoader
from .evaluation_framework import EvaluationFramework
import yaml

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '../configs')
SURFACE_CODE_CONFIG = os.path.join(CONFIG_DIR, 'surface_code_config.yaml')
HARDWARE_CONFIG = os.path.join(CONFIG_DIR, 'hardware.json')


def main():
    # Load config and hardware
    config = ConfigLoader.load_yaml(SURFACE_CODE_CONFIG)
    with open(HARDWARE_CONFIG, 'r') as f:
        hardware = yaml.safe_load(f)
    evaluator = EvaluationFramework(config)
    # Example: load a real layout (replace with actual path or generator as needed)
    layout_path = os.path.join(CONFIG_DIR, 'example_layout.yaml')
    if os.path.exists(layout_path):
        with open(layout_path, 'r') as f:
            layout = yaml.safe_load(f)
    else:
        print("No example layout found. Please provide a real layout YAML file.")
        return
    noise_model = hardware.get('noise_model', {})
    # Comprehensive validation
    result = evaluator.comprehensive_validate_layout(layout, hardware, noise_model)
    print("Comprehensive Validation Result:")
    print(result)
    # Run evaluation scenario
    scenario = {'layout': layout, 'hardware': hardware, 'noise_model': noise_model}
    scenario_results = evaluator.run_evaluation_scenarios([scenario])
    print("Evaluation Scenario Results:")
    print(scenario_results)
    # Baseline comparison (if baseline available)
    baseline_path = os.path.join(CONFIG_DIR, 'baseline_layout.yaml')
    if os.path.exists(baseline_path):
        with open(baseline_path, 'r') as f:
            baseline = yaml.safe_load(f)
        baseline_result = evaluator.comprehensive_validate_layout(baseline, hardware, noise_model)
        comparison = evaluator.compare_against_baseline(result, baseline_result)
        print("Comparison Against Baseline:")
        print(comparison)

if __name__ == '__main__':
    main() 