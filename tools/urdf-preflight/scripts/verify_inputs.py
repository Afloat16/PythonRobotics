"""Deterministic XML byte-mutation smoke test; not a replacement for fuzzing."""
from pathlib import Path
import json
import random
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from urdf_preflight import check_text

rng = random.Random(20260930)
seed = ('<robot name="r"><link name="a"/><link name="b"/>'
        '<joint name="j" type="continuous"><parent link="a"/>'
        '<child link="b"/><axis xyz="0 1 0"/></joint></robot>')
for _ in range(10000):
    data = bytearray(seed.encode())
    for _ in range(rng.randint(1, 7)):
        data[rng.randrange(len(data))] = rng.randrange(256)
    check_text(bytes(data))
print(json.dumps({'mutated_inputs': 10000, 'uncaught_exceptions': 0, 'seed': 20260930}))
