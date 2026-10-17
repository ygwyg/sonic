# sonic-modem (backend)

Python package for the Sonic OFDM acoustic data transmission engine.
See the repository root `README.md` for the full project documentation.

```bash
pip install -e ".[all]"
sonic encode input.py --output signal.wav
sonic decode signal.wav --output recovered.py
python -m pytest -q
```
