#!/usr/bin/env python3

import sys
import csv
import io
from datetime import datetime
from collections import defaultdict, Counter
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend


def derive_decryption_key():
    diagnostic_key_material = b'ghostnet_diagnostic_export_key_2024'
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'diagnostic_salt',
        info=b'telemetry_encryption',
        backend=default_backend()
    )
    return hkdf.derive(diagnostic_key_material)


def decrypt_telemetry_file(file_path):
    try:
        # Try hybrid diagnostics decryption first
        try:
            with open(file_path, 'rb') as f:
                len_epub_bytes = f.read(4)
                if len(len_epub_bytes) == 4:
                    len_epub = int.from_bytes(len_epub_bytes, 'big')
                    if 0 < len_epub < 1024:
                        epub_bytes = f.read(len_epub)
                        nonce = f.read(12)
                        ciphertext = f.read()
                        
                        # Load Support Desk Private Key (from tests / diagnostics keypair)
                        support_priv_hex = "3081b6020100301006072a8648ce3d020106052b8104002204819e30819b02010104308571c5da6df9cdd1a4a8664fbbf992e55127c66362ada15e0effde14bb9e20a5a647c098521a90f44826a0954131cc23a164036200040a06512a9218b19eb751ed125222e65b7964f86b210c0e9f338ccce5378e0329130faf0b8cbc647ac2622c5e171ec41ff6972a395fbfc5508729f16d380c1447d81547850acf9f3d54c70681aaa9bf98a21373a9224b8d9c313e0ecd48328415"
                        support_priv_key = serialization.load_der_private_key(bytes.fromhex(support_priv_hex), password=None)
                        
                        ephemeral_pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP384R1(), epub_bytes)
                        shared_secret = support_priv_key.exchange(ec.ECDH(), ephemeral_pub_key)
                        
                        hkdf = HKDF(
                            algorithm=hashes.SHA256(),
                            length=32,
                            salt=b'diagnostic_salt_v2',
                            info=b'telemetry_hybrid_encryption',
                            backend=default_backend()
                        )
                        aes_key = hkdf.derive(shared_secret)
                        
                        cipher = AESGCM(aes_key)
                        plaintext = cipher.decrypt(nonce, ciphertext, None)
                        return plaintext.decode('utf-8')
        except Exception:
            # Fallback to legacy symmetric decryption
            pass

        with open(file_path, 'rb') as f:
            nonce = f.read(12)
            ciphertext = f.read()
        
        if len(nonce) != 12:
            raise ValueError(f"Invalid nonce length: expected 12 bytes, got {len(nonce)}")
        
        derived_key = derive_decryption_key()
        cipher = AESGCM(derived_key)
        plaintext = cipher.decrypt(nonce, ciphertext, None)
        
        return plaintext.decode('utf-8')
    except Exception as e:
        print(f"Decryption error: {e}")
        sys.exit(1)


def parse_csv_data(csv_text):
    csv_file = io.StringIO(csv_text)
    reader = csv.DictReader(csv_file)
    rows = list(reader)
    return rows


def analyze_telemetry(rows):
    if not rows:
        print("No telemetry data found")
        return
    
    timestamps = []
    event_counts = defaultdict(int)
    peer_relay_counts = Counter()
    handshake_failures = 0
    connection_losses = 0
    relay_events = 0
    route_discovered = 0
    route_dropped = 0
    
    for row in rows:
        try:
            timestamp_str = row.get('timestamp', '')
            event_type = row.get('event_type', '')
            peer_id = row.get('peer_id', '')
            
            if timestamp_str:
                ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                timestamps.append(ts)
            
            event_counts[event_type] += 1
            
            if event_type == 'ROUTE_DISCOVERED':
                route_discovered += 1
            elif event_type == 'ROUTE_DROPPED':
                route_dropped += 1
            elif event_type == 'PACKET_RELAYED':
                relay_events += 1
                if peer_id:
                    peer_relay_counts[peer_id] += 1
            elif event_type == 'HANDSHAKE_FAILED':
                handshake_failures += 1
            elif event_type == 'CONNECTION_LOST':
                connection_losses += 1
        
        except Exception as e:
            pass
    
    if not timestamps:
        print("No valid timestamps found in telemetry data")
        return
    
    timestamps.sort()
    mission_start = timestamps[0]
    mission_end = timestamps[-1]
    mission_duration = mission_end - mission_start
    
    total_events = len(rows)
    total_failures = handshake_failures + connection_losses
    failure_rate = (total_failures / total_events * 100) if total_events > 0 else 0
    
    most_active_relay = peer_relay_counts.most_common(1)[0] if peer_relay_counts else (None, 0)
    
    print("\n" + "="*70)
    print("GHOST NET MISSION TELEMETRY ANALYSIS")
    print("="*70)
    
    print(f"\nMISSION TIMELINE")
    print("-" * 70)
    print(f"Start Time:        {mission_start.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} UTC")
    print(f"End Time:          {mission_end.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} UTC")
    print(f"Total Duration:    {str(mission_duration).split('.')[0]}")
    
    print(f"\nEVENT SUMMARY")
    print("-" * 70)
    print(f"Total Events Logged: {total_events}")
    for event_type in sorted(event_counts.keys()):
        count = event_counts[event_type]
        pct = (count / total_events * 100) if total_events > 0 else 0
        print(f"  • {event_type:<20} {count:>5} ({pct:>5.1f}%)")
    
    print(f"\nROUTING STABILITY")
    print("-" * 70)
    total_route_events = route_discovered + route_dropped
    if total_route_events > 0:
        stability_ratio = route_discovered / total_route_events * 100
    else:
        stability_ratio = 0.0
    print(f"Routes Discovered:   {route_discovered}")
    print(f"Routes Dropped:      {route_dropped}")
    print(f"Stability Ratio:     {stability_ratio:.1f}% (discovered/total)")
    
    print(f"\nMESH NETWORK LOAD")
    print("-" * 70)
    print(f"Total Packets Relayed: {relay_events}")
    if relay_events > 0:
        avg_relay_per_peer = relay_events / len(peer_relay_counts) if peer_relay_counts else 0
        print(f"Unique Relay Peers:    {len(peer_relay_counts)}")
        print(f"Avg Relays Per Peer:   {avg_relay_per_peer:.2f}")
    
    print(f"\nFAILURE ANALYSIS")
    print("-" * 70)
    print(f"Handshake Failures:  {handshake_failures}")
    print(f"Connection Losses:   {connection_losses}")
    print(f"Total Failures:      {total_failures}")
    print(f"Failure Rate:        {failure_rate:.2f}%")
    
    print(f"\nMOST ACTIVE RELAY NODE")
    print("-" * 70)
    if most_active_relay[0]:
        print(f"Peer ID:             {most_active_relay[0]}")
        print(f"Relay Events:        {most_active_relay[1]}")
        pct_of_total = (most_active_relay[1] / relay_events * 100) if relay_events > 0 else 0
        print(f"% of Total Relays:   {pct_of_total:.1f}%")
    else:
        print("No relay events found")
    
    print("\n" + "="*70 + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python mission_analyzer.py <encrypted_telemetry_file>")
        print("Example: python mission_analyzer.py mission_telemetry_20260309_190650.enc")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    csv_text = decrypt_telemetry_file(file_path)
    rows = parse_csv_data(csv_text)
    analyze_telemetry(rows)


if __name__ == '__main__':
    main()
