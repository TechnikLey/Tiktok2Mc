#!/usr/bin/env python3
"""Minimal command-line parsing shared by the supervisor entry points."""

import argparse


def parse_args():
    """Parse the command-line arguments shared by the supervisor binaries.

Returns:
    The argparse namespace; ``gui_hidden`` is true when the GUI should start
    without a visible window."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--gui-hidden", action="store_true")
    return parser.parse_args()
