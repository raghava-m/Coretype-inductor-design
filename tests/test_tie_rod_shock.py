"""Unit checks for tie-rod shock sizing (stdlib unittest)."""

from __future__ import annotations

import math
import unittest

from mechanical.tie_rod_shock import (
    G,
    ShockInputs,
    evaluate_rod,
    format_report,
    rod_loads,
    shank_diameter_for_bending_mm,
    shock_forces,
    size_tie_rods,
)


class TestShockForces(unittest.TestCase):
    def test_200kg_5g_20ms_half_sine(self) -> None:
        f = shock_forces(ShockInputs())
        self.assertAlmostEqual(f.weight_N, 200.0 * G, places=6)
        self.assertAlmostEqual(f.F_shock_N, 200.0 * 5.0 * G, places=6)
        self.assertAlmostEqual(f.F_vertical_down_N, 200.0 * 6.0 * G, places=6)
        self.assertAlmostEqual(f.F_vertical_up_N, 200.0 * 4.0 * G, places=6)
        self.assertAlmostEqual(f.F_lateral_N, 9810.0, places=1)
        # Δv = 2 a τ / π  for half-sine
        a = 5.0 * G
        tau = 0.020
        self.assertAlmostEqual(f.delta_v_m_s, 2.0 * a * tau / math.pi, places=6)
        self.assertAlmostEqual(f.impulse_N_s, 200.0 * f.delta_v_m_s, places=6)
        self.assertAlmostEqual(f.pulse_Hz, 25.0, places=6)

    def test_rectangular_impulse(self) -> None:
        f = shock_forces(ShockInputs(waveform="rectangular"))
        self.assertAlmostEqual(f.delta_v_m_s, 5.0 * G * 0.020, places=6)

    def test_rejects_bad_duration(self) -> None:
        with self.assertRaises(ValueError):
            shock_forces(ShockInputs(duration_ms=0.0))


class TestRodLoads(unittest.TestCase):
    def test_portal_bending_fixed_fixed(self) -> None:
        inp = ShockInputs(
            share_factor=1.0,
            shear_share=1.0,
            end_fixity="fixed_fixed",
            rods_resist_overturning=False,
            cg_ecc_x_mm=0.0,
            cg_ecc_y_mm=0.0,
            rod_ecc_mm=0.0,
            n_rods=4,
            free_length_mm=400.0,
            assume_shear_keys=True,
        )
        forces = shock_forces(inp)
        loads = rod_loads(inp, forces)
        V = forces.F_lateral_N / 4.0
        self.assertAlmostEqual(loads.M_portal_Nm, V * 0.400 / 2.0, places=6)
        self.assertAlmostEqual(loads.M_portal_Nm, 490.5, places=1)
        # Keys assumed → that moment is not applied to the rod.
        self.assertAlmostEqual(loads.V_shear_N, 0.0, places=6)
        self.assertAlmostEqual(loads.M_design_Nm, 0.0, places=6)

    def test_cantilever_is_double_the_portal_moment(self) -> None:
        base = ShockInputs(
            share_factor=1.0,
            shear_share=1.0,
            rod_ecc_mm=0.0,
            cg_ecc_x_mm=0.0,
            n_rods=4,
            free_length_mm=400.0,
        )
        f = shock_forces(base)
        m_ff = rod_loads(ShockInputs(**{**base.__dict__, "end_fixity": "fixed_fixed"}), f)
        m_c = rod_loads(ShockInputs(**{**base.__dict__, "end_fixity": "cantilever"}), f)
        self.assertAlmostEqual(m_c.M_portal_Nm, 2.0 * m_ff.M_portal_Nm, places=6)

    def test_single_rod_warning(self) -> None:
        result = size_tie_rods(ShockInputs(n_rods=1))
        self.assertTrue(any("Fewer than 4" in w for w in result["warnings"]))

    def test_overturning_adds_axial_when_enabled(self) -> None:
        inp = ShockInputs(
            rods_resist_overturning=True,
            share_factor=1.0,
            cg_ecc_x_mm=0.0,
            cg_ecc_y_mm=0.0,
            n_rods=4,
            spacing_x_mm=300.0,
            spacing_y_mm=200.0,
            h_cg_mm=250.0,
        )
        f = shock_forces(inp)
        loads = rod_loads(inp, f)
        # M = F h = 9810 * 0.25. Narrower rod spacing (Y = 200 mm) governs.
        M = 9810.0 * 0.25
        f_ot_x = M * 0.15 / (4.0 * 0.15**2)
        f_ot_y = M * 0.10 / (4.0 * 0.10**2)
        self.assertAlmostEqual(loads.F_axial_overturning_N, max(f_ot_x, f_ot_y), places=1)
        self.assertAlmostEqual(loads.F_axial_overturning_N, 6131.25, places=1)
        self.assertGreater(loads.F_axial_design_N, loads.F_axial_vertical_N)


