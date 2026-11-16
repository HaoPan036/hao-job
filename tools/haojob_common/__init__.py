"""Small standard-library helpers shared by the HaoJob tools.

Tools run as scripts, so each one adds the ``tools/`` directory to
``sys.path`` before importing this package. Only behaviour that is meant to be
identical across tools belongs here.
"""

from .text import clean_text, contains_job_id

__all__ = ["clean_text", "contains_job_id"]
