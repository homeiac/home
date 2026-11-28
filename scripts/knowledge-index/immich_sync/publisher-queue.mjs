// Catalog cycles own only catalog jobs. Recovery jobs have their own source and lifetime.
export const expireCatalog = `UPDATE immich_sync.jobs SET state='conflict',reason='source_removed'
 WHERE cycle_id<>$1 AND state<>'excluded' AND NOT (payload ? 'recovery')`;

export const restoreRecovery = `UPDATE immich_sync.jobs
 SET state=CASE WHEN applied->>'sourceRevision'=source_hash AND intent IS NULL THEN 'applied' ELSE 'pending' END,
     reason=NULL, available_at=now(), verified_at=NULL, updated_at=now()
 WHERE state='conflict' AND reason='source_removed' AND payload ? 'recovery'
   AND asset_id IS NOT NULL AND length(trim(payload->>'summary'))>0`;
