"""Deterministic threshold/rate-of-change rules from the AlgaePool expert
questionnaire (Dominique Delobel, project memory: project-spirulinaai-m1).

Severity scale matches the expert's table: 1=info, 2=warning, 3=critique.
These run on a single snapshot (+ optionally the previous reading for
rate-of-change) and need no training data — they cover the anomalies the
expert already gave hard numbers for.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Finding:
    parameter: str
    severity: int  # 1=info, 2=warning, 3=critical
    label: str
    detail: str


def check_ph(value: float, prev_value: Optional[float] = None, minutes_since_prev: Optional[float] = None) -> list[Finding]:
    findings = []
    if value < 8.5 or value > 11.5:
        findings.append(Finding("pH", 3, "pH hors plage critique", f"pH={value:.2f} (seuil critique <8.5 ou >11.5)"))
    elif value < 9.5 or value > 11:
        findings.append(Finding("pH", 2, "pH hors plage optimale", f"pH={value:.2f} (optimal 9.5-11)"))

    if prev_value is not None and minutes_since_prev and minutes_since_prev > 0:
        rate_per_15min = abs(value - prev_value) / (minutes_since_prev / 15.0)
        if rate_per_15min >= 0.5:
            findings.append(Finding("pH", 3, "Variation de pH critique", f"Δ={rate_per_15min:.2f}/15min (seuil critique 0.5)"))
        elif rate_per_15min >= 0.3:
            findings.append(Finding("pH", 2, "Variation de pH rapide", f"Δ={rate_per_15min:.2f}/15min (seuil warning 0.3)"))
    return findings


def check_ec(value: float, prev_value: Optional[float] = None, minutes_since_prev: Optional[float] = None) -> list[Finding]:
    findings = []
    if value > 30.0:
        findings.append(Finding("EC", 3, "Conductivité critique (arrêt de croissance)", f"EC={value:.2f} mS/cm (>30 mS/cm)"))
    elif value < 10.0:
        findings.append(Finding("EC", 3, "Conductivité trop basse (dilution probable)", f"EC={value:.2f} mS/cm (<10 mS/cm)"))
    elif value < 15.0 or value > 22.0:
        findings.append(Finding("EC", 2, "Conductivité hors plage de démarrage", f"EC={value:.2f} mS/cm (plage 15-22)"))

    if prev_value is not None and minutes_since_prev and minutes_since_prev > 0:
        drop_per_hour = (prev_value - value) / (minutes_since_prev / 60.0)
        if drop_per_hour >= 3.0:
            findings.append(Finding("EC", 3, "Chute brutale de conductivité (accident dilution)", f"chute={drop_per_hour:.2f} mS/cm/h"))
    return findings


def check_temperature(value: float) -> list[Finding]:
    findings = []
    if value < 20.0 or value > 41.0:
        findings.append(Finding("Temperature", 3, "Température critique", f"T={value:.2f}°C (seuil critique <20 ou >41)"))
    elif value < 25.0:
        findings.append(Finding("Temperature", 2, "Croissance faible (température basse)", f"T={value:.2f}°C (<25°C)"))
    elif value < 34.0 or value > 39.0:
        findings.append(Finding("Temperature", 2, "Température hors plage optimale", f"T={value:.2f}°C (optimal 34-39)"))
    return findings


def check_do(value: float, is_daytime: bool) -> list[Finding]:
    findings = []
    if value < 4.0:
        # expert: low DO at night is an open question, don't treat with the same
        # severity as a daytime drop (photosynthesis should be pushing DO up by day)
        severity = 3 if is_daytime else 2
        label = "DO effondré (jour)" if is_daytime else "DO bas (nuit, à surveiller)"
        findings.append(Finding("DO", severity, label, f"DO={value:.2f} mg/L (<4.0)"))
    elif value < 6.0 or value > 9.0:
        findings.append(Finding("DO", 1, "DO hors plage optimale", f"DO={value:.2f} mg/L (optimal 6-9)"))
    return findings


def check_luminosite(value: float) -> list[Finding]:
    # expert: informational only, not actionable on its own (Q12)
    findings = []
    if value < 2000.0 or value > 50000.0:
        findings.append(Finding("Luminosite", 1, "Luminosité hors plage", f"L={value:.0f} lux (seuil <2000 ou >50000)"))
    return findings


def check_turbidite(value: float) -> list[Finding]:
    findings = []
    if value > 1.5 or value < 0.1:
        findings.append(Finding("Turbidite", 3, "Turbidité critique", f"OD680={value:.3f} (seuil critique >1.5 ou <0.1)"))
    elif value < 0.3 or value > 1.2:
        findings.append(Finding("Turbidite", 2, "Turbidité hors plage optimale", f"OD680={value:.3f} (optimal 0.3-1.2)"))
    return findings


def evaluate_rules(snapshot: dict, previous: Optional[dict] = None, minutes_since_prev: Optional[float] = None) -> list[Finding]:
    """snapshot: dict with keys pH, EC, DO_mgL, Temperature, Luminosite, and
    optionally Turbidite. previous: same shape, the prior reading set (for
    rate-of-change checks).

    Turbidite is optional: production's turbidity sensor reports NTU and no
    NTU->OD680 conversion exists yet, so callers without a calibrated value
    just omit the key -- skip that one check rather than KeyError."""
    findings: list[Finding] = []

    prev_ph = previous.get("pH") if previous else None
    prev_ec = previous.get("EC") if previous else None

    findings += check_ph(snapshot["pH"], prev_ph, minutes_since_prev)
    findings += check_ec(snapshot["EC"], prev_ec, minutes_since_prev)
    findings += check_temperature(snapshot["Temperature"])
    findings += check_do(snapshot["DO_mgL"], is_daytime=snapshot.get("Luminosite", 0.0) > 2000.0)
    findings += check_luminosite(snapshot["Luminosite"])
    if snapshot.get("Turbidite") is not None:
        findings += check_turbidite(snapshot["Turbidite"])

    return findings
