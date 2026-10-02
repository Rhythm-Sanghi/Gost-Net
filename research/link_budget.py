"""
Tactical RF Link Budget Calculator.

Computes end-to-end RF link margins using the Friis transmission equation,
incorporating free-space path loss (FSPL), antenna gain, system noise
temperature, thermal noise floor, required SNR, and environmental
attenuation factors (rain, foliage, obstacle clutter).

Outputs link margin (dB), maximum usable range (m), and a BER estimate
under BPSK/QPSK modulation for tactical comms planning.

Technical foundation:
  Received power (dBm):
    P_rx = P_tx + G_tx + G_rx - FSPL - L_cable - L_atm - L_env
  Thermal noise floor (dBm):
    N = -174 + 10*log10(BW) + NF
  SNR (dB):
    SNR = P_rx - N
  Required SNR for BPSK BER 1e-6:
    SNR_req ≈ 10.5 dB
  Link margin:
    M = SNR - SNR_req
"""

import math
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------- #
#  Data classes                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class Antenna:
    """
    Antenna parameters for transmit or receive end of the link.

    Attributes
    ----------
    gain_dbi : float
        Antenna gain in dBi (isotropic reference).
    height_m : float
        Antenna height above ground in metres (affects two-ray model).
    cable_loss_db : float
        Feeder/cable insertion loss in dB (positive = loss).
    """
    gain_dbi: float = 0.0
    height_m: float = 1.5
    cable_loss_db: float = 0.5


@dataclass
class RadioParameters:
    """
    Transmitter/Receiver radio parameters.

    Attributes
    ----------
    tx_power_dbm : float
        Transmitter output power in dBm at the antenna port.
    frequency_hz : float
        Carrier frequency in Hz.
    bandwidth_hz : float
        Receiver noise bandwidth in Hz.
    noise_figure_db : float
        Receiver noise figure in dB.
    required_snr_db : float
        Minimum SNR (dB) required for the target BER/modulation.
    """
    tx_power_dbm: float = 27.0          # 500 mW
    frequency_hz: float = 915e6         # 915 MHz LoRa / UHF
    bandwidth_hz: float = 125e3         # 125 kHz LoRa spreading
    noise_figure_db: float = 6.0
    required_snr_db: float = -15.0      # LoRa SF=12 threshold


@dataclass
class EnvironmentalLoss:
    """
    Environmental propagation loss components.

    Attributes
    ----------
    rain_rate_mm_hr : float
        Rainfall intensity in mm/hr.  0 = clear sky.
    foliage_depth_m : float
        Depth of dense forest/canopy through which the signal passes.
    foliage_loss_db_per_m : float
        Excess attenuation per metre of foliage (typical: 0.1–0.4 dB/m).
    obstacle_loss_db : float
        Additional diffraction/obstacle loss (e.g. building knife-edge, dB).
    """
    rain_rate_mm_hr: float = 0.0
    foliage_depth_m: float = 0.0
    foliage_loss_db_per_m: float = 0.2
    obstacle_loss_db: float = 0.0


@dataclass
class LinkBudgetResult:
    """
    Output of a link budget calculation.

    Attributes
    ----------
    fspl_db : float
        Free-space path loss at the given distance.
    rx_power_dbm : float
        Received signal power at the receiver antenna port.
    noise_floor_dbm : float
        Thermal noise floor at the receiver.
    snr_db : float
        Signal-to-noise ratio at the receiver.
    link_margin_db : float
        Margin above the required SNR.  Positive = viable link.
    max_range_m : float
        Maximum viable communication range (m) where link_margin = 0.
    rain_loss_db : float
        Rain-induced attenuation on the path.
    foliage_loss_db : float
        Foliage attenuation on the path.
    """
    fspl_db: float = 0.0
    rx_power_dbm: float = 0.0
    noise_floor_dbm: float = 0.0
    snr_db: float = 0.0
    link_margin_db: float = 0.0
    max_range_m: float = 0.0
    rain_loss_db: float = 0.0
    foliage_loss_db: float = 0.0


# --------------------------------------------------------------------------- #
#  Core engine                                                                 #
# --------------------------------------------------------------------------- #

