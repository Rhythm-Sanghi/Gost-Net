"""
Gost-Net - Adaptive Modulation and Coding (AMC) & Link Adaptation Engine
Phase 15 Subsystem: Dynamic physical/link-layer rate adaptation based on Channel State
Information (CSI), Signal-to-Interference-plus-Noise Ratio (SINR / SNR), and packet error rate.
Supports multi-constellation switching (BPSK, QPSK, 16-QAM, 64-QAM, LoRa SF7-SF12),
hysteresis-filtered state transitions to avoid ping-pong oscillation, Shannon capacity
computation, and closed-loop Channel Quality Indicator (CQI) reporting.
"""

import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModulationProfile:
    name: str
    bits_per_symbol: int
    code_rate_num: int
    code_rate_den: int
    min_snr_db: float
    cqi_index: int
    is_lora: bool = False

    @property
    def code_rate(self) -> float:
        return self.code_rate_num / self.code_rate_den

    @property
    def spectral_efficiency(self) -> float:
        """Spectral efficiency in bits/second/Hz."""
        return self.bits_per_symbol * self.code_rate


# Standard Tactical Modulation and Coding Profiles ordered by ascending required SNR
TACTICAL_PROFILES: List[ModulationProfile] = [
    # LoRa Spread Spectrum Modes (for extreme noise/jamming)
    ModulationProfile("LORA_SF12", bits_per_symbol=1, code_rate_num=1, code_rate_den=2, min_snr_db=-20.0, cqi_index=1, is_lora=True),
    ModulationProfile("LORA_SF10", bits_per_symbol=1, code_rate_num=2, code_rate_den=3, min_snr_db=-15.0, cqi_index=2, is_lora=True),
    ModulationProfile("LORA_SF7",  bits_per_symbol=1, code_rate_num=4, code_rate_den=5, min_snr_db=-7.5,  cqi_index=3, is_lora=True),
    # Narrowband Digital Tactical Modulations
    ModulationProfile("BPSK_1_2",  bits_per_symbol=1, code_rate_num=1, code_rate_den=2, min_snr_db=-2.0,  cqi_index=4),
    ModulationProfile("BPSK_3_4",  bits_per_symbol=1, code_rate_num=3, code_rate_den=4, min_snr_db=1.0,   cqi_index=5),
    ModulationProfile("QPSK_1_2",  bits_per_symbol=2, code_rate_num=1, code_rate_den=2, min_snr_db=3.0,   cqi_index=6),
    ModulationProfile("QPSK_3_4",  bits_per_symbol=2, code_rate_num=3, code_rate_den=4, min_snr_db=6.5,   cqi_index=7),
    ModulationProfile("16QAM_1_2", bits_per_symbol=4, code_rate_num=1, code_rate_den=2, min_snr_db=10.5,  cqi_index=8),
    ModulationProfile("16QAM_3_4", bits_per_symbol=4, code_rate_num=3, code_rate_den=4, min_snr_db=14.0,  cqi_index=9),
    ModulationProfile("64QAM_2_3", bits_per_symbol=6, code_rate_num=2, code_rate_den=3, min_snr_db=18.0,  cqi_index=10),
    ModulationProfile("64QAM_5_6", bits_per_symbol=6, code_rate_num=5, code_rate_den=6, min_snr_db=22.0,  cqi_index=11),
]


@dataclass
class LinkAdaptationReport:
    active_profile: ModulationProfile
    snr_db: float
    target_cqi: int
    shannon_capacity_bps: float
    effective_throughput_bps: float
    spectral_efficiency: float
    bler_estimate: float
    hysteresis_active: bool


