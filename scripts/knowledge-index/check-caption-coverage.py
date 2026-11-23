#!/usr/bin/env python3
"""Read-only coverage audit of current media against both published caption sets.

Run with Piglet's knowledge-index venv. Prints counts only, never media identities.
Album-copy exclusion follows the existing name-and-size rule, not a content hash.
"""
import json
import duckdb

INDEX = '/local-3TB-backup/knowledge-index'
LUNA = '/local-3TB-backup/photo-enrichment/luna-backfill/luna_codex_captions/*.parquet'


def main() -> None:
    """Compare exact current (path, size) versions with successful saved captions."""
    with duckdb.connect(INDEX + '/knowledge.duckdb', read_only=True) as db:
        db.execute('SET threads=2')
        db.execute("""CREATE TEMP TABLE inventory AS
            SELECT DISTINCT path,size_bytes,name,
                lower(ext) IN ('mp4','mov','3gp','avi','mpg','m4v') AS video,
                regexp_matches(path, '/Photos from [0-9]{4}/') AS annual
            FROM gphotos_files WHERE kind='media'""")
        db.execute("""CREATE TEMP TABLE coverage AS WITH local_saved AS (
                SELECT DISTINCT path,size_bytes FROM read_parquet(?,union_by_name=true)
                WHERE source='gphotos' AND status='ok'),
            luna_saved AS (
                SELECT DISTINCT source_path AS path,size_bytes FROM read_parquet(?,union_by_name=true)
                WHERE state='ok')
            SELECT a.*, l.path IS NOT NULL AS local_saved, c.path IS NOT NULL AS luna_saved,
                NOT a.annual AND EXISTS (SELECT 1 FROM inventory y
                    WHERE y.annual AND y.name=a.name AND y.size_bytes=a.size_bytes) AS album_copy
            FROM inventory a LEFT JOIN local_saved l USING(path,size_bytes)
            LEFT JOIN luna_saved c USING(path,size_bytes)""", [INDEX + '/summaries/*/*.parquet', LUNA])
        for label, where in [('all_media_paths','true'),('excluding_album_copies','NOT album_copy')]:
            rows = db.execute('''SELECT CASE WHEN video THEN 'video' ELSE 'photo' END AS kind,
                count(*) AS total,
                count(*) FILTER (WHERE local_saved OR luna_saved) AS captioned,
                count(*) FILTER (WHERE NOT local_saved AND NOT luna_saved) AS missing,
                count(*) FILTER (WHERE local_saved AND luna_saved) AS both_models,
                count(*) FILTER (WHERE local_saved) AS local_total,
                count(*) FILTER (WHERE luna_saved) AS luna_total,
                count(*) FILTER (WHERE local_saved AND NOT luna_saved) AS local_only,
                count(*) FILTER (WHERE luna_saved AND NOT local_saved) AS luna_only
                FROM coverage WHERE ''' + where + ' GROUP BY video ORDER BY video').fetchall()
            print(json.dumps({label: [dict(zip(['kind','total','captioned','missing','both_models',
                'local_total','luna_total','local_only','luna_only'], row)) for row in rows]}))
        db.execute('''CREATE TEMP TABLE seeded AS SELECT path,size_bytes,state FROM read_parquet(
            '/local-3TB-backup/photo-enrichment/summary-reconciliation/current_inputs.parquet')''')
        paired=db.execute('''SELECT
            count(*) FILTER (WHERE local_saved AND luna_saved),
            count(*) FILTER (WHERE local_saved AND luna_saved AND s.path IS NOT NULL),
            count(*) FILTER (WHERE local_saved AND luna_saved AND s.path IS NULL)
            FROM coverage c LEFT JOIN seeded s USING(path,size_bytes) WHERE NOT album_copy''').fetchone()
        print(json.dumps(dict(reconciliation_overlap=dict(zip(
            ['both_models','already_seeded','not_yet_seeded'],paired)))))


if __name__ == '__main__':
    main()