class TestSizing(unittest.TestCase):
    def test_default_recommends_m12_with_keys(self) -> None:
        result = size_tie_rods(ShockInputs())
        passing = [c["size"] for c in result["candidates"] if c["passes"]]
        self.assertIn("M12", passing)
        self.assertEqual(result["recommended_size"], "M12")
        self.assertAlmostEqual(result["loads"]["M_portal_Nm"], 490.5, places=1)

    def test_without_keys_needs_m24_or_larger(self) -> None:
        result = size_tie_rods(ShockInputs(assume_shear_keys=False, min_size="M8"))
        passing = [c["size"] for c in result["candidates"] if c["passes"]]
        self.assertNotIn("M12", passing)
        self.assertNotIn("M16", passing)
        self.assertIn(result["recommended_size"], ("M24", "M30"))

    def test_axial_only_allows_smaller_rod(self) -> None:
        # If the core/friction takes shear, bending vanishes and M12 8.8 passes.
        result = size_tie_rods(
            ShockInputs(
                shear_share=0.0,
                rod_ecc_mm=0.0,
                cg_ecc_x_mm=0.0,
                preload_N=8000.0,
                clamp_pressure_MPa=0.0,
            )
        )
        passing = [c["size"] for c in result["candidates"] if c["passes"]]
        self.assertIn("M12", passing)

    def test_report_contains_key_numbers(self) -> None:
        text = format_report(size_tie_rods(ShockInputs()))
        self.assertIn("9.81 kN", text)
        self.assertIn("Portal BM", text)
        self.assertIn("Recommended rod", text)
        self.assertIn("M12", text)

    def test_unknown_grade_rejected(self) -> None:
        with self.assertRaises(ValueError):
            size_tie_rods(ShockInputs(grade="12.9"))

    def test_stainless_is_weaker_than_88(self) -> None:
        steel = size_tie_rods(ShockInputs(grade="8.8"))
        sst = size_tie_rods(ShockInputs(grade="A2-70"))
        # Same geometry: stainless utilisation must be higher.
        u_st = next(c["utilization"] for c in steel["candidates"] if c["size"] == "M16")
        u_ss = next(c["utilization"] for c in sst["candidates"] if c["size"] == "M16")
        self.assertGreater(u_ss, u_st)

    def test_evaluate_uses_thread_root(self) -> None:
        inp = ShockInputs(assume_shear_keys=False, shear_share=1.0, preload_N=10000.0)
        f = shock_forces(inp)
        loads = rod_loads(inp, f)
        rod = {"size": "M16", "d_mm": 16.0, "d3_mm": 13.546, "As_mm2": 157.0}
        cand = evaluate_rod(inp, loads, rod)
        self.assertGreater(cand.sigma_bending_MPa, 1000.0)  # 491 N·m on M16 root
        self.assertGreater(cand.sigma_vm_MPa, cand.sigma_axial_MPa)
        self.assertFalse(cand.passes)

    def test_shank_for_portal_moment(self) -> None:
        d = shank_diameter_for_bending_mm(490.5, 640e6 / 1.5)
        self.assertAlmostEqual(d, 22.7, delta=0.2)


if __name__ == "__main__":
    unittest.main()
