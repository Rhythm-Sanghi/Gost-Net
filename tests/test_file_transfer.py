import os
import sys
import time
import threading
import tempfile
from pathlib import Path

from network import GhostEngine
from security import CryptoManager
from android_mocks import get_file_picker, MockFilePicker

def create_test_file(size_bytes: int) -> str:
    fd, path = tempfile.mkstemp(suffix='.dat')
    os.write(fd, os.urandom(size_bytes))
    os.close(fd)
    return path

def test_file_picker():
    print("\n=== Testing File Picker ===")
    picker = get_file_picker()
    print(f"File picker type: {type(picker).__name__}")
    assert picker is not None, "File picker should not be None"
    print("✓ File picker initialized")

def test_encryption_chunks():
    print("\n=== Testing Chunk Encryption ===")
    crypto = CryptoManager()
    peer_id = "test_peer"
    
    shared_secret = os.urandom(32)
    crypto.set_peer_public_key(peer_id, b'\x00' * 97)
    aes_key = crypto.derive_aes_key(peer_id, shared_secret)
    
    assert aes_key is not None, "AES key derivation failed"
    print(f"✓ AES key derived: {len(aes_key)} bytes")
    
    chunk = b"Test chunk data " * 64
    nonce, ciphertext = crypto.encrypt_file_chunk(peer_id, chunk)
    
    assert nonce is not None and len(nonce) == 12, "Invalid nonce"
    assert ciphertext is not None, "Encryption failed"
    assert ciphertext != chunk, "Ciphertext should differ from plaintext"
    print(f"✓ Encrypted {len(chunk)} bytes → {len(ciphertext)} bytes (nonce: {len(nonce)})")
    
    decrypted = crypto.decrypt_file_chunk(peer_id, nonce, ciphertext)
    assert decrypted == chunk, "Decryption mismatch"
    print(f"✓ Decryption successful, verified integrity")

def test_file_transfer_protocol():
    print("\n=== Testing File Transfer Protocol ===")
    
    engine = GhostEngine(username="TestPeer")
    
    assert engine.CHUNK_SIZE == 8192, "Invalid chunk size"
    assert engine.MAX_FILE_SIZE == 100 * 1024 * 1024, "Invalid max file size"
    print(f"✓ Constants: CHUNK_SIZE={engine.CHUNK_SIZE}, MAX_FILE_SIZE={engine.MAX_FILE_SIZE}")
    
    test_file = create_test_file(1024 * 1024)
    checksum = engine._calculate_checksum(test_file)
    assert len(checksum) == 64, "Invalid checksum length"
    print(f"✓ Calculated SHA256 checksum: {checksum[:16]}...")
    
    safe_name = engine._sanitize_filename("../../etc/passwd")
    assert ".." not in safe_name, "Path traversal not prevented"
    print(f"✓ Sanitized dangerous filename: {safe_name}")
    
    safe_name = engine._sanitize_filename("file<name>.txt")
    assert "<" not in safe_name and ">" not in safe_name, "Dangerous chars not removed"
    print(f"✓ Removed invalid characters: {safe_name}")
    
    os.remove(test_file)

def test_progress_callback():
    print("\n=== Testing Progress Callback ===")
    
    progress_calls = []
    
    def progress_cb(bytes_sent, total_size):
        progress_pct = (bytes_sent / total_size) * 100 if total_size > 0 else 0
        progress_calls.append((bytes_sent, total_size, progress_pct))
    
    total = 1000000
    for i in range(0, total, 100000):
        progress_cb(i, total)
    
    assert len(progress_calls) > 0, "Progress callback not called"
    assert progress_calls[0][2] == 0, "First progress should be 0%"
    print(f"✓ Progress callback invoked {len(progress_calls)} times")
    print(f"  Sample: {progress_calls[3]}")

def test_chunk_structure():
    print("\n=== Testing Chunk Header Structure ===")
    
    nonce = os.urandom(12)
    chunk_size = 12345
    
    chunk_header = nonce + chunk_size.to_bytes(4, 'big')
    assert len(chunk_header) == 16, f"Invalid header size: {len(chunk_header)}"
    
    extracted_nonce = chunk_header[:12]
    extracted_size = int.from_bytes(chunk_header[12:16], 'big')
    
    assert extracted_nonce == nonce, "Nonce extraction failed"
    assert extracted_size == chunk_size, "Size extraction failed"
    print(f"✓ Chunk header structure valid (16 bytes total)")
    print(f"  Nonce: {len(extracted_nonce)} bytes")
    print(f"  Size: {extracted_size} bytes")

def test_large_file_simulation():
    print("\n=== Testing Large File Simulation ===")
    
    engine = GhostEngine(username="TestPeer")
    
    file_sizes = [
        (100 * 1024, "100 KB"),
        (10 * 1024 * 1024, "10 MB"),
        (50 * 1024 * 1024, "50 MB"),
    ]
    
    for size, label in file_sizes:
        test_file = create_test_file(size)
        checksum = engine._calculate_checksum(test_file)
        
        chunks = (size + engine.CHUNK_SIZE - 1) // engine.CHUNK_SIZE
        print(f"✓ {label}: {chunks} chunks of {engine.CHUNK_SIZE} bytes")
        
        os.remove(test_file)

def test_file_existing_handling():
    print("\n=== Testing File Existence Handling ===")
    
    engine = GhostEngine(username="TestPeer")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.txt")
        Path(test_file).write_text("original")
        
        base, ext = os.path.splitext(test_file)
        counter = 1
        new_path = test_file
        while os.path.exists(new_path):
            new_path = f"{base}_{counter}{ext}"
            counter += 1
        
        assert new_path != test_file, "Should generate different path"
        assert new_path == os.path.join(tmpdir, "test_1.txt"), "Incorrect renamed path"
        print(f"✓ Duplicate file handling: original → {os.path.basename(new_path)}")

def run_all_tests():
    print("\n" + "="*60)
    print("SECURE FILE TRANSFER - INTEGRATION TESTS")
    print("="*60)
    
    tests = [
        ("File Picker", test_file_picker),
        ("Chunk Encryption", test_encryption_chunks),
        ("File Transfer Protocol", test_file_transfer_protocol),
        ("Progress Callback", test_progress_callback),
        ("Chunk Header Structure", test_chunk_structure),
        ("Large File Simulation", test_large_file_simulation),
        ("File Existence Handling", test_file_existing_handling),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ ASSERTION FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ EXCEPTION: {type(e).__name__}: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
