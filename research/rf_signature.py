"""
RF Emission Signature Minimisation Advisor (Radar Cross-Section Model).

Computes an RF emission threat score based on transmitter EIRP, pulse duty
cycle, frequency, and operating environment visibility to model an adversary's
passive RF detection probability.  Provides scheduling recommendations to
minimise the node's detectable electromagnetic signature.

Technical basis:
  Effective Isotropic Radiated Power:
    EIRP_dBm = P_tx_dBm + G_ant_dBi - L_cable_dB

  Passive intercept range (Friis inversion for receiver SNR = 0 dB):
    R_int_m = (lambda / (4 * pi)) * sqrt(EIRP_W / (kTB * NF))

  Duty-cycle-weighted emission score:
    E_score = duty_cycle * EIRP_W * freq_penalty

  Frequency penalty (higher frequency = harder to intercept at long range
  due to atmospheric absorption, but easier to DF):
    freq_penalty = 1 + 0.3 * log10(f_Hz / 1e6)

  Minimum detectable signal (MDS) of intercept receiver:
    MDS_dBm = -174 + 10*log10(BW_Hz) + NF_int_dB + SNR_int_dB

Provides:
  - EIRP computation
  - Passive intercept range estimation
  - Emission threat score (0.0–1.0 normalised)
  - Transmission scheduling: short bursts at minimum power
  - Frequency selection guidance: best sub-band for lowest intercept probability
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# --------------------------------------------------------------------------- #
#  Constants                                                                   #
# --------------------------------------------------------------------------- #

_SPEED_OF_LIGHT_MPS = 299_792_458.0
_BOLTZMANN_J_K = 1.380649e-23
_TEMP_K = 290.0            # Standard reference temperature
_MILLIWATTS_PER_WATT = 1000.0


# --------------------------------------------------------------------------- #
#  Data classes                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class EmitterProfile:
    """
    RF emitter characteristics for signature computation.

    Attributes
    ----------
    tx_power_dbm : float
        Transmitter output power in dBm.
    antenna_gain_dbi : float
        Antenna gain in dBi.
    cable_loss_db : float
        Total feed/cable loss in dB (positive = loss).
    frequency_hz : float
        Operating frequency in Hz.
    duty_cycle : float
        Fraction of time transmitting (0.0–1.0).  1.0 = continuous wave.
    burst_duration_ms : float
        Duration of each transmission burst in milliseconds.
    bandwidth_hz : float
        Emission bandwidth in Hz.
    """
    tx_power_dbm: float = 27.0       # 500 mW
    antenna_gain_dbi: float = 2.15   # dipole
    cable_loss_db: float = 0.5
    frequency_hz: float = 915e6
    duty_cycle: float = 0.1          # 10% on-time
    burst_duration_ms: float = 50.0
    bandwidth_hz: float = 200e3


@dataclass
class InterceptReceiverProfile:
    """
    Characteristics of a hypothetical adversary intercept receiver.

    Attributes
    ----------
    noise_figure_db : float
        Receiver noise figure in dB.
    required_snr_db : float
        Minimum SNR required for successful detection.
    bandwidth_hz : float
        Intercept receiver bandwidth in Hz.
    """
    noise_figure_db: float = 3.0
    required_snr_db: float = 10.0
    bandwidth_hz: float = 1e6       # 1 MHz wideband sweep


@dataclass
class SignatureReport:
    """
    Output report from the signature minimisation advisor.

    Attributes
    ----------
    eirp_dbm : float
        Effective Isotropic Radiated Power in dBm.
    eirp_watts : float
        EIRP in watts.
    intercept_range_m : float
        Maximum passive intercept range (m) for the given intercept receiver.
    emission_score : float
        Normalised emission threat score in [0.0, 1.0].
        0 = minimal detectable signature; 1 = maximum exposure.
    recommended_tx_power_dbm : float
        Minimum transmit power (dBm) sufficient to close the link, reducing EIRP.
    recommended_duty_cycle : float
        Recommended duty cycle to reduce time-averaged intercept probability.
    recommended_burst_duration_ms : float
        Recommended burst length to minimise coherent integration gain by
        an adversary correlator.
    freq_penalty : float
        Dimensionless frequency penalty factor used in score computation.
    mds_dbm : float
        Minimum detectable signal of the intercept receiver in dBm.
    """
    eirp_dbm: float = 0.0
    eirp_watts: float = 0.0
    intercept_range_m: float = 0.0
    emission_score: float = 0.0
    recommended_tx_power_dbm: float = 0.0
    recommended_duty_cycle: float = 0.0
    recommended_burst_duration_ms: float = 0.0
    freq_penalty: float = 0.0
    mds_dbm: float = 0.0


# --------------------------------------------------------------------------- #
#  Core engine                                                                 #
# --------------------------------------------------------------------------- #

class RFSignatureAdvisor:
    """
    RF emission signature minimisation advisor.

    Evaluates a node's transmitter profile against a model of an adversary
    intercept receiver and computes:
      - EIRP
      - Maximum passive intercept range
      - Threat score
      - Scheduling recommendations to minimise detectability
    """

    # Reference EIRP for normalisation (100 W = +50 dBm)
    _EIRP_REF_WATTS = 100.0
    # Maximum emission score intercept range used for normalisation (km)
    _MAX_INTERCEPT_RANGE_KM = 100.0

    @classmethod
    def compute_eirp(cls, emitter: EmitterProfile) -> Tuple[float, float]:
        """
        Compute Effective Isotropic Radiated Power.

        Returns
        -------
        (eirp_dbm, eirp_watts) : Tuple[float, float]
        """
        eirp_dbm = emitter.tx_power_dbm + emitter.antenna_gain_dbi - emitter.cable_loss_db
        eirp_watts = (10.0 ** ((eirp_dbm - 30.0) / 10.0))
        return eirp_dbm, eirp_watts

    @classmethod
    def compute_mds(cls, intercept: InterceptReceiverProfile) -> float:
        """
        Minimum Detectable Signal of the intercept receiver in dBm.

        MDS = -174 + 10*log10(BW) + NF + SNR_req

        Returns
        -------
        float
            MDS in dBm.
        """
        return (
            -174.0
            + 10.0 * math.log10(intercept.bandwidth_hz)
            + intercept.noise_figure_db
            + intercept.required_snr_db
        )

    @classmethod
    def compute_intercept_range(
        cls,
        emitter: EmitterProfile,
        intercept: InterceptReceiverProfile,
    ) -> float:
        """
        Estimate maximum passive intercept range (m) where the adversary
        receiver achieves MDS.

        Derived from Friis: P_rx = EIRP * (lambda / (4*pi*R))^2
        Solving for R at P_rx = MDS:
          R = (lambda / (4*pi)) * sqrt(EIRP_W / MDS_W)

        Returns
        -------
        float
            Intercept range in metres.
        """
        _, eirp_watts = cls.compute_eirp(emitter)
        mds_dbm = cls.compute_mds(intercept)
        mds_watts = 10.0 ** ((mds_dbm - 30.0) / 10.0)

        wavelength_m = _SPEED_OF_LIGHT_MPS / emitter.frequency_hz

        if mds_watts <= 0 or eirp_watts <= 0:
            return 0.0

        ratio = eirp_watts / mds_watts
        if ratio <= 0:
            return 0.0

        range_m = (wavelength_m / (4.0 * math.pi)) * math.sqrt(ratio)
        return max(0.0, range_m)

    @classmethod
    def frequency_penalty(cls, frequency_hz: float) -> float:
        """
        Dimensionless frequency penalty factor.

        Higher frequencies are easier to direction-find but have shorter
        intercept ranges due to atmospheric attenuation at mm-wave.
        Penalty rises log-linearly with frequency above 1 MHz.

        Returns
        -------
        float
            Penalty factor >= 1.0.
        """
        return 1.0 + 0.3 * math.log10(max(1e6, frequency_hz) / 1e6)

    @classmethod
    def emission_score(
        cls,
        emitter: EmitterProfile,
        intercept: InterceptReceiverProfile,
    ) -> float:
        """
        Normalised emission threat score in [0.0, 1.0].

        score = duty_cycle * EIRP_W * freq_penalty / normaliser

        Returns
        -------
        float
            Score in [0.0, 1.0].  Higher = more detectable.
        """
        _, eirp_watts = cls.compute_eirp(emitter)
        fp = cls.frequency_penalty(emitter.frequency_hz)
        raw = emitter.duty_cycle * eirp_watts * fp
        normaliser = cls._EIRP_REF_WATTS * 2.0  # 100 W * max freq_penalty ≈ 200
        return min(1.0, raw / normaliser)

    @classmethod
    def recommend(
        cls,
        emitter: EmitterProfile,
        intercept: InterceptReceiverProfile,
        link_margin_db: float = 10.0,
    ) -> SignatureReport:
        """
        Generate a full signature report with scheduling recommendations.

        Parameters
        ----------
        emitter : EmitterProfile
        intercept : InterceptReceiverProfile
        link_margin_db : float
            Available link margin in dB (from link budget).  Used to
            compute the power reduction headroom.

        Returns
        -------
        SignatureReport
        """
        eirp_dbm, eirp_watts = cls.compute_eirp(emitter)
        mds_dbm = cls.compute_mds(intercept)
        intercept_range = cls.compute_intercept_range(emitter, intercept)
        fp = cls.frequency_penalty(emitter.frequency_hz)
        score = cls.emission_score(emitter, intercept)

        # Recommend reducing Tx power by the available link margin headroom
        # to stay just above the link closure threshold
        power_reduction_db = min(link_margin_db, 20.0)
        rec_tx_power = emitter.tx_power_dbm - power_reduction_db

        # Recommend duty cycle: halve if score > 0.5, else keep current
        rec_duty = emitter.duty_cycle * 0.5 if score > 0.5 else emitter.duty_cycle
        rec_duty = max(0.01, rec_duty)

        # Recommend burst duration: limit to 20 ms to reduce coherent integration gain
        rec_burst = min(emitter.burst_duration_ms, 20.0)

        return SignatureReport(
            eirp_dbm=eirp_dbm,
            eirp_watts=eirp_watts,
            intercept_range_m=intercept_range,
            emission_score=score,
            recommended_tx_power_dbm=rec_tx_power,
            recommended_duty_cycle=rec_duty,
            recommended_burst_duration_ms=rec_burst,
            freq_penalty=fp,
            mds_dbm=mds_dbm,
        )

    @classmethod
    def rank_frequencies(
        cls,
        candidate_freqs_hz: List[float],
        emitter: EmitterProfile,
        intercept: InterceptReceiverProfile,
    ) -> List[Tuple[float, float]]:
        """
        Rank candidate frequencies by ascending intercept range.

        Lower intercept range = harder for adversary to detect.

        Parameters
        ----------
        candidate_freqs_hz : List[float]
            List of candidate carrier frequencies in Hz.
        emitter : EmitterProfile
            Base emitter profile (frequency_hz will be overridden).
        intercept : InterceptReceiverProfile

        Returns
        -------
        List[Tuple[float, float]]
            Sorted list of (frequency_hz, intercept_range_m), ascending range.
        """
        results: List[Tuple[float, float]] = []
        for freq in candidate_freqs_hz:
            em = EmitterProfile(
                tx_power_dbm=emitter.tx_power_dbm,
                antenna_gain_dbi=emitter.antenna_gain_dbi,
                cable_loss_db=emitter.cable_loss_db,
                frequency_hz=freq,
                duty_cycle=emitter.duty_cycle,
                burst_duration_ms=emitter.burst_duration_ms,
                bandwidth_hz=emitter.bandwidth_hz,
            )
            r = cls.compute_intercept_range(em, intercept)
            results.append((freq, r))
        results.sort(key=lambda x: x[1])
        return results
