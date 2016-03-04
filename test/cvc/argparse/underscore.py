import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--no-cache", action="store_true")
args = parser.parse_args()

if args.no_cache:
    print("verbosity turned on")