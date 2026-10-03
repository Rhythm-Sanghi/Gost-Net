#!/usr/bin/env python3
"""
Gost-Net - Master Release Qualification & Verification Script (v1.0.0-rc1)
Enforces syntax compilation, core importability, crypto dependency verification,
research isolation (zero-leak AST checks), packaging spec validation, secret scans,
and official test suite execution.
"""

import sys
import os
import ast
import subprocess
import compileall
import time
import glob

RESEARCH_MODULE_NAMES = {
    "acoustic_handshake", "adaptive_modulation", "anti_jamming", "anti_replay",
    "bearer_failover", "bundle_protocol", "chaos_fuzzer", "cognitive_radio",
    "collaborative_ecm", "compact_framing", "cot_geojson", "covert_channel",
    "dsss_modulation", "dtn_pubsub", "duty_cycler", "ephemeral_handshake",
    "fec_engine", "frequency_agility", "fuzzy_routing", "geocast",
    "group_rekeying", "homomorphic_aggregation", "link_budget", "memory_scrubber",
    "merkle_vault", "mesh_healing", "mesh_time_sync", "mesh_topology",
    "multipath_routing", "network_coding", "post_quantum_kem", "proximity_crypto",
    "qos_shaper", "quantum_resilient", "remote_wipe", "rf_signature",
    "sovereign_identity", "spatial_privacy", "stego_transport", "swarm_consensus",
    "tactical_dht", "tactical_hud", "tak_bridge", "traffic_camouflage",
    "transport_bearer", "virtual_array", "zkp_auth"
}

def run_step(description, func):
    print(f"\n========================================================")
    print(f"[*] {description}")
    print(f"========================================================")
    t0 = time.time()
    try:
        success = func()
    except Exception as e:
        print(f"[!] EXCEPTION in {description}: {e}")
        success = False
    duration = time.time() - t0
    if not success:
        print(f"[!] FAILED: {description} ({duration:.2f}s)")
        sys.exit(1)
    print(f"[+] PASSED: {description} ({duration:.2f}s)")

def check_compilation():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(root_dir, 'src')
    main_py = os.path.join(root_dir, 'main.py')
    service_py = os.path.join(root_dir, 'service.py')
    
    print("Compiling all Python files...")
    ok = compileall.compile_dir(src_dir, quiet=1)
    ok = ok and compileall.compile_file(main_py, quiet=1)
    ok = ok and compileall.compile_file(service_py, quiet=1)
    return bool(ok)

