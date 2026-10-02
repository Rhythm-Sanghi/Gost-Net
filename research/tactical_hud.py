"""
Gost-Net - Unified Tactical HUD & Diagnostic Dashboard Controller
Phase 16 Subsystem: Centralized situational awareness and diagnostic aggregation engine
unifying physical-layer AMC, link budget, LKH group key status, jammer triangulation,
sliding-window anti-replay, and Merkle audit ledgers into a single operational HUD.
"""

import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class TacticalAlert:
    severity: str    # INFO, WARNING, CRITICAL
    subsystem: str
    message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class HUDState:
    callsign: str
    peer_id: str
    network_state: str
    timestamp: float
    # Physical / RF
    amc_profile: str
    cqi: int
    shannon_capacity_bps: float
    link_margin_db: float
    eirp_threat_score: float
    # Network & Mesh
    mesh_nodes_count: int
    mesh_diameter: int
    critical_bridges_count: int
    anti_replay_rejected: int
    # Cryptographic & Security
    lkh_group_key_id: int
    merkle_ledger_height: int
    merkle_root_hash: str
    # Electronic Warfare
    jammer_detected: bool
    jammer_azimuth_deg: Optional[float]
    jammer_distance_m: Optional[float]
    alerts: List[TacticalAlert] = field(default_factory=list)


class TacticalHUDController:
    """
    Unified C4ISR Tactical HUD Controller.
    Aggregates diagnostic telemetry from all active GostEngine subsystems.
    """

    def __init__(self, callsign: str = "OPERATOR", peer_id: str = "NODE_LOCAL"):
        self.callsign = callsign
        self.peer_id = peer_id
        self.alerts: List[TacticalAlert] = []

    def add_alert(self, severity: str, subsystem: str, message: str):
        """Records a tactical operational alert with FIFO bounding (max 50)."""
        alert = TacticalAlert(severity=severity.upper(), subsystem=subsystem, message=message)
        self.alerts.append(alert)
        if len(self.alerts) > 50:
            self.alerts.pop(0)

    def compile_hud_state(self, engine: Any) -> HUDState:
        """Extracts and unifies diagnostic data across all GhostEngine subsystems."""
        # 1. Physical / RF
        amc_profile = "UNKNOWN"
        cqi = 0
        shannon_bps = 0.0
        if getattr(engine, "adaptive_modulation", None):
            prof = engine.adaptive_modulation.current_profile
            amc_profile = prof.name
            cqi = prof.cqi_index
            shannon_bps = engine.adaptive_modulation.shannon_capacity(
                engine.adaptive_modulation.bandwidth_hz,
                engine.adaptive_modulation.last_snr_db
            )

        link_margin = 0.0
        eirp_score = 0.0
        if getattr(engine, "rf_signature_advisor", None):
            try:
                sig = engine.evaluate_rf_signature()
                eirp_score = sig.get("emission_score", 0.0)
            except Exception:
                pass

        # 2. Network & Mesh
        mesh_nodes = 0
        mesh_diam = 0
        bridges_count = 0
        if getattr(engine, "topology_manager", None):
            mesh_nodes = len(engine.topology_manager.node_metadata)
            mesh_diam = engine.topology_manager.calculate_network_diameter()
            bridges_count = len(engine.topology_manager.find_critical_bridge_nodes())

        replays_rejected = 0
        if getattr(engine, "anti_replay", None):
            replays_rejected = engine.anti_replay.stats.replays_rejected

        # 3. Cryptographic & Security
        lkh_key_id = 1
        if getattr(engine, "lkh_rekeying", None):
            lkh_key_id = engine.lkh_rekeying.root_id

        merkle_height = 0
        merkle_root = "0" * 64
        if getattr(engine, "merkle_ledger", None):
            merkle_height = len(engine.merkle_ledger.entries)
            if hasattr(engine.merkle_ledger, "get_latest_hash"):
                merkle_root = engine.merkle_ledger.get_latest_hash()
            elif hasattr(engine.merkle_ledger, "get_root_hash"):
                merkle_root = engine.merkle_ledger.get_root_hash()

        # 4. Electronic Warfare
        jammer_detected = False
        jammer_az = None
        jammer_dist = None
        if getattr(engine, "anti_jamming", None):
            jammer_detected = engine.anti_jamming.is_jamming_detected

        state_label = "OFFLINE"
        if hasattr(engine, "get_network_state_label"):
            state_label = engine.get_network_state_label()

        return HUDState(
            callsign=self.callsign,
            peer_id=self.peer_id,
            network_state=state_label,
            timestamp=time.time(),
            amc_profile=amc_profile,
            cqi=cqi,
            shannon_capacity_bps=round(shannon_bps, 1),
            link_margin_db=round(link_margin, 2),
            eirp_threat_score=round(eirp_score, 4),
            mesh_nodes_count=mesh_nodes,
            mesh_diameter=mesh_diam,
            critical_bridges_count=bridges_count,
            anti_replay_rejected=replays_rejected,
            lkh_group_key_id=lkh_key_id,
            merkle_ledger_height=merkle_height,
            merkle_root_hash=merkle_root,
            jammer_detected=jammer_detected,
            jammer_azimuth_deg=jammer_az,
            jammer_distance_m=jammer_dist,
            alerts=list(self.alerts)
        )

    def render_ascii_dashboard(self, state: HUDState) -> str:
        """Renders an ASCII tactical dashboard suitable for headless terminal operators."""
        lines = [
            "=================================================================",
            f" [GOST-NET TACTICAL HUD]  OPERATOR: {state.callsign} | ID: {state.peer_id[:8]}",
            f" STATUS: {state.network_state} | EPOCH: {int(state.timestamp)}",
            "-----------------------------------------------------------------",
            " [RF & PHYSICAL LAYER]",
            f"   AMC Constellation : {state.amc_profile} (CQI {state.cqi})",
            f"   Shannon Capacity  : {state.shannon_capacity_bps:,.1f} bps",
            f"   EIRP Threat Score : {state.eirp_threat_score:.4f}",
            " [MESH TOPOLOGY & ROUTING]",
            f"   Visible Nodes     : {state.mesh_nodes_count} | Diameter: {state.mesh_diameter}",
            f"   Critical Bridges  : {state.critical_bridges_count} SPoF",
            f"   Replays Blocked   : {state.anti_replay_rejected} packets",
            " [CRYPTOGRAPHY & INTEGRITY]",
            f"   LKH Key Epoch     : Root #{state.lkh_group_key_id}",
            f"   Merkle Ledger     : Height {state.merkle_ledger_height} | Root {state.merkle_root_hash[:16]}...",
            " [ELECTRONIC WARFARE (EW)]",
            f"   Jamming Status    : {'ACTIVE THREAT' if state.jammer_detected else 'CLEAR SKY'}",
            "-----------------------------------------------------------------",
            f" RECENT ALERTS ({len(state.alerts)}):"
        ]
        if not state.alerts:
            lines.append("   [INFO] All tactical subsystems nominal.")
        else:
            for alt in state.alerts[-5:]:
                lines.append(f"   [{alt.severity}] ({alt.subsystem}) {alt.message}")
        lines.append("=================================================================")
        return "\n".join(lines)
