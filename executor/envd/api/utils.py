#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Utility functions for envd REST API
"""

import os
import re
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException

from shared.logger import setup_logger

logger = setup_logger("envd_api_utils")

# Allowed base directories for file operations
ALLOWED_BASE_PATHS = [
    "/workspace",
    "/home",
    "/tmp",
    str(Path.home()),
]

# Dangerous path patterns to block
DANGEROUS_PATTERNS = [
    r"\.\.",  # Parent directory traversal
    r"^~",    # Home directory expansion
    r"\0",    # Null byte
]


def verify_access_token(x_access_token: Optional[str] = Header(None)) -> bool:
    """Stub authentication - accepts token but doesn't validate"""
    if x_access_token:
        logger.debug(f"Access token received (not validated): {x_access_token[:10]}...")
    return True


def verify_signature(
    signature: Optional[str], signature_expiration: Optional[int]
) -> bool:
    """Stub signature verification - logs but doesn't validate"""
    if signature:
        logger.debug(f"Signature received (not validated): {signature[:10]}...")
    if signature_expiration:
        logger.debug(f"Signature expiration: {signature_expiration}")
    return True


def _is_path_safe(path: str) -> bool:
    """
    Check if path contains dangerous patterns.

    Args:
        path: Path string to check

    Returns:
        True if path is safe, False otherwise
    """
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, path):
            return False
    return True


def _resolve_allowed_base(path: Path) -> Optional[Path]:
    """
    Find which allowed base directory a path belongs to.

    Args:
        path: Absolute path to check

    Returns:
        The matching base path or None
    """
    try:
        resolved = path.resolve()
        for base in ALLOWED_BASE_PATHS:
            base_path = Path(base).resolve()
            try:
                resolved.relative_to(base_path)
                return base_path
            except ValueError:
                continue
    except (OSError, ValueError):
        pass
    return None


def resolve_path(
    path: Optional[str], username: Optional[str], default_workdir: Optional[str]
) -> Path:
    """
    Resolve file path, handling relative paths and user home directories.
    Security-hardened against path traversal attacks.

    Args:
        path: File path (absolute or relative)
        username: Username for resolving relative paths
        default_workdir: Default working directory

    Returns:
        Resolved absolute Path

    Raises:
        HTTPException: If path is not provided, contains dangerous patterns,
                      or resolves outside allowed directories
    """
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")

    # Security check: block dangerous patterns
    if not _is_path_safe(path):
        logger.warning(f"Blocked dangerous path pattern: {path}")
        raise HTTPException(status_code=400, detail="Invalid path: contains dangerous patterns")

    p = Path(path)

    # If relative path, resolve against user home or default workdir
    if not p.is_absolute():
        if username:
            # Resolve relative to user's home
            user_home = (
                Path.home()
                if username == os.getenv("USER")
                else Path(f"/home/{username}")
            )
            p = user_home / p
        elif default_workdir:
            p = Path(default_workdir) / p
        else:
            # Use current working directory
            p = Path.cwd() / p

    # Resolve to absolute path (removes symlinks and ..)
    try:
        resolved = p.resolve()
    except (OSError, ValueError) as e:
        logger.warning(f"Failed to resolve path {p}: {e}")
        raise HTTPException(status_code=400, detail="Invalid path")

    # Security check: ensure path is within allowed directories
    allowed_base = _resolve_allowed_base(resolved)
    if allowed_base is None:
        logger.warning(f"Path {resolved} is outside allowed directories")
        raise HTTPException(status_code=403, detail="Access denied: path outside allowed directories")

    return resolved
