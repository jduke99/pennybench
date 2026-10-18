#!/bin/bash
mkdir -p /logs/verifier
expected=$(python3 - <<'PY'
for i in range(1, 31):
    print("FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else i)
PY
)
actual=$(python3 /app/fizzbuzz.py 30 2>/dev/null)
if [ "$actual" == "$expected" ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
