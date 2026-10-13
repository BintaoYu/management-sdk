"""Dependency-free HTTP management of already deployed Runtime applications."""
from .client import ManagementClient, ManagementError

__all__ = ["ManagementClient", "ManagementError"]
__version__ = "0.1.0"
