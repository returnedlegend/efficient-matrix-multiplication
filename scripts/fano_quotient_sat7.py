"""Prepare one pinned Fano formula without launching a solver."""
import argparse
import json
from pathlib import Path
import signal
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT), str(ROOT/'.xor-deps')]
from mmsearch.fano_quotient_adapter7 import load_pinned_case
from mmsearch.marathon7_cached_guard import CampaignGuard


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign',type=Path,default=ROOT/'artifacts/marathon7_20261103T122417Z')
    parser.add_argument('--ordinal',type=int,choices=(2,3),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=20)
    parser.add_argument('--memory-mb',type=int,default=1024)
    args=parser.parse_args()
    guard=CampaignGuard(args.seconds,'2026-11-03T19:24:17Z',guard_state=args.campaign/'operations-v3/state.json',campaign_dir=args.campaign)
    signal.signal(signal.SIGTERM,lambda *_:guard.stop());signal.signal(signal.SIGINT,lambda *_:guard.stop())
    guard.check('pre_fano_input');case=load_pinned_case(args.campaign,args.ordinal);guard.check('post_fano_input')
    result=dict(status='PREPARED_NO_SOLVER_QUERY',case=case['case'],input_core_sha256=case['input_core_sha256'],metadata_case_sha256=case['metadata_case_sha256'],formula=case['problem'],solver_calls=0)
    guard.check('pre_fano_result');args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:json.dump(result,stream,sort_keys=True);stream.write('\n')
    guard.check('post_fano_result')
    print(json.dumps(dict(status=result['status'],case=case['case'],metadata=case['problem']['metadata'],solver_calls=0),sort_keys=True))


if __name__=='__main__':main()
