"""Compatibility entrypoint for the frozen calibration eligibility analysis."""

from stage3_hybrid.analyze import main

if __name__ == "__main__":
    raise SystemExit(main())