class AdaptiveModulationEngine:
    """
    Adaptive Modulation and Coding (AMC) controller.
    Selects the optimal modulation profile based on real-time SNR/SINR measurements,
    enforcing an upward hysteresis margin to prevent ping-pong oscillation under channel fading.
    """

    def __init__(
        self,
        bandwidth_hz: float = 125000.0,
        upward_hysteresis_db: float = 1.5,
        default_profile_name: str = "QPSK_1_2"
    ):
        self.bandwidth_hz = max(1000.0, float(bandwidth_hz))
        self.upward_hysteresis_db = max(0.0, float(upward_hysteresis_db))
        
        self.profiles: List[ModulationProfile] = sorted(TACTICAL_PROFILES, key=lambda p: p.min_snr_db)
        
        # Locate default profile
        matching = [p for p in self.profiles if p.name == default_profile_name]
        self.current_profile: ModulationProfile = matching[0] if matching else self.profiles[5]
        self.last_snr_db: float = self.current_profile.min_snr_db

    @staticmethod
    def shannon_capacity(bandwidth_hz: float, snr_db: float) -> float:
        """
        Computes theoretical maximum Shannon channel capacity:
        C = B * log2(1 + SNR_linear)
        """
        if bandwidth_hz <= 0.0:
            return 0.0
        # Convert dB to linear power ratio
        snr_linear = math.pow(10.0, snr_db / 10.0)
        return bandwidth_hz * math.log2(1.0 + snr_linear)

    @staticmethod
    def estimate_bler(snr_db: float, profile: ModulationProfile) -> float:
        """
        Heuristic Block Error Rate (BLER) estimation based on SNR deficit from profile threshold.
        """
        margin = snr_db - profile.min_snr_db
        if margin >= 5.0:
            return 1e-5
        elif margin <= -5.0:
            return 1.0
        # Smooth logistic decay across [-5, 5] dB margin
        return 1.0 / (1.0 + math.exp(margin * 0.9))

    def select_profile(self, measured_snr_db: float) -> LinkAdaptationReport:
        """
        Evaluates measured SNR and adapts the modulation profile with hysteresis filtering.
        To step UP to a higher profile, SNR must exceed candidate min_snr_db + upward_hysteresis_db.
        To step DOWN to a lower profile, SNR simply drops below current profile's min_snr_db.
        """
        current_idx = self.profiles.index(self.current_profile)
        best_idx = 0
        hysteresis_applied = False

        # Find candidate profile without hysteresis
        for i, profile in enumerate(self.profiles):
            if measured_snr_db >= profile.min_snr_db:
                best_idx = i

        # Apply hysteresis for upward transitions
        if best_idx > current_idx:
            candidate_profile = self.profiles[best_idx]
            required_snr_with_hysteresis = candidate_profile.min_snr_db + self.upward_hysteresis_db
            if measured_snr_db < required_snr_with_hysteresis:
                # Retain current profile (or highest profile that satisfies hysteresis)
                hysteresis_applied = True
                valid_idx = current_idx
                for j in range(current_idx + 1, best_idx + 1):
                    if measured_snr_db >= self.profiles[j].min_snr_db + self.upward_hysteresis_db:
                        valid_idx = j
                best_idx = valid_idx

        self.current_profile = self.profiles[best_idx]
        self.last_snr_db = measured_snr_db

        shannon_bps = self.shannon_capacity(self.bandwidth_hz, measured_snr_db)
        bler = self.estimate_bler(measured_snr_db, self.current_profile)
        raw_rate_bps = self.bandwidth_hz * self.current_profile.spectral_efficiency
        effective_throughput = raw_rate_bps * max(0.0, 1.0 - bler)

        return LinkAdaptationReport(
            active_profile=self.current_profile,
            snr_db=measured_snr_db,
            target_cqi=self.current_profile.cqi_index,
            shannon_capacity_bps=shannon_bps,
            effective_throughput_bps=effective_throughput,
            spectral_efficiency=self.current_profile.spectral_efficiency,
            bler_estimate=bler,
            hysteresis_active=hysteresis_applied
        )

    def encode_cqi_feedback(self) -> Dict[str, Any]:
        """Encodes closed-loop CQI telemetry packet to report back to transmitting peer."""
        return {
            "cqi": self.current_profile.cqi_index,
            "profile": self.current_profile.name,
            "snr_db": round(self.last_snr_db, 2),
            "spectral_eff": round(self.current_profile.spectral_efficiency, 3),
            "is_lora": self.current_profile.is_lora
        }

    def decode_and_apply_cqi(self, feedback: Dict[str, Any]) -> ModulationProfile:
        """Decodes CQI telemetry from remote peer and updates transmission profile."""
        cqi = int(feedback.get("cqi", self.current_profile.cqi_index))
        matching = [p for p in self.profiles if p.cqi_index == cqi]
        if matching:
            self.current_profile = matching[0]
        return self.current_profile
