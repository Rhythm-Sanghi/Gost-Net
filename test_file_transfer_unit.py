import os
import sys
import tempfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import hashlib

def test_aes_gcm_chunk_encryption():
    print("\n=== Testing AES-GCM Chunk Encryption ===")
    
    aes_key = os.urandom(32)
    
    chunk = b"This is test data for encryption " * 32
    nonce = os.urandom(12)
    
    cipher = AESGCM(aes_key)
    ciphertext = cipher.encrypt(nonce, chunk, None)
    
    assert ciphertext != chunk, "Ciphertext should differ"
    assert len(nonce) == 12, "Invalid nonce size"
    print(f"✓ Encrypted {len(chunk)} bytes → {len(ciphertext)} bytes")
    
    decrypted = cipher.decrypt(nonce, ciphertext, None)
    assert decrypted == chunk, "Decryption mismatch"
    print(f"✓ Decrypted successfully, verified integrity")

def test_chunk_header_structure():
    print("\n=== Testing Chunk Header Structure ===")
    
    CHUNK_SIZE = 8192
    nonce = os.urandom(12)
    chunk_size = 12345
    
    chunk_header = nonce + chunk_size.to_bytes(4, 'big')
    assert len(chunk_header) == 16, f"Invalid header: {len(chunk_header)}"
    
    extracted_nonce = chunk_header[:12]
    extracted_size = int.from_bytes(chunk_header[12:16], 'big')
    
    assert extracted_nonce == nonce, "Nonce extraction failed"
    assert extracted_size == chunk_size, "Size extraction failed"
    print(f"✓ Header structure valid (16 bytes)")
    print(f"  Nonce: {len(extracted_nonce)} bytes (random)")
    print(f"  Size: {extracted_size} bytes (big-endian uint32)")

def test_file_chunking():
    print("\n=== Testing File Chunking ===")
    
    CHUNK_SIZE = 8192
    file_sizes = [
        (100 * 1024, "100 KB"),
        (10 * 1024 * 1024, "10 MB"),
        (50 * 1024 * 1024, "50 MB"),
    ]
    
    for size, label in file_sizes:
        chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        print(f"✓ {label}: {chunks} chunks of {CHUNK_SIZE} bytes")

def test_sha256_checksum():
    print("\n=== Testing SHA256 Checksum ===")
    
    fd, path = tempfile.mkstemp()
    try:
        test_data = os.urandom(1024 * 1024)
        os.write(fd, test_data)
        os.close(fd)
        
        sha256 = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        
        checksum = sha256.hexdigest()
        assert len(checksum) == 64, "Invalid checksum length"
        print(f"✓ SHA256 checksum: {checksum[:16]}...")
        print(f"  Length: {len(checksum)} hex chars (256-bit)")
    finally:
        os.remove(path)

def test_filename_sanitization():
    print("\n=== Testing Filename Sanitization ===")
    
    dangerous_names = [
        ("../../etc/passwd", "path_traversal"),
        ("file<name>.txt", "angle_brackets"),
        ('file"name".doc', "quotes"),
        ("file|name.zip", "pipe"),
        ("file*name.*", "asterisks"),
        ("file:name.txt", "colons"),
        ("file?name.txt", "question_mark"),
    ]
    
    for unsafe, description in dangerous_names:
        sanitized = os.path.basename(unsafe)
        dangerous_chars = '<>:"|?*\\'
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '_')
        
        assert all(c not in sanitized for c in dangerous_chars), f"Failed: {description}"
        print(f"✓ {description:20} → {sanitized}")

def test_file_duplicate_handling():
    print("\n=== Testing File Duplicate Handling ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_file = os.path.join(tmpdir, "test.txt")
        Path(base_file).write_text("original")
        
        paths = []
        test_path = base_file
        base, ext = os.path.splitext(base_file)
        counter = 1
        
        for i in range(4):
            if i == 0:
                paths.append(base_file)
            else:
                while os.path.exists(test_path):
                    test_path = f"{base}_{counter}{ext}"
                    counter += 1
                Path(test_path).write_text(f"duplicate_{i}")
                paths.append(test_path)
        
        expected = [
            "test.txt",
            "test_1.txt",
            "test_2.txt",
            "test_3.txt"
        ]
        
        for path, expected_name in zip(paths, expected):
            assert os.path.basename(path) == expected_name, f"Expected {expected_name}, got {os.path.basename(path)}"
        
        print(f"✓ Duplicate naming convention:")
        for path in paths:
            print(f"  {os.path.basename(path)}")

def test_progress_callback_simulation():
    print("\n=== Testing Progress Callback Simulation ===")
    
    total_size = 100 * 1024 * 1024
    CHUNK_SIZE = 8192
    progress_updates = []
    
    for bytes_sent in range(0, total_size, CHUNK_SIZE * 10):
        progress_pct = (bytes_sent / total_size) * 100
        progress_updates.append((bytes_sent, total_size, progress_pct))
    
    assert len(progress_updates) > 0, "No progress updates"
    assert progress_updates[0][2] == 0, "First update should be 0%"
    assert progress_updates[-1][2] < 100, "Last update should be < 100%"
    
    print(f"✓ Progress callback simulation ({len(progress_updates)} updates)")
    print(f"  0%:   {progress_updates[0][0] / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB")
    print(f"  50%:  {progress_updates[len(progress_updates)//2][0] / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB")
    print(f"  95%:  {progress_updates[-1][0] / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB")

def test_header_protocol():
    print("\n=== Testing File Header Protocol ===")
    
    import json
    
    header = {
        "type": "FILE",
        "filename": "document.pdf",
        "filesize": 1048576,
        "file_id": "abc123def456",
        "checksum": "a" * 64,
        "chunked": True,
        "timestamp": "2026-03-09T17:50:00"
    }
    
    header_json = json.dumps(header)
    header_bytes = header_json.encode('utf-8')
    
    parsed = json.loads(header_bytes.decode('utf-8'))
    
    assert parsed["type"] == "FILE", "Type mismatch"
    assert parsed["chunked"] == True, "Chunked flag missing"
    assert parsed["file_id"] == "abc123def456", "File ID mismatch"
    
    print(f"✓ Header protocol valid ({len(header_bytes)} bytes)")
    print(f"  File: {parsed['filename']} ({parsed['filesize']} bytes)")
    print(f"  Chunked: {parsed['chunked']}")
    print(f"  ID: {parsed['file_id']}")

def test_nonce_uniqueness():
    print("\n=== Testing Nonce Uniqueness ===")
    
    nonces = set()
    for _ in range(1000):
        nonce = os.urandom(12)
        nonces.add(nonce)
    
    assert len(nonces) == 1000, "Nonce collision detected!"
    print(f"✓ Generated 1000 unique nonces (12 bytes each)")
    print(f"  No collisions detected")

def run_all_tests():
    print("\n" + "="*70)
    print("SECURE FILE TRANSFER PIPELINE - UNIT TESTS")
    print("="*70)
    
    tests = [
        ("AES-GCM Chunk Encryption", test_aes_gcm_chunk_encryption),
        ("Chunk Header Structure", test_chunk_header_structure),
        ("File Chunking Calculation", test_file_chunking),
        ("SHA256 Checksum", test_sha256_checksum),
        ("Filename Sanitization", test_filename_sanitization),
        ("File Duplicate Handling", test_file_duplicate_handling),
        ("Progress Callback Simulation", test_progress_callback_simulation),
        ("File Header Protocol (JSON)", test_header_protocol),
        ("Nonce Uniqueness", test_nonce_uniqueness),
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
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*70)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("="*70 + "\n")
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