class LinkBudgetCalculator:
    """
    Tactical RF link budget computation engine.

    Provides static methods so individual calculations can be called without
    instantiation, and a convenience ``calculate`` method that chains them.
    """

    SPEED_OF_LIGHT_MPS: float = 299_792_458.0
    BOLTZMANN_DBM_HZ: float = -174.0  # dBm/Hz at 290 K

    # ------------------------------------------------------------------
    # Static building-block methods
    # ------------------------------------------------------------------

    @staticmethod
    def free_space_path_loss_db(distance_m: float, frequency_hz: float) -> float:
        """
        Friis free-space path loss.

        FSPL = 20*log10(4*pi*d*f / c)

        Parameters
        ----------
        distance_m : float
            Link distance in metres.
        frequency_hz : float
            Carrier frequency in Hz.

        Returns
        -------
        float
            Free-space path loss in dB (positive = loss).
        """
        if distance_m <= 0:
            return 0.0
        wavelength_m = LinkBudgetCalculator.SPEED_OF_LIGHT_MPS / frequency_hz
        fspl = 20.0 * math.log10(4.0 * math.pi * distance_m / wavelength_m)
        return fspl

    @staticmethod
    def thermal_noise_floor_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
        """
        Thermal noise floor.

        N = -174 dBm/Hz + 10*log10(BW_Hz) + NF_dB

        Returns
        -------
        float
            Noise power in dBm.
        """
        return (
            LinkBudgetCalculator.BOLTZMANN_DBM_HZ
            + 10.0 * math.log10(bandwidth_hz)
            + noise_figure_db
        )

    @staticmethod
    def rain_attenuation_db(
        rain_rate_mm_hr: float,
        frequency_hz: float,
        path_length_m: float,
    ) -> float:
        """
        ITU-R P.838 simplified rain attenuation (terrestrial link).

        gamma_R = k * R^alpha   [dB/km]
        A = gamma_R * path_length_km

        Coefficients are approximated for the 0.3 GHz–10 GHz range using
        a polynomial fit to the ITU tables (horizontal polarisation).

        Returns
        -------
        float
            Rain attenuation in dB (positive = loss).
        """
        if rain_rate_mm_hr <= 0 or path_length_m <= 0:
            return 0.0

        freq_ghz = frequency_hz / 1e9

        # Simplified ITU-R P.838-3 k and alpha for horizontal polarisation
        # Valid approximately 0.5 GHz <= f <= 40 GHz
        if freq_ghz < 1.0:
            k, alpha = 2.09e-4, 1.58
        elif freq_ghz < 2.5:
            k, alpha = 9.88e-4 * freq_ghz**0.45, 1.42 - 0.015 * freq_ghz
        elif freq_ghz < 10.0:
            k, alpha = 3.15e-3 * freq_ghz**0.62, 1.26 - 0.02 * freq_ghz
        else:
            k, alpha = 0.0125 * freq_ghz**0.52, 1.06

        gamma_r = k * (rain_rate_mm_hr ** alpha)
        path_km = path_length_m / 1000.0
        return gamma_r * path_km

    @staticmethod
    def foliage_attenuation_db(
        foliage_depth_m: float,
        loss_db_per_m: float,
    ) -> float:
        """
        Excess foliage/canopy attenuation (early COST 235 model).

        Returns
        -------
        float
            Foliage loss in dB (positive = loss).
        """
        return max(0.0, foliage_depth_m * loss_db_per_m)

    @staticmethod
    def bpsk_ber(snr_linear: float) -> float:
        """
        Theoretical BPSK bit-error-rate.

        BER = Q(sqrt(2 * Eb/N0)) ≈ 0.5 * erfc(sqrt(Eb/N0))

        Parameters
        ----------
        snr_linear : float
            Linear SNR (ratio, not dB).

        Returns
        -------
        float
            BER in [0, 0.5].
        """
        if snr_linear <= 0:
            return 0.5
        # erfc approximation
        x = math.sqrt(snr_linear)
        # Complementary error function via approximation (Abramowitz & Stegun 7.1.26)
        t = 1.0 / (1.0 + 0.3275911 * x)
        poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
        erfc_val = poly * math.exp(-x * x)
        return max(0.0, min(0.5, 0.5 * erfc_val))

    # ------------------------------------------------------------------
    # Internal helper (no recursion with calculate)
    # ------------------------------------------------------------------

    @classmethod
    def _compute_margin(
        cls,
        radio: RadioParameters,
        tx_antenna: Antenna,
        rx_antenna: Antenna,
        env: EnvironmentalLoss,
        distance_m: float,
    ) -> float:
        """
        Internal helper: compute link margin (dB) without invoking max_range_meters.

        Used by both ``calculate`` and ``max_range_meters`` to break the
        circular dependency that would otherwise cause infinite recursion.
        """
        fspl = cls.free_space_path_loss_db(distance_m, radio.frequency_hz)
        rain_loss = cls.rain_attenuation_db(env.rain_rate_mm_hr, radio.frequency_hz, distance_m)
        fol_loss = cls.foliage_attenuation_db(env.foliage_depth_m, env.foliage_loss_db_per_m)
        cable_loss = tx_antenna.cable_loss_db + rx_antenna.cable_loss_db
        rx_power = (
            radio.tx_power_dbm
            + tx_antenna.gain_dbi
            + rx_antenna.gain_dbi
            - fspl
            - cable_loss
            - rain_loss
            - fol_loss
            - env.obstacle_loss_db
        )
        noise_floor = cls.thermal_noise_floor_dbm(radio.bandwidth_hz, radio.noise_figure_db)
        snr = rx_power - noise_floor
        return snr - radio.required_snr_db

    @classmethod
    def max_range_meters(
        cls,
        radio: RadioParameters,
        tx_antenna: Antenna,
        rx_antenna: Antenna,
        env: EnvironmentalLoss,
    ) -> float:
        """
        Binary-search for the distance at which link_margin == 0.

        Uses ``_compute_margin`` internally to avoid recursive calls to
        ``calculate``.

        Returns
        -------
        float
            Maximum range in metres.
        """
        lo, hi = 1.0, 1_000_000.0
        for _ in range(60):
            mid = (lo + hi) / 2.0
            margin = cls._compute_margin(radio, tx_antenna, rx_antenna, env, mid)
            if margin >= 0:
                lo = mid
            else:
                hi = mid
        return lo

    # ------------------------------------------------------------------
    # Main calculation entry point
    # ------------------------------------------------------------------

    @classmethod
    def calculate(
        cls,
        radio: RadioParameters,
        tx_antenna: Antenna,
        rx_antenna: Antenna,
        env: EnvironmentalLoss,
        distance_m: float,
    ) -> LinkBudgetResult:
        """
        Full end-to-end link budget computation.

        Parameters
        ----------
        radio : RadioParameters
        tx_antenna : Antenna
        rx_antenna : Antenna
        env : EnvironmentalLoss
        distance_m : float
            Link path length in metres.

        Returns
        -------
        LinkBudgetResult
        """
        fspl = cls.free_space_path_loss_db(distance_m, radio.frequency_hz)
        rain_loss = cls.rain_attenuation_db(env.rain_rate_mm_hr, radio.frequency_hz, distance_m)
        fol_loss = cls.foliage_attenuation_db(env.foliage_depth_m, env.foliage_loss_db_per_m)
        obstacle_loss = env.obstacle_loss_db
        cable_loss = tx_antenna.cable_loss_db + rx_antenna.cable_loss_db

        rx_power = (
            radio.tx_power_dbm
            + tx_antenna.gain_dbi
            + rx_antenna.gain_dbi
            - fspl
            - cable_loss
            - rain_loss
            - fol_loss
            - obstacle_loss
        )

        noise_floor = cls.thermal_noise_floor_dbm(radio.bandwidth_hz, radio.noise_figure_db)
        snr = rx_power - noise_floor
        margin = snr - radio.required_snr_db

        # max_range_meters calls _compute_margin internally — no recursion
        max_range = cls.max_range_meters(radio, tx_antenna, rx_antenna, env)

        return LinkBudgetResult(
            fspl_db=fspl,
            rx_power_dbm=rx_power,
            noise_floor_dbm=noise_floor,
            snr_db=snr,
            link_margin_db=margin,
            max_range_m=max_range,
            rain_loss_db=rain_loss,
            foliage_loss_db=fol_loss,
        )
