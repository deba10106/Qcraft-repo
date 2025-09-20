import sys
import time

from stable_baselines3.common.callbacks import BaseCallback
import sys
import time

class ProgressBarCallback(BaseCallback):
    """
    Modular SB3-compatible callback for terminal and callback-based RL training progress reporting.
    Can be extended or composed for GUI integration.
    """
    def __init__(self, total_steps, bar_length=40, print_freq=1.0, callback=None, mode='terminal', run_id=None):
        super().__init__()
        self.total_steps = total_steps
        self.bar_length = bar_length
        self.print_freq = print_freq
        self.callback = callback  # For GUI/API
        self.mode = mode  # 'terminal', 'callback', or 'both'
        self.run_id = run_id
        self.start_time = None
        self.last_print_time = None
        self.last_step = 0
        self.last_reward = None
        self.last_ler = None
        self.n_calls = 0  # For SB3 compatibility
        self.verbose = True  # Always verbose for dev


    def _on_training_start(self) -> None:
        self.start_time = time.time()
        self.last_print_time = self.start_time
        print("Training started")


    def _on_step(self) -> bool:
        self.n_calls += 1  # Required by SB3
        now = time.time()
        n = self.model.num_timesteps
        rewards = self.locals.get('rewards', [])
        infos = self.locals.get('infos', [])
        avg_reward = sum(rewards) / len(rewards) if rewards else None
        lers = [info.get('ler', None) or info.get('logical_error_rate', None) for info in infos if isinstance(info, dict)]
        lers = [ler for ler in lers if ler is not None]
        avg_ler = sum(lers) / len(lers) if lers else None
        progress = n / self.total_steps
        elapsed = now - self.start_time
        eta = (elapsed / progress - elapsed) if progress > 0 else 0
        eta_str = time.strftime('%H:%M:%S', time.gmtime(eta)) if progress > 0 else 'N/A'
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
        reward_str = f'Reward: {avg_reward:.3f}' if avg_reward is not None else ''
        ler_str = f'LER: {avg_ler:.5f}' if avg_ler is not None else ''
        filled_len = int(self.bar_length * progress)
        bar = '=' * filled_len + '>' + ' ' * (self.bar_length - filled_len - 1)
        progress_info = {
            "step": n,
            "total_steps": self.total_steps,
            "reward": avg_reward,
            "ler": avg_ler,
            "eta": eta,
            "elapsed": elapsed,
            "progress": progress,
            "msg": None
        }
        if self.mode in ('terminal', 'both'):
            self.callback(progress_info)
        self.last_print_time = now
        return True

    def _on_training_end(self) -> None:
        if self.mode in ('terminal', 'both'):
            sys.stdout.write('\n')
            sys.stdout.flush()
        print("Training ended")


    def update(self, step, reward=None, ler=None):
        now = time.time()
        progress = step / self.total_steps
        elapsed = now - self.start_time
        eta = (elapsed / progress - elapsed) if progress > 0 else 0
        eta_str = time.strftime('%H:%M:%S', time.gmtime(eta)) if progress > 0 else 'N/A'
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
        self.last_step = step
        if reward is not None:
            self.last_reward = reward
        if ler is not None:
            self.last_ler = ler
        reward_str = f'Reward: {self.last_reward:.3f}' if self.last_reward is not None else ''
        ler_str = f'LER: {self.last_ler:.3e}' if self.last_ler is not None else ''
        # Terminal progress bar
        filled_len = int(self.bar_length * progress)
        bar = '=' * filled_len + '>' + ' ' * (self.bar_length - filled_len - 1)
        sys.stdout.write(
            f'\r[{bar}] {progress*100:6.2f}% | Step: {step}/{self.total_steps} | Elapsed: {elapsed_str} | ETA: {eta_str} | {reward_str} {ler_str}   '
        )
        sys.stdout.flush()
        progress_info = {
            "step": step,
            "total_steps": self.total_steps,
            "reward": self.last_reward,
            "ler": self.last_ler,
            "eta": eta,
            "elapsed": elapsed,
            "progress": progress
        }
        print(f"[DEBUG] Progress callback: {progress_info}")
        if self.callback:
            self.callback(progress_info)
        self.last_print_time = now

    def finish(self):
        if self.mode in ('terminal', 'both'):
            sys.stdout.write('\n')
            sys.stdout.flush()