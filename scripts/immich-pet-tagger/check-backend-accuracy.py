#!/usr/bin/env python3
"""Run owner-reviewed holdouts on every backend without modifying Immich."""
import argparse
import json
import logging
from pathlib import Path
from benchmark import run


def main() -> None:
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('holdout',type=Path)
    parser.add_argument('inventory',type=Path)
    parser.add_argument('--workers',nargs='+',default=['mac','pve','still-fawn'],choices=['mac','pve','still-fawn','fun-bedbug','chief-horse'])
    args=parser.parse_args()
    truth=json.loads(args.holdout.read_text())
    ids=set(truth['positive']+truth['negative'])
    assets=[a for a in json.loads(args.inventory.read_text()) if a['id'] in ids]
    assert len(assets)==len(ids)==26
    for worker in args.workers:
        run('holdout-'+worker,assets,[worker])


if __name__=='__main__':
    main()
