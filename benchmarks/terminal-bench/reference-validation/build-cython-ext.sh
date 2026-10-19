#!/bin/bash
# Reference feasibility check only. Never installed into a model trial.
set -e
bash /reference/solve.sh
pip install 'planarity==0.6' pytest==8.4.1 pytest-json-ctrf==0.3.5
mkdir -p /logs/verifier
cd /app/pyknotid
pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
