"""Caption coverage with the existing Takeout filename/size copy assumption.

Keep year-folder files and standalone album files. Map an album copy to the
lexically first matching year-folder path. This preserves the existing exclusion
count without merging separate year-folder files. A caption on any mapped copy
covers its group; it does not imply that every copy was sent to a model.
"""
import glob
from pathlib import Path


def completion_counts(con, index: str, luna_dir: str) -> list[tuple]:
    """Return kind, model, scope, total and complete from current media versions."""
    local = str(Path(index) / 'summaries/*/*.parquet')
    luna = str(Path(luna_dir) / '*.parquet')
    empty = 'SELECT NULL::VARCHAR AS path, NULL::BIGINT AS size_bytes WHERE false'
    local_sql = ("SELECT DISTINCT path,size_bytes FROM read_parquet(?,union_by_name=true) "
                 "WHERE source='gphotos' AND status='ok'") if glob.glob(local) else empty
    luna_sql = ("SELECT DISTINCT source_path AS path,size_bytes FROM read_parquet(?,union_by_name=true) "
                "WHERE state='ok'") if glob.glob(luna) else empty
    params = ([local] if glob.glob(local) else []) + ([luna] if glob.glob(luna) else [])
    return con.execute("""
        WITH inventory AS (
            SELECT DISTINCT path,size_bytes,name,
                CASE WHEN lower(ext) IN ('mp4','mov','3gp','avi','mpg','m4v')
                     THEN 'video' ELSE 'photo' END AS kind,
                regexp_matches(path, '/Photos from [0-9]{4}/') AS annual
            FROM gphotos_files WHERE kind='media'
        ), annual AS (
            SELECT name,size_bytes,min(path) AS representative
            FROM inventory WHERE annual GROUP BY name,size_bytes
        ), local_saved AS (""" + local_sql + """), luna_saved AS (""" + luna_sql + """),
        mapped AS (
            SELECT i.*,
                CASE WHEN i.annual THEN i.path ELSE coalesce(a.representative,i.path) END AS canonical,
                l.path IS NOT NULL AS local_ok, c.path IS NOT NULL AS luna_ok
            FROM inventory i LEFT JOIN annual a USING(name,size_bytes)
            LEFT JOIN local_saved l ON l.path=i.path AND l.size_bytes=i.size_bytes
            LEFT JOIN luna_saved c ON c.path=i.path AND c.size_bytes=i.size_bytes
        ), groups AS (
            SELECT canonical,size_bytes,kind,count(*) AS copies,
                bool_or(local_ok) AS local_ok, bool_or(luna_ok) AS luna_ok
            FROM mapped GROUP BY canonical,size_bytes,kind
        ), coverage AS (
            SELECT g.*, m.model,
                CASE m.model WHEN 'local' THEN local_ok WHEN 'luna' THEN luna_ok
                     ELSE local_ok OR luna_ok END AS complete
            FROM groups g CROSS JOIN (VALUES ('local'),('luna'),('either')) m(model)
        ) SELECT kind,model,s.scope,
            sum(CASE s.scope WHEN 'deduplicated' THEN 1 ELSE copies END)::BIGINT AS total,
            sum(CASE WHEN complete THEN CASE s.scope WHEN 'deduplicated' THEN 1 ELSE copies END
                     ELSE 0 END)::BIGINT AS complete
        FROM coverage CROSS JOIN (VALUES ('deduplicated'),('including_copies')) s(scope)
        GROUP BY kind,model,s.scope ORDER BY kind,model,s.scope
    """, params).fetchall()
