# Shared constants for RL environments (Surface and qLDPC)
# Centralizing these avoids divergence across environments and stabilizes SB3 interfaces.

MAX_PATCHES = 3      # Maximum number of patches supported by curriculum
MAX_QUBITS = 65      # Upper bound for hardware qubits across supported devices
NUM_FEATURES = 5     # Node feature dimensions used by observation space
