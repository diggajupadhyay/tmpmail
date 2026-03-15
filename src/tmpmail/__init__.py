"""tmpmail - A temporary email right from your terminal."""

__version__ = "1.2.3"
__author__ = "Siddharth Dushantha"
__email__ = "siddharth.dushantha@gmail.com"

from tmpmail.cli import TmpMail, main

__all__ = ["TmpMail", "main", "__version__"]
