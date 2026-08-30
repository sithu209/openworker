"""Native OpenWorker agent runtime adapter."""

from ..engine import TurnEngine


class NativeRuntime(TurnEngine):
    """Expose the existing TurnEngine behind the runtime seam."""

    runtime_name = "native"