def check_core_importability_and_crypto():
    """Validates that production entrypoints and cryptographic primitives import cleanly."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    try:
        import cryptography
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
        from cryptography.fernet import Fernet
        print(f"Verified cryptography {cryptography.__version__} with AESGCM, HKDF, SECP384R1, Ed25519, Fernet.")
    except Exception as e:
        print(f"[!] Cryptography import verification failed: {e}")
        return False

    try:
        import main
        import service
        print("Verified production entrypoints (main, service) import successfully.")
    except Exception as e:
        print(f"[!] Core entrypoint import failed: {e}")
        return False

    return True

def check_research_isolation():
    """Ensures production source code contains zero imports from research modules."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(root_dir, 'src')
    targets = [os.path.join(root_dir, 'main.py'), os.path.join(root_dir, 'service.py')]
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith('.py'):
                targets.append(os.path.join(root, f))

    violations = []
    for filepath in targets:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            try:
                tree = ast.parse(f.read(), filename=filepath)
            except SyntaxError as se:
                print(f"[!] Syntax error parsing {filepath}: {se}")
                return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_base = alias.name.split('.')[0]
                    if mod_base == "research" or mod_base in RESEARCH_MODULE_NAMES:
                        violations.append((filepath, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod_base = node.module.split('.')[0]
                    if mod_base == "research" or mod_base in RESEARCH_MODULE_NAMES:
                        violations.append((filepath, node.module))

    if violations:
        print("[!] Research isolation violated! Production code imports research modules:")
        for vp, vm in violations:
            print(f"    - {vp} -> {vm}")
        return False

    print(f"Research isolation verified: 0 research imports found across {len(targets)} production source files.")
    return True

def check_buildozer_spec():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec_path = os.path.join(root_dir, 'buildozer.spec')
    if not os.path.exists(spec_path):
        print(f"buildozer.spec missing at {spec_path}")
        return False
    with open(spec_path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert ("android.api = 36" in content or "android.api = 33" in content), "Missing android.api = 36 (or 33)"
    assert ("android.minapi = 21" in content or "android.minapi = 26" in content), "Missing android.minapi"
    assert "research" in content and "experiments" in content, "Missing research/experiments in source.exclude_dirs"
    assert "title = Gost-Net" in content, "App title in buildozer.spec must be Gost-Net"
    print("buildozer.spec validated (title Gost-Net, target API 36/33, research excluded).")
    return True

def check_required_files():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    required = [
        'main.py',
        'service.py',
        'buildozer.spec',
        'buildozer-sideload.spec',
        'buildozer-api36.spec',
        'requirements.txt',
        'requirements-lock.txt',
        'src/config.py',
        'src/network.py',
        'src/network_state.py',
        'src/auth_manager.py',
        'src/storage.py',
        'src/database.py',
        'src/security.py',
        'src/routing.py',
        'src/audio_manager.py',
        'src/diagnostics.py',
        'src/logger.py',
        'research/README.md',
    ]
    for rel in required:
        path = os.path.join(root_dir, rel)
        if not os.path.exists(path):
            print(f"[!] Required file missing: {rel}")
            return False
    print(f"All {len(required)} canonical release files verified present.")
    return True

def check_no_release_secrets():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(root_dir, 'src')
    suspicious = [
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----"
    ]
    
    scan_files = [
        os.path.join(root_dir, 'main.py'),
        os.path.join(root_dir, 'service.py'),
        os.path.join(root_dir, 'buildozer.spec'),
        os.path.join(root_dir, '.env.example')
    ]
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith('.py'):
                scan_files.append(os.path.join(root, f))

    for fp in scan_files:
        if not os.path.exists(fp):
            continue
        with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
            content = fh.read()
            for pattern in suspicious:
                if pattern in content:
                    print(f"[!] Suspicious secret found in {fp}: {pattern}")
                    return False
    print(f"Secret scan completed: zero unencrypted private key blocks found across {len(scan_files)} release files.")
    return True

def run_official_tests():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [sys.executable, "-m", "pytest", "tests/"]
    print(f"Executing with 300s timeout: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, cwd=root_dir, timeout=300)
        return res.returncode == 0
    except subprocess.TimeoutExpired:
        print("[!] Pytest execution timed out after 300s!")
        return False

def verify_temp_cleanup():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    junk = glob.glob(os.path.join(root_dir, "*.mbtiles")) + glob.glob(os.path.join(root_dir, "*.part"))
    for j in junk:
        try:
            os.remove(j)
            print(f"Cleaned leftover test file: {j}")
        except:
            pass
    return True

def main():
    start_time = time.time()
    print("Starting Gost-Net Release Qualification (v1.0.0-rc1)...")
    run_step("1. Python Compilation Check", check_compilation)
    run_step("2. Core Importability & Cryptography Check", check_core_importability_and_crypto)
    run_step("3. Research Isolation (Zero Leak) AST Scan", check_research_isolation)
    run_step("4. Packaging Spec Validation", check_buildozer_spec)
    run_step("5. Canonical Release Files Inspection", check_required_files)
    run_step("6. Release Secret Scan", check_no_release_secrets)
    run_step("7. Official Core Test Suite Execution", run_official_tests)
    run_step("8. Temporary Artifact Cleanup Verification", verify_temp_cleanup)
    total_time = time.time() - start_time
    print("\n========================================================")
    print(f"[SUCCESS] All release qualification checks passed in {total_time:.2f}s.")
    print("========================================================\n")

if __name__ == '__main__':
    main()
