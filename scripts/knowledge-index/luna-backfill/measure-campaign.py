#!/usr/bin/env python3
"""Read-only elapsed-time and output accounting for the completed Luna campaign.

Prints aggregate timestamps and counts, never photo paths, captions or identities.
Current job timestamps include any correction pass; they are not summed model time.
"""
import datetime
import json
import sqlite3

LEDGER='/local-3TB-backup/photo-enrichment/luna-backfill/luna-ledger.sqlite3'
VIDEO="ext IN ('mp4','mov','3gp','avi','mpg','m4v')"


def elapsed(start, end):
    if start is None or end is None:return None
    return (datetime.datetime.fromisoformat(end)-datetime.datetime.fromisoformat(start)).total_seconds()


def main():
    with sqlite3.connect('file:'+LEDGER+'?mode=ro',uri=True) as db:
        start=db.execute('SELECT min(started) FROM jobs').fetchone()[0]
        rows=db.execute("SELECT CASE WHEN "+VIDEO+" THEN 'video' ELSE 'photo' END,count(*),min(started),min(finished),max(finished) FROM jobs WHERE state='ok' AND published=1 GROUP BY 1").fetchall()
        milestone=db.execute("SELECT finished FROM jobs WHERE state='ok' AND published=1 AND NOT ("+VIDEO+") ORDER BY finished,id LIMIT 1 OFFSET 69999").fetchone()
        result={'first_retained_attempt_utc':start,
                'published':[dict(zip(['kind','count','first_started_utc','first_finished_utc','last_finished_utc'],r)) for r in rows],
                'photo_70000_finished_utc':milestone[0] if milestone else None,
                'seconds_until_photo_70000':elapsed(start,milestone[0]) if milestone else None,
                'estimated_cost_plus_pilot_usd':db.execute("SELECT ((SELECT coalesce(sum(cost),0) FROM jobs)+(SELECT coalesce(sum(cost),0) FROM previous_captions)+(SELECT cast(value AS INTEGER) FROM config WHERE key='pilot_cost'))/1000000.0").fetchone()[0]}
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
