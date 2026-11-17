"""Small standard-library helpers shared by the HaoJob tools.

Tools run as scripts, so each one adds the ``tools/`` directory to
``sys.path`` before importing this package. Only behaviour that is meant to be
identical across tools belongs here.
"""

from .paths import PathPolicyError, reject_symlinks, require_private_path
from .text import clean_text, contains_job_id
from .urls import canonical_url

__all__ = ["PathPolicyError", "canonical_url", "clean_text", "contains_job_id",
           "reject_symlinks", "require_private_path"]
