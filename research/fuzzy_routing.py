"""
Gost-Net - Multi-Criteria Fuzzy Logic / AHP Tactical Route Optimization Engine
Phase 15 Subsystem: Advanced tactical route cost estimation and path selection combining
disparate non-linear parameters: residual battery level, RF signal strength (RSSI/SNR),
Packet Delivery Ratio (PDR), latency/jitter (RTT), and hop count.
Features triangular/trapezoidal membership functions, Analytic Hierarchy Process (AHP)
weight vectors with mission presets (STANDARD, EMERGENCY, LOW_POWER), bottleneck pruning,
and Pareto-optimal multi-hop candidate path ranking.
"""

import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class MissionMode(Enum):
    STANDARD = "STANDARD"
    EMERGENCY = "EMERGENCY"
    LOW_POWER = "LOW_POWER"


@dataclass
class NodeMetrics:
    node_id: str
    battery_pct: float       # 0.0 to 100.0%
    rssi_dbm: float          # typically -120.0 to -30.0 dBm
    pdr: float               # Packet Delivery Ratio: 0.0 to 1.0
    rtt_ms: float            # Round-trip latency: >= 0.0 ms
    hop_count: int = 1       # Number of hops from destination


@dataclass
class FuzzyEvaluation:
    node_id: str
    composite_score: float   # 0.0 to 1.0 (higher is superior)
    battery_score: float
    link_score: float
    pdr_score: float
    latency_score: float
    hop_score: float
    classification: str      # OPTIMAL, ACCEPTABLE, DEGRADED, PRUNED


@dataclass
class PathRank:
    path_nodes: List[str]
    bottleneck_score: float
    average_score: float
    total_hops: int
    is_viable: bool


