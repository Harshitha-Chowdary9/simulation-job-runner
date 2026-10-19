import pytest

from simrunner.simulation import (
    SimulationError,
    SimulationParams,
    check_params,
    solve_heat_1d,
    stability_ratio,
)


class TestValidation:
    def test_defaults_are_stable_and_valid(self):
        check_params(SimulationParams())

    def test_unstable_grid_rejected(self):
        p = SimulationParams(dt=100.0)  # huge dt breaks the CFL condition
        with pytest.raises(SimulationError, match="unstable"):
            check_params(p)

    @pytest.mark.parametrize("field,value", [
        ("nx", 2), ("steps", 0), ("diffusivity", 0.0), ("dt", -1.0),
    ])
    def test_invalid_values_rejected(self, field, value):
        with pytest.raises(SimulationError):
            check_params(SimulationParams(**{field: value}))

    def test_unknown_parameter_rejected(self):
        with pytest.raises(SimulationError, match="unknown"):
            SimulationParams.from_dict({"nx": 10, "bogus": 1})


class TestSolver:
    def test_uniform_field_stays_uniform(self):
        p = SimulationParams(left_temp=50.0, right_temp=50.0, initial_temp=50.0)
        out = solve_heat_1d(p)
        assert out["final_min"] == pytest.approx(50.0)
        assert out["final_max"] == pytest.approx(50.0)

    def test_heat_diffuses_from_hot_end(self):
        p = SimulationParams(left_temp=100.0, right_temp=0.0, initial_temp=20.0)
        out = solve_heat_1d(p)
        assert out["final_mean"] > 20.0          # interior warms up
        assert out["final_max"] <= 100.0         # no overshoot beyond boundary
        assert out["stability_ratio"] <= 0.5

    def test_result_is_json_serialisable_summary(self):
        import json
        out = solve_heat_1d(SimulationParams(nx=30, steps=50))
        json.dumps(out)
        assert set(out) == {"nx", "steps", "stability_ratio", "final_min",
                            "final_max", "final_mean", "profile"}
