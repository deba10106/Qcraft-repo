# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import yaml
import jsonschema

class SchemaValidator:
    @staticmethod
    def validate(config, schema_path):
        """Validate a config dict against a YAML/JSON schema."""
        with open(schema_path, 'r') as f:
            schema = yaml.safe_load(f)
        try:
            jsonschema.validate(instance=config, schema=schema)
            return True
        except jsonschema.ValidationError as e:
            print(f"Validation error: {e}")
            return False

    @staticmethod
    def validate_with_schema(config, schema: dict):
        """Validate a config dict against a provided schema dict."""
        try:
            jsonschema.validate(instance=config, schema=schema)
            return True
        except jsonschema.ValidationError as e:
            print(f"Validation error: {e}")
            return False

    @staticmethod
    def load_schema(schema_path):
        """Load a YAML/JSON schema from file."""
        with open(schema_path, 'r') as f:
            return yaml.safe_load(f) 