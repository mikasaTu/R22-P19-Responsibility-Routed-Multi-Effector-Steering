"""RoboTwin 2.0 bimanual validation for R22-P19.

The package keeps simulator-privileged oracle evidence separate from learned
policy and deployability claims.  Importing it does not import RoboTwin; the
external checkout is selected explicitly by the runtime entrypoints.
"""

__all__ = ["wrappers", "responsibility", "operator", "baselines"]
