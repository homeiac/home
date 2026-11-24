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
    ap.add_argument('--decode-report',type=Path)
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
        story=('Keep up to eight sampled moments so the event still makes sense. Resize previews to 768px and describe the main activity '
               'and observed changes; cap output at 256 tokens. Four-frame variants lost event detail. Replays exaggerated RTX gains, '
               'so its comparison resets runtime caches before synthetic warmup. Matched bars time model requests; live 10-minute '
               'averages include decoding, queueing and writes.'),
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
    if args.decode_report:
        decoded=json.loads(args.decode_report.read_text())
        modes={r['mode']:r for r in decoded}
        if set(modes)!= {'default','bounded','bounded2'} or any(r['cells']!=12 or r['frames']!=96 or r['errors'] or r['pixel_changes'] for r in decoded):
            raise ValueError('Decoder selection requires complete pixel-preserving comparisons')
        fastest=min(modes[m]['seconds'] for m in ('bounded','bounded2'))
        mode=next(m for m in ('bounded','bounded2') if modes[m]['seconds']<=fastest*1.05)
        threads={'bounded':1,'bounded2':2}[mode]
        result['selected']['video_decode_threads']=threads
        result['decode']=dict(selected_threads=threads,identical_percent=100,frame_comparisons=288,
            time_reduction_percent=round(100*(1-modes[mode]['seconds']/modes['default']['seconds']),1),
            trials=[dict(label={'default':'Default threads','bounded':'1 decoder thread','bounded2':'2 decoder threads'}[r['mode']],
                         mean_seconds=round(r['seconds']/r['cells'],3),**r) for r in decoded],
            method='Six fixed clips, two passes with reversed clip/configuration order for default vs one thread, followed by a two-thread pass in both clip orders. Low-priority extraction under live host load. Each mode extracted 96 frames; 288 decoded RGB arrays matched the original previews exactly. Measures wall time for reading/decoding/scaling/JPEG output; includes host contention.')
        result['story'] += ' Bounded decoder threads cut extraction time with identical frame pixels.'
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
