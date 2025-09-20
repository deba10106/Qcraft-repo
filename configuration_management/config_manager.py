import os
import yaml
import json
from .schema_validator import SchemaValidator
import importlib.resources

class ConfigManager:
    config_registry = {}
    env_path = '.env'
    _env_cache = None

    @classmethod
    def load_registry(cls):
        """Load the config registry mapping module names to config file paths."""
        try:
            with importlib.resources.open_text('configs', 'config_registry.yaml') as f:
                cls.config_registry = yaml.safe_load(f)['config_registry']
        except (FileNotFoundError, ModuleNotFoundError):
            # Fallback for dev mode
            local_path = os.path.join(os.path.dirname(__file__), '../../configs/config_registry.yaml')
            with open(local_path, 'r') as f:
                cls.config_registry = yaml.safe_load(f)['config_registry']

    @classmethod
    def load_config(cls, module_name, config_path=None):
        """Load a YAML or JSON config for a module."""
        if not config_path:
            config_path = cls.config_registry.get(module_name)
        # If the config is in the package (configs/), use importlib.resources
        if config_path and os.path.basename(os.path.dirname(config_path)) == 'configs':
            fname = os.path.basename(config_path)
            try:
                from importlib.resources import files
                if fname.endswith('.yaml') or fname.endswith('.yml'):
                    hw_path = files('configs').joinpath(fname)
                    with hw_path.open('r') as f:
                        return yaml.safe_load(f)
                elif fname.endswith('.json'):
                    hw_path = files('configs').joinpath(fname)
                    with hw_path.open('r') as f:
                        return json.load(f)
            except (FileNotFoundError, ModuleNotFoundError, AttributeError, ImportError):
                pass  # fallback to open below
        # Fallback to filesystem
        if config_path.endswith('.yaml') or config_path.endswith('.yml'):
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        elif config_path.endswith('.json'):
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            raise ValueError("Unsupported config file format.")

    @classmethod
    def get_config(cls, module_name):
        """Get the current config for a module."""
        return cls.load_config(module_name)

    @classmethod
    def update_config(cls, module_name, updates):
        """Update a config for a module and save it. Notifies frontend if registered."""
        if not cls.config_registry:
            cls.load_registry()
        if module_name not in cls.config_registry:
            raise KeyError(f"Module '{module_name}' not found in config_registry. Please check configs/config_registry.yaml.")
        config = cls.get_config(module_name)
        config.update(updates)
        cls.save_config(module_name, config_path=None, config=config)
        cls._notify_config_change(module_name, config)

    @classmethod
    def get_user_config_path(cls, fname):
        """Return a user-writable config path for fname (e.g., ~/.qcraft/configs/fname)."""
        user_dir = os.path.expanduser('~/.qcraft/configs')
        os.makedirs(user_dir, exist_ok=True)
        return os.path.join(user_dir, fname)

    @classmethod
    def save_config(cls, module_name, config_path=None, config=None):
        """Save a config for a module to file. If the config is in the installed package, redirect to user config dir."""
        if not cls.config_registry:
            cls.load_registry()
        if not config_path:
            config_path = cls.config_registry.get(module_name)
        if config_path is None:
            raise KeyError(f"Module '{module_name}' not found in config_registry. Please check configs/config_registry.yaml.")
        if config is None:
            config = cls.get_config(module_name)
        # If the config path is in site-packages or not writable, redirect to user config dir
        fname = os.path.basename(config_path)
        try:
            # Try to write to the original path
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                with open(config_path, 'w') as f:
                    yaml.safe_dump(config, f)
            elif config_path.endswith('.json'):
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
            else:
                raise ValueError("Unsupported config file format.")
        except (PermissionError, FileNotFoundError, OSError):
            # Fallback: write to user config dir
            user_path = cls.get_user_config_path(fname)
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                with open(user_path, 'w') as f:
                    yaml.safe_dump(config, f)
            elif config_path.endswith('.json'):
                with open(user_path, 'w') as f:
                    json.dump(config, f, indent=2)
            else:
                raise ValueError("Unsupported config file format.")

    @classmethod
    def list_configs(cls):
        """List all registered config modules/files."""
        return list(cls.config_registry.keys())

    @classmethod
    def load_hardware_json(cls, path=None):
        """Load hardware.json specifying provider_name and device_name."""
        if not path:
            path = cls.config_registry.get('hardware')
        fname = os.path.basename(path)
        try:
            with importlib.resources.open_text('configs', fname) as f:
                return json.load(f)
        except (FileNotFoundError, ModuleNotFoundError):
            with open(path, 'r') as f:
                return json.load(f)

    @classmethod
    def update_hardware_json(cls, updates):
        """Update hardware.json with new provider/device selection. Writes to user config dir if needed."""
        path = cls.config_registry.get('hardware')
        fname = os.path.basename(path)
        try:
            hardware = cls.load_hardware_json(path)
        except Exception:
            hardware = {}
        hardware.update(updates)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump(hardware, f, indent=2)
        except (PermissionError, FileNotFoundError, OSError):
            user_path = cls.get_user_config_path(fname)
            with open(user_path, 'w') as f:
                json.dump(hardware, f, indent=2)

    @classmethod
    def resolve_device_config(cls, provider_name):
        """Return the path to the provider-specific device config file."""
        key = f'{provider_name}_devices'
        return cls.config_registry.get(key)

    @classmethod
    def validate_config(cls, module_name, schema_path=None):
        """Validate a config against a schema."""
        config = cls.get_config(module_name)
        # Prefer package/resource-aware schema loading
        try:
            schema = cls.get_schema(module_name)
        except Exception:
            schema = None
        # If explicit schema_path is provided, try to load from there
        if schema is None and schema_path:
            try:
                from .schema_validator import SchemaValidator as _SV
                return _SV.validate(config, schema_path)
            except Exception:
                return True  # Missing schema: treat as valid
        if schema is None:
            return True  # No schema found: treat as valid
        from .schema_validator import SchemaValidator as _SV
        return _SV.validate_with_schema(config, schema)

    @classmethod
    def get_schema(cls, module_name):
        """Get the schema for a module's config."""
        # Try to load schema from package or local filesystem robustly
        schema_fname = f'{module_name}.schema.yaml'
        try:
            import importlib.resources
            # Try package-based access first
            try:
                with importlib.resources.open_text('schemas', schema_fname) as f:
                    return yaml.safe_load(f)
            except (FileNotFoundError, ModuleNotFoundError):
                pass
            # Fallback to absolute path
            abs_path = os.path.join(os.path.dirname(__file__), '../schemas', schema_fname)
            if os.path.exists(abs_path):
                with open(abs_path, 'r') as f:
                    return yaml.safe_load(f)
            # Fallback to project root
            abs_path2 = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../schemas', schema_fname))
            if os.path.exists(abs_path2):
                with open(abs_path2, 'r') as f:
                    return yaml.safe_load(f)
            raise FileNotFoundError(f"Schema file not found: {schema_fname}")
        except Exception as e:
            raise RuntimeError(f"Failed to load schema for {module_name}: {e}")

    @classmethod
    def get_outputs_dir(cls):
        """Return the absolute path to the outputs directory (for results, metrics, etc.)."""
        return os.path.abspath('outputs')

    @classmethod
    def get_training_artifacts_dir(cls):
        """Return the absolute path to the training_artifacts directory (for RL models, etc.)."""
        return os.path.abspath('training_artifacts')

    @classmethod
    def ensure_output_dirs(cls):
        """Ensure that outputs and training_artifacts directories exist."""
        os.makedirs(cls.get_outputs_dir(), exist_ok=True)
        os.makedirs(cls.get_training_artifacts_dir(), exist_ok=True)

    # --- PySide6/Frontend Integration ---
    _config_change_callbacks = []

    @classmethod
    def register_config_change_callback(cls, callback):
        """Register a callback to be called when any config is updated (for frontend live reload)."""
        if callback not in cls._config_change_callbacks:
            cls._config_change_callbacks.append(callback)

    @classmethod
    def _notify_config_change(cls, module_name, config):
        """Notify all registered callbacks of a config change."""
        for cb in cls._config_change_callbacks:
            try:
                cb(module_name, config)
            except Exception as e:
                print(f"ConfigManager callback error: {e}")

    @classmethod
    def hot_reload_config(cls, module_name):
        """Reload a config from disk (for frontend live reload)."""
        return cls.get_config(module_name)

    # --- .env API Key Management ---
    @classmethod
    def ensure_env_file(cls):
        if not os.path.exists(cls.env_path):
            with open(cls.env_path, 'w') as f:
                f.write('# Provider API keys\n')
                f.write('# Example:\n')
                f.write('# ibm_api_key: your_ibm_api_key_here\n')
                f.write('# ionq_api_key: your_ionq_api_key_here\n')

    @classmethod
    def load_env(cls):
        cls.ensure_env_file()
        env = {}
        with open(cls.env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if ':' in line:
                    k, v = line.split(':', 1)
                    env[k.strip()] = v.strip()
        cls._env_cache = env
        return env

    @classmethod
    def get_api_key(cls, provider_name):
        env = cls._env_cache or cls.load_env()
        key = f'{provider_name}_api_key'
        return env.get(key)

    @classmethod
    def set_api_key(cls, provider_name, api_key):
        env = cls._env_cache or cls.load_env()
        key = f'{provider_name}_api_key'
        env[key] = api_key
        cls.save_env(env)

    @classmethod
    def save_env(cls, env):
        with open(cls.env_path, 'w') as f:
            f.write('# Provider API keys\n')
            for k, v in env.items():
                f.write(f'{k}: {v}\n')
        cls._env_cache = env 