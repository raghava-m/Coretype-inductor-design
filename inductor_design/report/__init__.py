"""Human-readable design reports."""
from __future__ import annotations

from ..optimizer.search import DesignResult, DesignCandidate


def _fmt_si(value: float, unit: str, digits: int = 3) -> str:
    if value == 0:
        return f"0 {unit}"
    prefixes = [
        (1e9, "G"), (1e6, "M"), (1e3, "k"),
        (1.0, ""), (1e-3, "m"), (1e-6, "µ"),
        (1e-9, "n"), (1e-12, "p"),
    ]
    absv = abs(value)
    for scale, pre in prefixes:
        if absv >= scale:
            return f"{value/scale:.{digits}f} {pre}{unit}"
    return f"{value:.3e} {unit}"


def _fmt_candidate(c: DesignCandidate) -> str:
    lines = [
        f"- Core:             {c.core_name} ({c.material_name})",
        f"- Wire:             {c.wire_name}",
        f"- Turns:            {c.turns}",
        f"- Gap:              {c.gap_mm:.3f} mm"
        if c.gap_mm > 0 else "- Gap:              (distributed, powder)",
        f"- Inductance:       {_fmt_si(c.inductance_h, 'H')}",
        f"- B_peak / B_ac:    {c.b_peak_t:.3f} T / {c.b_ac_t:.3f} T",
        f"- Saturation margin:{c.saturation_margin*100:+.1f} %",
        f"- Fill factor:      {c.fill*100:.1f} %",
        f"- Core loss:        {c.p_core_w:.2f} W",
        f"- Winding loss:     {c.p_cu_w:.2f} W  (Fr = {c.winding_fr:.2f})",
        f"- Total loss:       {c.p_total_w:.2f} W",
        f"- ΔT / hotspot:     {c.temperature_rise_c:.1f} K / {c.hotspot_c:.1f} °C",
        f"- Volume / height:  {c.volume_mm3:.0f} mm³ / {c.height_mm:.1f} mm",
        f"- Est. cost:        $ {c.cost_usd:.2f}",
    ]
    return "\n".join(lines)


def render_markdown(result: DesignResult, max_alternatives: int = 5) -> str:
    s = result.spec_summary
    op = result.operating_point
    out: list[str] = []
    out.append(f"# Inductor design report — {s['topology'].upper()}")
    out.append("")
    out.append("## Converter spec")
    out.append(f"- Vin:    {s['vin'][0]} V to {s['vin'][1]} V")
    out.append(f"- Vout:   {s['vout']} V")
    out.append(f"- Iout:   {s['iout']} A")
    out.append(f"- fsw:    {_fmt_si(s['fsw'], 'Hz', digits=1)}")
    out.append(f"- ripple: {s['ripple_ratio']*100:.0f} %")
    out.append(f"- η:      {s['efficiency']*100:.0f} %")
    out.append("")
    out.append("## Derived operating point")
    out.append(f"- L_min required:    {_fmt_si(op['target_l'], 'H')}")
    out.append(f"- Duty range:        {op['duty_min']*100:.1f}% → {op['duty_max']*100:.1f}%")
    out.append(f"- ΔI_L pk-pk:        {op['delta_i']:.3f} A")
    out.append(f"- I_peak:            {op['i_peak']:.3f} A")
    out.append(f"- I_rms:             {op['i_rms']:.3f} A")
    out.append(f"- V·s (on-time):     {_fmt_si(op['volt_seconds'], 'V·s')}")
    out.append("")
    out.append("## Search summary")
    out.append(
        f"- Candidates evaluated: {result.all_candidates_evaluated}"
    )
    out.append(f"- Feasible designs:     {result.feasible_count}")
    out.append(f"- Pareto front size:    {len(result.pareto)}")
    out.append("")
    if result.best is None:
        out.append("## No feasible design found")
        out.append(
            "Try loosening max_temp_rise, increasing max_fill, or adding larger cores."
        )
        return "\n".join(out)
    out.append("## Recommended design")
    out.append("")
    out.append(_fmt_candidate(result.best))
    out.append("")
    if len(result.pareto) > 1:
        out.append("## Pareto alternatives")
        out.append("")
        for i, c in enumerate(result.pareto[1:max_alternatives+1], start=2):
            out.append(f"### Alternative {i}")
            out.append(_fmt_candidate(c))
            out.append("")
    return "\n".join(out)