class FuzzyRoutingEngine:
    """
    Multi-criteria routing decision engine.
    Uses fuzzy membership evaluation and weighted aggregation to score nodes and candidate paths.
    """

    # AHP Weights for each operational mode (sum to 1.0)
    MODE_WEIGHTS = {
        MissionMode.STANDARD: {
            "battery": 0.25,
            "link": 0.25,
            "pdr": 0.25,
            "latency": 0.15,
            "hops": 0.10,
        },
        MissionMode.EMERGENCY: {
            "battery": 0.05,
            "link": 0.35,
            "pdr": 0.40,
            "latency": 0.10,
            "hops": 0.10,
        },
        MissionMode.LOW_POWER: {
            "battery": 0.45,
            "link": 0.15,
            "pdr": 0.15,
            "latency": 0.10,
            "hops": 0.15,
        }
    }

    def __init__(self, mode: MissionMode = MissionMode.STANDARD, min_viable_score: float = 0.30):
        self.mode = mode
        self.min_viable_score = max(0.05, min(0.90, min_viable_score))

    @staticmethod
    def _clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, val))

    @classmethod
    def fuzzify_battery(cls, battery_pct: float) -> float:
        """
        Fuzzy mapping for battery:
        <= 15% -> steeply drops to 0.0 (prevent dead-node blackhole)
        15% - 40% -> linear rise to 0.5
        40% - 80% -> rise to 0.9
        > 80% -> 1.0
        """
        pct = max(0.0, min(100.0, battery_pct))
        if pct <= 10.0:
            return 0.01 * pct  # Max 0.10 for critical battery
        elif pct <= 40.0:
            return 0.10 + (pct - 10.0) / 30.0 * 0.50  # 0.10 to 0.60
        elif pct <= 80.0:
            return 0.60 + (pct - 40.0) / 40.0 * 0.35  # 0.60 to 0.95
        else:
            return 0.95 + (pct - 80.0) / 20.0 * 0.05  # 0.95 to 1.00

    @classmethod
    def fuzzify_rssi(cls, rssi_dbm: float) -> float:
        """
        Fuzzy mapping for RSSI:
        <= -115 dBm -> 0.0 (receiver sensitivity floor)
        -115 to -85 dBm -> linear rise from 0.0 to 0.6
        -85 to -60 dBm -> rise from 0.6 to 0.9
        >= -60 dBm -> 1.0 (strong line of sight)
        """
        if rssi_dbm <= -115.0:
            return 0.0
        elif rssi_dbm >= -60.0:
            return 1.0
        elif rssi_dbm <= -85.0:
            return cls._clamp((rssi_dbm - (-115.0)) / 30.0 * 0.60)
        else:
            return cls._clamp(0.60 + (rssi_dbm - (-85.0)) / 25.0 * 0.40)

    @classmethod
    def fuzzify_pdr(cls, pdr: float) -> float:
        """
        Fuzzy mapping for Packet Delivery Ratio:
        Quadratic preference for high PDR (PDR^1.5)
        """
        clamped = cls._clamp(pdr)
        return math.pow(clamped, 1.3)

    @classmethod
    def fuzzify_latency(cls, rtt_ms: float) -> float:
        """
        Fuzzy mapping for latency / RTT:
        <= 10 ms -> 1.0
        10 ms to 200 ms -> linear decrease to 0.5
        200 ms to 1000 ms -> decrease to 0.1
        > 1000 ms -> 0.02
        """
        if rtt_ms <= 10.0:
            return 1.0
        elif rtt_ms <= 200.0:
            return 1.0 - (rtt_ms - 10.0) / 190.0 * 0.50
        elif rtt_ms <= 1000.0:
            return 0.50 - (rtt_ms - 200.0) / 800.0 * 0.40
        else:
            return 0.02

    @classmethod
    def fuzzify_hops(cls, hop_count: int) -> float:
        """
        Fuzzy penalty for hop count:
        1 hop -> 1.0
        2 hops -> 0.85
        3 hops -> 0.70
        4 hops -> 0.55
        5+ hops -> 1 / (1 + 0.3 * hops)
        """
        h = max(1, hop_count)
        if h == 1:
            return 1.0
        elif h == 2:
            return 0.85
        elif h == 3:
            return 0.70
        elif h == 4:
            return 0.55
        else:
            return 1.0 / (1.0 + 0.35 * (h - 1))

    def evaluate_node(self, metrics: NodeMetrics) -> FuzzyEvaluation:
        """Computes weighted multi-criteria routing score for a single candidate relay node."""
        weights = self.MODE_WEIGHTS[self.mode]
        
        b_score = self.fuzzify_battery(metrics.battery_pct)
        l_score = self.fuzzify_rssi(metrics.rssi_dbm)
        p_score = self.fuzzify_pdr(metrics.pdr)
        lat_score = self.fuzzify_latency(metrics.rtt_ms)
        h_score = self.fuzzify_hops(metrics.hop_count)

        composite = (
            weights["battery"] * b_score +
            weights["link"] * l_score +
            weights["pdr"] * p_score +
            weights["latency"] * lat_score +
            weights["hops"] * h_score
        )
        composite = self._clamp(composite)

        # Classification
        if composite >= 0.80:
            cls_name = "OPTIMAL"
        elif composite >= 0.55:
            cls_name = "ACCEPTABLE"
        elif composite >= self.min_viable_score:
            cls_name = "DEGRADED"
        else:
            cls_name = "PRUNED"

        # Battery Starvation Guard:
        # If battery is critical (<= 10%), cap classification to DEGRADED or PRUNED to prevent node death
        if metrics.battery_pct <= 10.0:
            if self.mode == MissionMode.LOW_POWER or composite < self.min_viable_score:
                cls_name = "PRUNED" if composite < self.min_viable_score else "DEGRADED"
            elif cls_name in ("OPTIMAL", "ACCEPTABLE"):
                cls_name = "DEGRADED"

        # Link Failure Guard:
        # A node with PDR < 0.50 or RSSI < -110 dBm cannot reliably transport packets
        if metrics.pdr < 0.50 or metrics.rssi_dbm < -110.0:
            cls_name = "PRUNED"

        return FuzzyEvaluation(
            node_id=metrics.node_id,
            composite_score=round(composite, 4),
            battery_score=round(b_score, 4),
            link_score=round(l_score, 4),
            pdr_score=round(p_score, 4),
            latency_score=round(lat_score, 4),
            hop_score=round(h_score, 4),
            classification=cls_name
        )

    def rank_paths(self, candidate_paths: List[List[NodeMetrics]]) -> List[PathRank]:
        """
        Ranks candidate multi-hop paths from source to destination.
        Each candidate path is an ordered list of intermediate NodeMetrics.
        Evaluates bottleneck link score (min) and mean score across hops.
        Returns paths sorted in descending order of optimality.
        """
        ranked = []
        for path in candidate_paths:
            if not path:
                continue
            evals = [self.evaluate_node(m) for m in path]
            scores = [e.composite_score for e in evals]
            bottleneck = min(scores)
            avg = sum(scores) / len(scores)
            is_viable = all(e.classification != "PRUNED" for e in evals) and (bottleneck >= self.min_viable_score)
            
            node_ids = [m.node_id for m in path]
            ranked.append(PathRank(
                path_nodes=node_ids,
                bottleneck_score=round(bottleneck, 4),
                average_score=round(avg, 4),
                total_hops=len(path),
                is_viable=is_viable
            ))

        # Sort: first viable, then highest bottleneck score, then highest average
        ranked.sort(key=lambda pr: (pr.is_viable, pr.bottleneck_score, pr.average_score), reverse=True)
        return ranked
