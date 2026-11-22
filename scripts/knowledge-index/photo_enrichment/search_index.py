"""Rebuildable local Parquet search/group index; PostgreSQL facts remain authoritative."""
import json
import sqlite3
from contextlib import closing
from .places import distance
from .store import sql_path

TABLES=('photo_search','photo_group_index')


def immich_places(snapshot):
    """Read the same immutable, exact-file metadata snapshot as the caption workers."""
    if snapshot is None or not snapshot.is_file():
        return
    with closing(sqlite3.connect(snapshot.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)) as source:
        for path,size,raw in source.execute("""SELECT path,size,json_extract(metadata,'$.place')
            FROM context WHERE json_extract(metadata,'$.place')<>'{}'"""):
            place=json.loads(raw)
            label=', '.join(dict.fromkeys(place[key] for key in ('city','state','country') if place.get(key)))
            yield dict(path=path,size_bytes=size,location=label)


def build(db,directory,immich_snapshot=None):
    for name in ('enriched_media','faces','face_scans','photo_groups','group_members','album_duplicates'):
        db.execute(f'CREATE TEMP VIEW idx_{name} AS SELECT * FROM read_parquet({sql_path(directory/(name+".parquet"))})')
    db.execute('CREATE TEMP TABLE idx_context(path VARCHAR,size_bytes BIGINT,context_location VARCHAR,place_terms VARCHAR,context_tags VARCHAR[],people VARCHAR[],summary VARCHAR)')
    db.execute('CREATE TEMP TABLE idx_places(latitude DOUBLE,longitude DOUBLE,place_label VARCHAR,place_words VARCHAR)')
    db.execute("""CREATE TEMP TABLE idx_immich_places AS SELECT unnest(?::STRUCT(
        path VARCHAR,size_bytes BIGINT,location VARCHAR)[],recursive:=true)""",
        [list(immich_places(immich_snapshot))])
    cache_file=directory/'photo_place_cache.parquet'
    if cache_file.exists():
        cells={}
        for raw, in db.execute('SELECT context FROM read_parquet(?) ORDER BY retrieved_at',[str(cache_file)]).fetchall():
            context=json.loads(raw) if isinstance(raw,str) else raw
            if context.get('query_latitude') is None or not context.get('candidates'):continue
            lat,lon=context['query_latitude'],context['query_longitude']
            nearest=min(context['candidates'],key=lambda c:distance(lat,lon,c['latitude'],c['longitude']))
            cells[lat,lon]=(lat,lon,'Near '+nearest['title'],
                ' '.join(c.get('title','')+' '+c.get('description','') for c in context['candidates']))
        if cells:db.executemany('INSERT INTO idx_places VALUES (?,?,?,?)',list(cells.values()))
    context_file=directory/'photo_context.parquet'
    if context_file.exists():
        rows=db.execute('SELECT path,size_bytes,context,tags,input,summary FROM read_parquet(?) WHERE status=\'done\'',[str(context_file)]).fetchall()
        records=[]
        for path,size,context,tags,inputs,summary in rows:
            context=json.loads(context) if isinstance(context,str) else context or {}
            inputs=json.loads(inputs) if isinstance(inputs,str) else inputs
            candidates=context.get('candidates',[])
            place=None
            if candidates and inputs.get('latitude') is not None:
                nearest=min(candidates,key=lambda c:distance(inputs['latitude'],inputs['longitude'],c['latitude'],c['longitude']))
                place='Near '+nearest['title']
            terms=' '.join(c.get('title','')+' '+c.get('description','') for c in candidates)
            records.append((path,size,place,terms,tags or [],[p['name'] for p in context.get('saved_people',[])],summary))
        if records:db.executemany('INSERT INTO idx_context VALUES (?,?,?,?,?,?,?)',records)
    # Group annotations and saved person labels are separate from inferred context.
    db.execute("""CREATE TEMP TABLE idx_photo_search AS
        WITH people AS (
            SELECT f.path,f.size_bytes,list(DISTINCT f.person ORDER BY f.person) AS names
            FROM idx_faces f JOIN idx_face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes
            AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model WHERE f.person IS NOT NULL GROUP BY f.path,f.size_bytes),
        annotations AS (
            SELECT gm.path,gm.size_bytes,string_agg(concat_ws(' ',g.event,g.location,g.venue,g.notes,array_to_string(g.tags,' ')),' ') AS words,
                string_agg(DISTINCT nullif(g.location,''),' · ') AS annotation_location,
                flatten(list(g.tags)) AS annotation_tags
            FROM idx_group_members gm JOIN idx_photo_groups g ON g.id=gm.group_id GROUP BY gm.path,gm.size_bytes)
        SELECT m.path,m.size_bytes,CAST(to_timestamp(m.capture_ts) AS DATE) AS capture_day,
            coalesce(p.names,[]::VARCHAR[]) AS people,coalesce(a.annotation_location,i.location,c.context_location,pc.place_label) AS location,
            CASE WHEN a.annotation_location IS NOT NULL THEN 'user' WHEN i.location IS NOT NULL THEN 'immich'
                WHEN coalesce(c.context_location,pc.place_label) IS NOT NULL THEN 'nearby_gps' END AS location_source,
            list_sort(list_distinct(list_concat(coalesce(m.summary_tags,[]::VARCHAR[]),coalesce(c.context_tags,[]::VARCHAR[]),
                coalesce(a.annotation_tags,[]::VARCHAR[]),coalesce(p.names,[]::VARCHAR[])))) AS tags,
            lower(concat_ws(' ',m.name,m.summary,array_to_string(m.people,' '),array_to_string(tags,' '),
                c.place_terms,pc.place_words,c.summary,a.words,location,CAST(capture_day AS VARCHAR))) AS search_text,
            sha256(coalesce(CAST(capture_day AS VARCHAR),'unknown')||':'||coalesce(location,'')) AS group_id
        FROM idx_enriched_media m LEFT JOIN people p ON p.path=m.path AND p.size_bytes=m.size_bytes
        LEFT JOIN idx_context c ON c.path=m.path AND c.size_bytes=m.size_bytes
            AND list_sort(list_distinct(c.people))=coalesce(p.names,[]::VARCHAR[])
        LEFT JOIN idx_places pc ON pc.latitude=round(m.latitude,3) AND pc.longitude=round(m.longitude,3)
        LEFT JOIN idx_immich_places i ON i.path=m.path AND i.size_bytes=m.size_bytes
        LEFT JOIN annotations a ON a.path=m.path AND a.size_bytes=m.size_bytes
        WHERE NOT EXISTS(SELECT 1 FROM idx_album_duplicates d WHERE d.path=m.path)""")
    db.execute(f'COPY idx_photo_search TO {sql_path(directory/"photo_search.parquet")} (FORMAT parquet, COMPRESSION zstd)')
    db.execute(f"""COPY (SELECT group_id,capture_day,location,location_source,count(*) AS photos,
        list_sort(list_distinct(flatten(list(people)))) AS people,
        list_sort(list_distinct(flatten(list(tags)))) AS tags
        FROM idx_photo_search GROUP BY group_id,capture_day,location,location_source)
        TO {sql_path(directory/'photo_group_index.parquet')} (FORMAT parquet, COMPRESSION zstd)""")
