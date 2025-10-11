# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# SPDX-FileCopyrightText: 2025 Dr. Debasis Mondal <deba10106@gmail.com>

# Shared constants for RL environments (Surface and qLDPC)
# Centralizing these avoids divergence across environments and stabilizes SB3 interfaces.

MAX_PATCHES = 3      # Maximum number of patches supported by curriculum
MAX_QUBITS = 65      # Upper bound for hardware qubits across supported devices
NUM_FEATURES = 5     # Node feature dimensions used by observation space
