# Gost-Net

[![CI](https://github.com/Rhythm-Sanghi/Gost-Net/actions/workflows/build.yml/badge.svg)](https://github.com/Rhythm-Sanghi/Gost-Net/actions/workflows/build.yml)

A Python/Kivy messaging prototype for communication over a local network.
Peers discover one another over UDP and exchange messages and files over TCP.
The application includes encrypted storage, delivery acknowledgements, message
expiry, local maps, and Android transport adapters.

## Run on desktop

Use Python 3.10 or 3.11 in an isolated environment:

```sh
git clone https://github.com/Rhythm-Sanghi/Gost-Net.git
cd Gost-Net
python -m venv .venv
```

Activate `.venv` (`.venv\Scripts\Activate.ps1` on Windows or
`source .venv/bin/activate` on Linux/macOS), then:

```sh
python -m pip install -r requirements.txt
python main.py
```

Connect devices to the same local network and allow the application through the
local firewall. UDP discovery uses port 37020; TCP uses 37021 or a dynamic port.
The existing default master PIN is `1234`; the duress PIN is `9999`. Change them
in Settings before storing personal messages. Use disposable data when testing
duress mode or emergency wipe.

## Supported application and limits

- LAN discovery, TCP messaging, application acknowledgements and retry.
- Chunked file transfer with SHA-256 checks and temporary `.part` files.
- Local SQLite storage with encrypted content, expiry and ephemeral mode.
- Peer identity checks and out-of-band safety numbers.
- Location/waypoint tools, local maps, and CoT/GeoJSON exchange.
- Android Bluetooth, Wi-Fi Direct, audio and service adapters whose physical
  device qualification remains incomplete.

The [capability table](docs/CAPABILITIES.md) separates source implementation,
automated tests, desktop checks and physical Android qualification. A successful
build or mocked test does not establish operation on physical Android devices.

Runtime session agreement uses SECP384R1 ECDH with Ed25519 identities and
AES-GCM message encryption; see [the crypto specification](docs/CRYPTO_SPEC.md).
This is not an independently audited secure messenger. Python memory clearing
and logical database deletion do not establish complete erasure of runtime
copies, filesystem remnants or backups. Safety-number comparison helps detect
identity mismatches; it does not guarantee the absence of every attack.

## Tests and Android builds

```sh
python -m pytest tests/
```

[GitHub Actions](https://github.com/Rhythm-Sanghi/Gost-Net/actions/workflows/build.yml)
runs the configured tests and Android build. Use the linked run for current
results rather than a fixed test count. Physical-device checks are described in
[Android field qualification](docs/ANDROID_FIELD_QUALIFICATION.md).

## Research

[`research/`](research/README.md) contains standalone mesh, radio, cryptography
and networking experiments. These modules are excluded from the normal release
build and are not supported runtime features. Run their tests separately:

```sh
python -m pytest research/tests/
```

## Documentation

- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Security architecture](docs/SECURITY_ARCHITECTURE.md)
- [Cryptography and review questions](docs/CRYPTO_SPEC.md)
- [Maintenance](docs/MAINTENANCE.md)

## License

MIT. See [LICENSE](LICENSE).
