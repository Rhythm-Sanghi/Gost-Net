"""
Cooperative Distributed Virtual Antenna Array Coordination Engine.
Coordinates multiple adjacent squad radios to act as a distributed phased array,
calculating carrier phase shifts and timing offsets to synthesize directional constructive
beamforming toward distant friendly repeaters or gateways.
"""

import math
from typing import Dict, List, Tuple, Any, Optional


SPEED_OF_LIGHT = 299792458.0  # m/s


class VirtualArrayCoordinator:
    """
    Computes distributed phased array steering vectors and collaborative array factors.
    """

    def __init__(self, local_node_id: str, default_carrier_freq_hz: float = 915e6):
        self.local_node_id = local_node_id
        self.carrier_freq_hz = default_carrier_freq_hz
        # node_id -> (x_meters, y_meters) relative to array centroid
        self.nodes: Dict[str, Tuple[float, float]] = {}

    def register_node(self, node_id: str, x_meters: float, y_meters: float):
        """Registers a participating node's spatial position relative to array reference."""
        self.nodes[node_id] = (float(x_meters), float(y_meters))

    def remove_node(self, node_id: str):
        self.nodes.pop(node_id, None)

    def get_wavelength(self) -> float:
        return SPEED_OF_LIGHT / self.carrier_freq_hz

    def compute_steering_phases(
        self,
        target_azimuth_deg: float,
        carrier_freq_hz: Optional[float] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Computes the required phase shifts psi_i and time delays tau_i for each node
        to achieve constructive beamforming toward target_azimuth_deg.
        """
        freq = carrier_freq_hz or self.carrier_freq_hz
        wavelength = SPEED_OF_LIGHT / freq
        k = (2.0 * math.pi) / wavelength

        phi_rad = math.radians(target_azimuth_deg)
        ux = math.cos(phi_rad)
        uy = math.sin(phi_rad)

        steering_results: Dict[str, Dict[str, float]] = {}

        for nid, (x, y) in self.nodes.items():
            # Spatial path delay: d = x * cos(phi) + y * sin(phi)
            spatial_distance = (x * ux) + (y * uy)
            phase_rad = (-k * spatial_distance) % (2.0 * math.pi)
            delay_sec = spatial_distance / SPEED_OF_LIGHT

            steering_results[nid] = {
                "phase_rad": round(phase_rad, 4),
                "delay_nanoseconds": round(delay_sec * 1e9, 2),
                "x_m": x,
                "y_m": y
            }

        return steering_results

    def compute_array_power_gain_db(self) -> float:
        """
        Theoretical coherent power gain of an N-element distributed array:
        Gain_dB = 10 * log10(N^2) = 20 * log10(N).
        """
        n = len(self.nodes)
        if n <= 1:
            return 0.0
        return round(20.0 * math.log10(n), 2)

    def compute_array_factor(
        self,
        steering_azimuth_deg: float,
        observation_azimuth_deg: float
    ) -> float:
        """
        Computes normalized magnitude of the Array Factor |AF(theta)| at observation_azimuth_deg
        when steered toward steering_azimuth_deg.
        Returns value in [0.0, 1.0].
        """
        n = len(self.nodes)
        if n == 0:
            return 1.0

        wavelength = self.get_wavelength()
        k = (2.0 * math.pi) / wavelength

        # Steering direction vector
        phi_steer = math.radians(steering_azimuth_deg)
        ux_s, uy_s = math.cos(phi_steer), math.sin(phi_steer)

        # Observation direction vector
        phi_obs = math.radians(observation_azimuth_deg)
        ux_o, uy_o = math.cos(phi_obs), math.sin(phi_obs)

        # Sum complex phasors
        real_sum = 0.0
        imag_sum = 0.0

        for nid, (x, y) in self.nodes.items():
            # Net phase difference = k * ((x*ux_o + y*uy_o) - (x*ux_s + y*uy_s))
            phase_diff = k * (((x * ux_o) + (y * uy_o)) - ((x * ux_s) + (y * uy_s)))
            real_sum += math.cos(phase_diff)
            imag_sum += math.sin(phase_diff)

        magnitude = math.sqrt(real_sum ** 2 + imag_sum ** 2) / float(n)
        return min(1.0, max(0.0, magnitude))
