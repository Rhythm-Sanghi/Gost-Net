# Capability and verification status

This is the maintained capability table for the application under `src/`.
The earlier desktop checks and automated tests are useful evidence, but do not
establish physical Android behavior. Current automated results are available in
[CI](https://github.com/Rhythm-Sanghi/Gost-Net/actions/workflows/build.yml).

| Capability | Implementation | Automated evidence | Desktop qualification | Physical Android qualification |
|---|---|---|---|---|
| Ed25519 identities and SECP384R1 ECDH | `src/security.py` | `tests/test_ghostnet.py` crypto tests | Prior desktop checks reported; rerun for a release | Not established |
| Ratchet and AES-GCM messages | `src/security.py` | `tests/test_ghostnet.py` | Prior desktop checks reported | Not established |
| LAN discovery, TCP, acknowledgements and deduplication | `src/network.py` | `tests/` protocol and process tests | Prior multi-process checks reported | Not established |
| File transfers and resumption | `src/network.py` | `tests/` | Prior desktop checks reported | Not established |
| Encrypted content storage, PIN and expiry | `src/database.py`, `src/auth_manager.py` | `tests/` storage/authentication tests | Prior desktop checks reported | Not established |
| Duress and inactivity cleanup | Application/security modules | `tests/` | Logical cleanup only; complete erasure is not guaranteed | Not established |
| Maps, waypoints and location exchange | Application map/network modules | Headless tests and source inspection | GUI/device behavior needs release checks | Not established |
| Voice notes | Audio adapters | Headless container/platform tests | Real capture/playback needs qualification | Not established |
| Bluetooth and Wi-Fi Direct | Android adapters | Mock platform tests | Not a desktop qualification of Android transport | Not established |
| Android permissions and foreground service | Android adapters and `service.py` | Mock platform tests and build configuration | Not applicable | Not established |

Review [ANDROID_FIELD_QUALIFICATION.md](ANDROID_FIELD_QUALIFICATION.md) before
claiming physical device support. Record devices, OS versions, build revision,
commands and results when updating this table. Distribution profiles and SDK
versions are defined in `buildozer.spec` and the build workflow; build targets
alone are not a tested-device list.

## Experimental modules

Radio models, advanced mesh algorithms, audio steganography, acoustic handshakes
and experimental cryptographic constructs are catalogued in
[research/README.md](../research/README.md). They are excluded from the release
runtime and do not extend the application's supported security claims.
