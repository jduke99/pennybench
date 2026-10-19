#!/bin/bash
# Reference-only missing build dependency. Never injected into model trials.
set -e
sudo apt-get update -qq
sudo apt-get install -y cmake
bash /reference/solve.sh
bash /tests/test.sh
