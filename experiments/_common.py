import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
RESULTS = os.path.join(HERE, "..", "benchmarks", "results")
