SELECT m.path,m.size_bytes,m.ext,m.mtime,m.taken_ts,
       s.summary,s.tags AS summary_tags,s.model AS summary_model,s.created_at AS summary_created_at,
       c.summary AS context_summary,c.tags AS context_tags,c.model AS context_model,c.context AS location_context,
       e.capture_ts,e.capture_source,e.latitude,e.longitude,e.gps_source,e.width,e.height,
       coalesce((SELECT jsonb_agg(jsonb_build_object('id',f.id,'person',f.person,'box',f.box,'model',f.model,'revision',f.updated_at,'label_source',f.label_source) ORDER BY f.id)
                 FROM faces f WHERE f.path=m.path AND f.size_bytes=m.size_bytes AND f.person IS NOT NULL),'[]'::jsonb) AS faces,
       coalesce((SELECT jsonb_agg(to_jsonb(g) ORDER BY g.id) FROM photo_groups g JOIN group_members gm ON gm.group_id=g.id WHERE gm.path=m.path),'[]'::jsonb) AS groups
FROM catalog.gphotos_media m
LEFT JOIN (SELECT DISTINCT ON (path,size_bytes) path,size_bytes,summary,tags,model,created_at FROM catalog.media_summaries WHERE status='ok' ORDER BY path,size_bytes,created_at DESC,enricher DESC) s ON s.path=m.path AND s.size_bytes=m.size_bytes
LEFT JOIN photo_context c ON c.path=m.path AND c.size_bytes=m.size_bytes AND c.status='done'
LEFT JOIN extracted e ON e.path=m.path AND e.size_bytes=m.size_bytes
WHERE m.kind='media'
