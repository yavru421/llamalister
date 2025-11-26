from abc import ABC, abstractmethod
import sys

# Activate APT strict mode early for any agent import
try:
    import strict_mode  # noqa: F401 - activate strict mode (exits on uncaught exceptions)
except ImportError:
    # Strict mode is required by APT; fail fast if not present
    print("[APT FATAL ERROR] strict_mode module not found")
    sys.exit(1)
from typing import Dict, Any, Optional
import logging


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        log_level = self.config.get("log_level", "INFO")
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.max_runs: int = int(self.config.get("max_runs", 3))
        if self.max_runs <= 0:
            raise ValueError("max_runs must be greater than zero")
        self._run_count: int = 0
        self._expired: bool = False

    def safe_run(self, *args: Any, **kwargs: Any) -> Any:
        """
        Executes run() with logging, lifecycle checks, and error handling.
        """
        if self._expired:
            self.logger.warning(
                "Shelf life exhausted; no further runs (total=%s)", self._run_count
            )
            return {"status": "expired", "runs": self._run_count}

        run_number = self._run_count + 1
        self.logger.info("Starting run #%s with args=%s kwargs=%s", run_number, args, kwargs)

        try:
            result = self.run(*args, **kwargs)
            self.logger.info("Run #%s completed successfully", run_number)
            return result
        except Exception as exc:
            self.logger.exception("Run #%s failed: %s", run_number, exc)
            return {"status": "error", "message": str(exc)}
        finally:
            self._run_count += 1
            if self._run_count >= self.max_runs:
                self._expired = True
                self.logger.info(
                    "Shelf life reached after %s runs; future runs will be blocked",
                    self._run_count,
                )

    @abstractmethod
    def run(self, input: Any = None, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Standard agent execution interface.

        Args:
            input: Primary input data (string, dict, etc.)
            context: Optional context parameters (agent_source, entry_type, coordinates, etc.)

        Returns:
            Any: Agent execution result
        """
        raise NotImplementedError("Subclasses must implement run()")

    def reset_shelf_life(self, max_runs: Optional[int] = None) -> None:
        """
        Resets the lifecycle counter; optionally updates the allowed run count.
        """
        if max_runs is not None:
            if max_runs <= 0:
                raise ValueError("max_runs must be greater than zero")
            self.max_runs = max_runs
        self._run_count = 0
        self._expired = False

    @property
    def remaining_runs(self) -> int:
        """
        Returns how many runs remain before expiration.
        """
        return max(self.max_runs - self._run_count, 0)

    @property
    def is_expired(self) -> bool:
        """
        Indicates whether the agent has exhausted its shelf life.
        """
        return self._expired
