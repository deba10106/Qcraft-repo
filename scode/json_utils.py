# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

import json
import datetime
import numpy as np

def json_default(obj):
    """
    Custom JSON serializer for objects not serializable by default json code.
    Handles numpy types and datetime/date objects.
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)
