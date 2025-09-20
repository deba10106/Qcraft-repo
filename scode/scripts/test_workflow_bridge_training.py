import sys
import time
from circuit_designer.workflow_bridge import QuantumWorkflowBridge

def log_callback(msg, progress):
    # Print log message and show progress bar in terminal
    if progress is not None:
        bar_len = 40
        filled_len = int(round(bar_len * progress))
        bar = '=' * filled_len + '-' * (bar_len - filled_len)
        percent = int(progress * 100)
        sys.stdout.write(f"\r[{bar}] {percent}% | {msg}")
        sys.stdout.flush()
        if progress >= 1.0:
            print()
    else:
        print(msg)

def main():
    bridge = QuantumWorkflowBridge()
    print("Launching RL training via QuantumWorkflowBridge...\n")
    # Optionally set agent config here if needed
    # bridge.set_agent_config({...})
    try:
        result = bridge.train_multi_patch_rl_agent(log_callback=log_callback)
        print("\nTraining finished. Result:", result)
    except Exception as e:
        print(f"[ERROR] RL training failed: {e}")

if __name__ == "__main__":
    main()
