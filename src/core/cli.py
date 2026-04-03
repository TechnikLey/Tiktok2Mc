import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui-hidden", action="store_true")
    parser.add_argument("--register-only", action="store_true")
    return parser.parse_args()