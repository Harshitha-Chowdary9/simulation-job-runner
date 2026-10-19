"""The "simulation": a 1D heat-conduction solver (explicit finite differences).

Deliberately small but real numerics, in the spirit of a heat/fluid
simulation backend: given a rod with fixed end temperatures, advance the
temperature field in time and return a compact result summary.

Scheme: FTCS (forward time, centered space). Stability requires
    r = alpha * dt / dx^2 <= 0.5
which the validate workflow step enforces - an unstable grid is a user
error, not something to silently "fix".
"""

from __future__ import annotations

from dataclasses import dataclass


class SimulationError(ValueError):
    """The requested simulation is not physically/numerically valid."""


@dataclass(frozen=True)
class SimulationParams:
    nx: int = 50               # grid points along the rod
    steps: int = 400           # time steps
    diffusivity: float = 0.01  # thermal diffusivity alpha
    dt: float = 0.01           # time step size (keeps default grid stable: r=0.24)
    left_temp: float = 100.0   # fixed temperature at x=0
    right_temp: float = 0.0    # fixed temperature at x=L
    initial_temp: float = 20.0 # interior initial temperature

    @classmethod
    def from_dict(cls, raw: dict) -> "SimulationParams":
        known = set(cls.__dataclass_fields__)
        sim_keys = {k: v for k, v in raw.items() if not k.startswith("_")}
        unknown = set(sim_keys) - known
        if unknown:
            raise SimulationError(f"unknown parameters: {sorted(unknown)}")
        # Underscore-prefixed keys are control/chaos knobs for the workflow
        # engine, not simulation parameters.
        return cls(**sim_keys)


def stability_ratio(p: SimulationParams) -> float:
    dx = 1.0 / (p.nx - 1)
    return p.diffusivity * p.dt / (dx * dx)


def check_params(p: SimulationParams) -> None:
    if p.nx < 3:
        raise SimulationError("nx must be >= 3")
    if p.steps < 1:
        raise SimulationError("steps must be >= 1")
    if p.diffusivity <= 0:
        raise SimulationError("diffusivity must be positive")
    if p.dt <= 0:
        raise SimulationError("dt must be positive")
    if p.nx > 2000 or p.steps > 200_000:
        raise SimulationError("grid too large for this demo service")
    r = stability_ratio(p)
    if r > 0.5:
        raise SimulationError(
            f"unstable grid: alpha*dt/dx^2 = {r:.3f} > 0.5; reduce dt or diffusivity"
        )


def solve_heat_1d(p: SimulationParams) -> dict:
    """Run the FTCS scheme and return a compact, JSON-serialisable summary."""
    check_params(p)
    dx = 1.0 / (p.nx - 1)
    r = p.diffusivity * p.dt / (dx * dx)

    u = [p.initial_temp] * p.nx
    u[0], u[-1] = p.left_temp, p.right_temp

    for _ in range(p.steps):
        unew = u[:]
        for i in range(1, p.nx - 1):
            unew[i] = u[i] + r * (u[i + 1] - 2 * u[i] + u[i - 1])
        u = unew
        u[0], u[-1] = p.left_temp, p.right_temp

    interior = u[1:-1]
    return {
        "nx": p.nx,
        "steps": p.steps,
        "stability_ratio": round(r, 6),
        "final_min": round(min(interior), 6),
        "final_max": round(max(interior), 6),
        "final_mean": round(sum(interior) / len(interior), 6),
        # Downsampled profile for quick plotting/inspection.
        "profile": [round(v, 4) for v in u[:: max(1, p.nx // 10)]],
    }
