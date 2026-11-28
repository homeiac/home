// Pipe the generated fixture to psql. It uses private temporary rows and always rolls back.
import {restoreRecovery,expireCatalog} from './immich_sync/publisher-queue.mjs';
const fixture = sql => sql.replaceAll('immich_sync.jobs','pg_temp.jobs');
console.log(`BEGIN;
 CREATE TEMP TABLE jobs(id int PRIMARY KEY,cycle_id text,state text,reason text,payload jsonb,
     asset_id text,source_hash text,applied jsonb,intent jsonb,available_at timestamptz,verified_at timestamptz,updated_at timestamptz);
 INSERT INTO jobs(id,cycle_id,state,reason,payload,asset_id,source_hash,applied) VALUES
     (1,'recovery','conflict','source_removed','{"recovery":{},"summary":"a"}','a','v',NULL),
     (2,'recovery','conflict','source_removed','{"recovery":{},"summary":"b"}','b','v','{"sourceRevision":"v"}'),
     (3,'old','pending',NULL,'{}','c','v',NULL),
     (4,'current','pending',NULL,'{}','d','v',NULL),
     (5,'recovery','conflict','machine_metadata_edited','{"recovery":{},"summary":"e"}','e','v',NULL);
 ${fixture(restoreRecovery)};
 ${fixture(expireCatalog).replace('$1',"'current'")};
 ${fixture(restoreRecovery)};
 DO $$ BEGIN
   IF (SELECT array_agg(state ORDER BY id) FROM jobs) <> ARRAY['pending','applied','conflict','pending','conflict']
      OR (SELECT reason FROM jobs WHERE id=3) IS DISTINCT FROM 'source_removed'
      OR (SELECT reason FROM jobs WHERE id=5) IS DISTINCT FROM 'machine_metadata_edited'
      THEN RAISE EXCEPTION 'Publisher ownership regression'; END IF;
 END $$;
 ROLLBACK;`);
