# Gost-Net

Gost-Net is a Python and Kivy experiment in peer-to-peer messaging. It explores how nearby devices can exchange messages and files over local links and queue messages while a peer is unavailable.

## Desktop demo

With Python 3.10 or 3.11, clone the repository, then run the following in a virtual environment from the repository root:

```sh
python -m pip install -r requirements.txt
python main.py
```

Run the automated tests with `python -m pytest -q` after installing pytest.

## Project status

The desktop demo and automated tests cover parts of the protocol. Android device results and open checks are tracked in the [field qualification notes](docs/ANDROID_FIELD_QUALIFICATION.md). This is a networking research prototype. Use test messages while evaluating it.

See the [capability matrix](docs/CAPABILITY_MATRIX.md) for the current implementation status.
