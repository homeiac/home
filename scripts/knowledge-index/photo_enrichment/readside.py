"""Gallery queries over immutable Parquet, overlaid with recent PostgreSQL edits."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from .snapshots import analytical_connection
from .telemetry import get_telemetry


class GalleryReader:
    def __init__(self,store):
        self.store=store
        self.db,self.manifest=analytical_connection(store.state)
        try:
            # Only post-snapshot review changes come from the writable authority.
            edits=store.rows('SELECT id,person,label_source,updated_at AS revision FROM faces WHERE updated_at>=to_timestamp(?)',
                [self.manifest['captured_at']])
            self.db.execute("""CREATE TEMP TABLE live_edits AS SELECT value->>'id' AS id,value->>'person' AS person,
                value->>'label_source' AS label_source,CAST(value->>'revision' AS TIMESTAMP) AS revision
                FROM json_each(?)""",[json.dumps(edits,default=str)])
            self.db.execute("""CREATE TEMP VIEW reviewed_faces AS SELECT f.* EXCLUDE(person,label_source,updated_at),
                CASE WHEN e.id IS NOT NULL THEN e.person ELSE f.person END AS person,
                CASE WHEN e.id IS NOT NULL THEN e.label_source ELSE f.label_source END AS label_source,
                CASE WHEN e.id IS NOT NULL THEN e.revision ELSE f.updated_at END AS updated_at
                FROM faces f LEFT JOIN live_edits e USING(id)""")
            if 'album_duplicates' not in self.manifest['tables']:
                # Compatibility with pre-readside snapshots until the next export.
                duplicates=store.rows('SELECT path FROM catalog.gphotos_album_dup')
                self.db.execute("CREATE TEMP TABLE album_duplicates AS SELECT value->>'path' AS path FROM json_each(?)",[json.dumps(duplicates)])
            if 'photo_context' not in self.manifest['tables']:
                self.db.execute("CREATE TEMP TABLE photo_context(path VARCHAR,size_bytes BIGINT,status VARCHAR,summary VARCHAR,context JSON)")
        except BaseException:
            self.db.close();raise

    def close(self):self.db.close()

    def rows(self,query,params=()):
        with get_telemetry().stage('duckdb.query',**{'db.system.name':'duckdb'}):
            result=self.db.execute(query,params)
            names=[c[0] for c in result.description]
            return [dict(zip(names,row)) for row in result.fetchall()]

    def faces(self,person,status,offset,limit,matches):
        if status not in ('all','unreviewed','named','suggested') or offset<0 or not 1<=limit<=100:
            raise ValueError('Invalid face filter')
        base="""FROM reviewed_faces f JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes
            AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
            JOIN enriched_media m ON m.path=f.path AND m.size_bytes=f.size_bytes
            WHERE NOT EXISTS (SELECT 1 FROM album_duplicates d WHERE d.path=f.path)"""
        counts=self.rows('SELECT count(*) AS total,count(*) FILTER(WHERE f.person IS NULL) AS unreviewed '+base)[0]
        people=self.rows('SELECT f.person,count(*) AS faces '+base+' AND f.person IS NOT NULL GROUP BY f.person ORDER BY lower(f.person)')
        visible={row['id'] for row in self.rows('SELECT f.id '+base+' AND f.person IS NULL')}
        matches={key:value for key,value in matches.items() if key in visible}
        fields='SELECT f.id,f.path,f.box,f.confidence,f.person,f.label_source,f.updated_at AS revision,m.capture_ts,m.latitude,m.longitude,m.summary '
        filters,params='',[]
        if status=='suggested':
            selected=sorted((key for key,value in matches.items() if not person or value['person']==person),
                key=lambda key:(matches[key]['person'],-matches[key]['score'],key))
            total=len(selected);ids=selected[offset:offset+limit]
            faces=self.rows(fields+base+' AND f.id=ANY(?)',[ids]) if ids else []
            faces.sort(key=lambda face:ids.index(face['id']))
        else:
            if status=='unreviewed':filters+=' AND f.person IS NULL'
            if status=='named':filters+=' AND f.person IS NOT NULL'
            if person:filters+=' AND f.person=?';params.append(person)
            total=self.rows('SELECT count(*) n '+base+filters,params)[0]['n']
            faces=self.rows(fields+base+filters+' ORDER BY m.capture_ts DESC NULLS LAST,f.id LIMIT ? OFFSET ?',[*params,limit,offset])
        groups={}
        for face in faces:face['suggestion']=matches.get(face['id']) if face['person'] is None else None
        for match in matches.values():groups[match['person']]=groups.get(match['person'],0)+1
        counts['suggested']=len(matches)
        return dict(faces=faces,total=total,offset=offset,people=people,counts=counts,
            suggested_people=[dict(person=name,faces=count) for name,count in sorted(groups.items())],
            query_backend='duckdb',captured_at=self.manifest['captured_at'])

    def dates(self,timezone):
        ZoneInfo(timezone)
        return self.rows("""SELECT coalesce(CAST(CAST(timezone(?,to_timestamp(capture_ts)) AS DATE) AS VARCHAR),'unknown') AS date,
            count(*) AS photos,count(*) FILTER(WHERE latitude IS NOT NULL) AS with_gps FROM enriched_media m
            WHERE NOT EXISTS (SELECT 1 FROM album_duplicates d WHERE d.path=m.path) GROUP BY 1 ORDER BY 1 DESC""",[timezone])

    def photos(self,date,timezone,offset,limit):
        ZoneInfo(timezone)
        if date!='unknown':dt.date.fromisoformat(date)
        if offset<0 or not 1<=limit<=200:raise ValueError('Invalid pagination')
        condition="""coalesce(CAST(CAST(timezone(?,to_timestamp(capture_ts)) AS DATE) AS VARCHAR),'unknown')=?
            AND NOT EXISTS (SELECT 1 FROM album_duplicates d WHERE d.path=m.path)"""
        total=self.rows('SELECT count(*) n FROM enriched_media m WHERE '+condition,[timezone,date])[0]['n']
        photos=self.rows("""SELECT m.*,c.summary AS context_summary,c.context AS location_context,
            (SELECT list(DISTINCT f.person ORDER BY f.person) FROM reviewed_faces f JOIN face_scans fs
             ON fs.path=f.path AND fs.size_bytes=f.size_bytes AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
             WHERE f.path=m.path AND f.size_bytes=m.size_bytes AND f.person IS NOT NULL) AS saved_people
            FROM enriched_media m LEFT JOIN photo_context c ON c.path=m.path AND c.size_bytes=m.size_bytes AND c.status='done'
            WHERE """+condition+' ORDER BY capture_ts NULLS LAST,m.path LIMIT ? OFFSET ?',
            [timezone,date,limit,offset])
        return dict(photos=photos,total=total,offset=offset,query_backend='duckdb',captured_at=self.manifest['captured_at'])
