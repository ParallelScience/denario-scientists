# Damped Harmonic Oscillator Dataset

## File location

The dataset is a NumPy structured array saved at:

    /home/node/data/damped_oscillators.npy

## How to load

```python
import numpy as np
data = np.load("/home/node/data/damped_oscillators.npy", allow_pickle=False)

# Access columns by name:
t = data['time']
x = data['displacement']
v = data['velocity']
osc_ids = data['oscillator_id']

# Filter to a single oscillator:
mask = data['oscillator_id'] == 1
osc1 = data[mask]
```

## Contents

The file contains 10,000 rows (20 oscillators x 500 time steps) as a NumPy
structured array with the following fields:

| Field                | Type    | Unit     | Description                                     |
|----------------------|---------|----------|-------------------------------------------------|
| oscillator_id        | int32   | —        | Integer identifier (1–20)                       |
| time                 | float64 | s        | Time from 0 to 20 seconds                       |
| displacement         | float64 | m        | Position x(t) with Gaussian measurement noise   |
| velocity             | float64 | m/s      | Velocity dx/dt with Gaussian measurement noise  |
| mass_kg              | float64 | kg       | Oscillator mass (0.1–10 kg)                     |
| spring_constant      | float64 | N/m      | Spring constant k = m * omega^2                 |
| damping_coefficient  | float64 | kg/s     | Damping coefficient b = 2 * m * gamma           |
| natural_frequency    | float64 | rad/s    | Angular frequency omega (0.5–5 rad/s)           |
| damping_ratio        | float64 | —        | gamma / omega (all < 1, i.e. underdamped)       |
| initial_amplitude    | float64 | m        | Initial amplitude A (0.5–3 m)                   |
| initial_phase        | float64 | rad      | Initial phase phi (0–2*pi)                      |
| kinetic_energy       | float64 | J        | 0.5 * m * v^2 (instantaneous)                   |
| potential_energy     | float64 | J        | 0.5 * k * x^2 (instantaneous)                   |
| total_energy         | float64 | J        | KE + PE (should decay due to damping)           |

## Physics model

Each oscillator follows the damped harmonic oscillator equation:

    x(t) = A * exp(-gamma * t) * cos(omega * t + phi) + noise

where gamma is the damping rate and omega is the natural frequency.
All 20 oscillators are underdamped (damping_ratio < 1).

## Hardware constraints

- Linux container (Debian Bookworm, x86_64)
- Maximum 4 CPU cores for parallel workloads
- No computation should run for more than 2 minutes
- No GPU / no CUDA — do not use CUDA-dependent libraries
- For PyTorch: use device='cpu' only
- Keep memory usage under 8 GB
