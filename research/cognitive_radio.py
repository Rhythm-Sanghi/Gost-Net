"""
Cognitive Radio Spectrum Sensing & Dynamic Energy Detection Engine.
Performs radiometric energy detection, noise floor estimation, spectral flatness analysis,
and dynamic channel vacancy ranking to advise adaptive frequency hopping and avoid jammed bands.
"""

import math
import time
import threading
from typing import Dict, List, Optional, Tuple, Any


class SpectrumSensingEngine:
    """
    Evaluates RF spectrum characteristics using energy detection and statistical metrics
    to dynamically identify clear transmission channels.
    """

    def __init__(
        self,
        noise_floor_window: int = 50,
        default_detection_threshold_margin: float = 1.35
    ):
        self.noise_floor_window = noise_floor_window
        self.default_detection_threshold_margin = default_detection_threshold_margin

        # channel_id -> list of float noise floor samples
        self.channel_noise_histories: Dict[int, List[float]] = {}
        # channel_id -> list of bool (True=occupied, False=vacant)
        self.channel_occupancy_histories: Dict[int, List[bool]] = {}
        self.lock = threading.RLock()

    @staticmethod
    def compute_energy(samples: List[float]) -> float:
        """
        Computes normalized energy of signal samples:
        E = (1 / N) * sum(|x[i]|^2)
        """
        if not samples:
            return 0.0
        sum_sq = sum(float(x) ** 2 for x in samples)
        return sum_sq / float(len(samples))

    @staticmethod
    def compute_spectral_flatness(power_spectrum_bins: List[float]) -> float:
        """
        Computes spectral flatness (Wiener entropy):
        Ratio of geometric mean to arithmetic mean of power spectrum.
        Values near 1.0 indicate white noise; values near 0.0 indicate narrowband signals / tones.
        """
        if not power_spectrum_bins:
            return 1.0

        # Avoid zero or negative values in log
        valid_bins = [max(1e-12, float(p)) for p in power_spectrum_bins]
        n = len(valid_bins)

        arithmetic_mean = sum(valid_bins) / float(n)
        if arithmetic_mean <= 1e-12:
            return 1.0

        log_sum = sum(math.log(b) for b in valid_bins)
        geometric_mean = math.exp(log_sum / float(n))

        flatness = geometric_mean / arithmetic_mean
        return max(0.0, min(1.0, flatness))

    def update_channel_observation(
        self,
        channel_id: int,
        samples: List[float],
        power_spectrum: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Records an RF observation for a channel and determines if the channel is occupied.
        """
        energy = self.compute_energy(samples)
        flatness = self.compute_spectral_flatness(power_spectrum) if power_spectrum else 1.0

        with self.lock:
            if channel_id not in self.channel_noise_histories:
                self.channel_noise_histories[channel_id] = []
            if channel_id not in self.channel_occupancy_histories:
                self.channel_occupancy_histories[channel_id] = []

            history = self.channel_noise_histories[channel_id]
            occ_history = self.channel_occupancy_histories[channel_id]

            # Estimate baseline noise floor
            if len(history) < 5:
                est_noise_floor = energy
            else:
                # Lowest 30th percentile represents quiet background noise floor
                sorted_hist = sorted(history)
                idx = int(len(sorted_hist) * 0.3)
                est_noise_floor = sorted_hist[idx]

            # Adaptive detection threshold
            threshold = est_noise_floor * self.default_detection_threshold_margin
            is_occupied = energy > threshold

            # Record in histories (bounded by window size)
            history.append(energy)
            if len(history) > self.noise_floor_window:
                history.pop(0)

            occ_history.append(is_occupied)
            if len(occ_history) > self.noise_floor_window:
                occ_history.pop(0)

            # Compute SNR in dB
            snr_db = 10.0 * math.log10(max(1e-6, energy / max(1e-6, est_noise_floor)))

            return {
                "channel_id": channel_id,
                "energy": energy,
                "noise_floor": est_noise_floor,
                "threshold": threshold,
                "is_occupied": is_occupied,
                "snr_db": snr_db,
                "spectral_flatness": flatness
            }

    def get_channel_duty_cycle(self, channel_id: int) -> float:
        """Returns the ratio of time channel_id was detected as occupied (0.0 to 1.0)."""
        with self.lock:
            occ = self.channel_occupancy_histories.get(channel_id, [])
            if not occ:
                return 0.0
            return sum(1 for x in occ if x) / float(len(occ))

    def rank_vacant_channels(self, candidate_channels: List[int]) -> List[Tuple[int, float]]:
        """
        Ranks channels by vacancy quality.
        Returns a sorted list of (channel_id, vacancy_score) where lowest duty cycle and lowest
        energy are ranked highest (best first).
        """
        with self.lock:
            scores = []
            for ch in candidate_channels:
                duty = self.get_duty_cycle_unlocked(ch)
                recent_energy = 0.0
                hist = self.channel_noise_histories.get(ch, [])
                if hist:
                    recent_energy = hist[-1]
                # Combined penalty: duty cycle heavily weighted + energy
                penalty = (duty * 100.0) + recent_energy
                scores.append((ch, penalty))

            # Sort ascending by penalty (lowest penalty = best channel)
            scores.sort(key=lambda item: item[1])
            return scores

    def get_duty_cycle_unlocked(self, channel_id: int) -> float:
        occ = self.channel_occupancy_histories.get(channel_id, [])
        if not occ:
            return 0.0
        return sum(1 for x in occ if x) / float(len(occ))
