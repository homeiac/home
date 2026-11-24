#!/usr/bin/env python3
"""Export only aggregate, completed trial cells for the generated dashboard."""
import argparse
import datetime
import json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('report',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--mac-parallel',type=int,choices=(1,2,4),required=True)
    ap.add_argument('--reviewed-pairs',type=int,required=True,help='Number of manually reviewed matched clip/backend pairs')
    args=ap.parse_args()
    if not 0 <= args.reviewed_pairs <= 12:
        ap.error('--reviewed-pairs must be between zero and twelve for this sample')
    rows=json.loads(args.report.read_text())
    def cell(profile,backend,block):
        row=next(r for r in rows if (r['profile'],r['backend'],r['block'])==(profile,backend,block))
        if row['ok']!=row['requests'] or row['requests']!=6:
            raise ValueError('Final comparison requires six valid results per cell')
        return dict(row)
    rtx_before=cell('current','rtx',12);rtx_after=cell('story_final','rtx',12)
    mac_before=cell('current','mac',10)
    mac_after=cell('story_final','mac',{1:14,2:13,4:10}[args.mac_parallel])
    selected=[]
    for row,label in ((rtx_before,'Before · 1024px / 2 requests'),(rtx_after,'After · 768px / 2 requests'),
                      (mac_before,'Before · 1024px / 4 requests'),(mac_after,f'After · 768px / {args.mac_parallel} request(s)')):
        row['label']=label;selected.append(row)
    gain=lambda before,after:round(100*(after['successful_per_minute']/before['successful_per_minute']-1),1)
    result=dict(status='selected',updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        selected=dict(frames=8,edge=768,prompt='video-story-v1',output_limit=256,rtx_requests=2,mac_requests=args.mac_parallel,mac_video_requests=args.mac_parallel,mac_photo_capacity=4),
        story=('Keep the story: up to eight chronological frames and a prompt focused on the main activity and supported changes. '
               '768px previews reduce model input; 256 output tokens bound the caption. Four-frame variants lost event detail; '
               'literal frame-by-frame prompts were less useful for recall. Replaying clips inflated RTX gains, so its final comparison '
               'resets the model cache and warms on synthetic frames. Live charts below track fresh production work.'),
        method=('Six fixed clips, 5.8–376.9 seconds. Short-clip frame cap and JPEG resizing match production. '
                'RTX: two requests, model-runtime reset and synthetic warmup before each cell; load/warmup excluded. '
                'Mac: warm server with prompt caching disabled; old four-request configuration vs selected concurrency. '
                'Caption cache bypassed. Media decode is precomputed for model trials. Shared homelab hardware; not a controlled quality benchmark.'),
        reviewed=args.reviewed_pairs,quality=('Manual comparison against six eight-frame contact sheets. '
            'Accepted for main-activity/event recall with remaining minor inferred details; not a blind accuracy score. '
            'No speech transcription is installed. Reconciliation still handles text disagreements.'),
        trials=selected,all_trials=rows,rtx_gain_percent=gain(rtx_before,rtx_after),mac_gain_percent=gain(mac_before,mac_after),
        token_reduction_percent=round(100*(1-rtx_after['prompt_tokens']/rtx_before['prompt_tokens']),1),valid_percent=100,
        live_validation=dict(status='pending'))
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
