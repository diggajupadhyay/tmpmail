"""Tests for tmpmail package."""

import pytest
from tmpmail import TmpMail, __version__


def test_version():
    """Test that the version is set correctly."""
    assert __version__ == "1.2.3"


def test_tmpmail_initialization():
    """Test that TmpMail class initializes correctly."""
    tmpmail = TmpMail()
    assert tmpmail.tmpmail_dir is not None
    assert tmpmail.browser == "w3m"
    assert tmpmail.raw_text is False


def test_get_domains():
    """Test getting available domains."""
    tmpmail = TmpMail()
    domains = tmpmail.get_domains()
    assert isinstance(domains, list)
    assert len(domains) > 0
    assert all(isinstance(d, str) for d in domains)
