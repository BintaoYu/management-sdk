"""Dependency-free HTTP management of the current application through Apps HTTP."""
from .client import ManagementClient, ManagementError

__all__ = ["ManagementClient", "ManagementError"]
__version__ = "0.3.0"
