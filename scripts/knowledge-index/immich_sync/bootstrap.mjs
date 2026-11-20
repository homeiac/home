// Executed only by the GitOps bootstrap Job in namespace database.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();await db.connect();
try {
 await db.query("SET log_statement='none'");
 await db.query('BEGIN');
 await db.query('SELECT pg_advisory_xact_lock(217,8000)');
 const exists=(await db.query("SELECT 1 FROM pg_roles WHERE rolname='immich_reconciler'")).rowCount;
 if(!exists)await db.query('CREATE ROLE immich_reconciler LOGIN');
 const statement=(await db.query("SELECT format('ALTER ROLE immich_reconciler PASSWORD %L',$1::text) command",[process.env.ROLE_PASSWORD])).rows[0].command;
 await db.query(statement);
 await db.query('GRANT CONNECT ON DATABASE photo_enrichment TO immich_reconciler');
 await db.query('GRANT USAGE ON SCHEMA public,catalog TO immich_reconciler');
 await db.query('GRANT SELECT ON catalog.gphotos_media,catalog.media_summaries,public.photo_context,public.extracted,public.faces,public.photo_groups,public.group_members TO immich_reconciler');
 await db.query('CREATE SCHEMA IF NOT EXISTS immich_sync AUTHORIZATION immich_reconciler');
 await db.query('SET LOCAL ROLE immich_reconciler');
 await db.query(await fs.readFile('/code/schema.sql','utf8'));
 await db.query('COMMIT');
 console.log('Scoped reconciliation role and schema ready; source tables are read-only.');
} catch {await db.query('ROLLBACK');console.error('Bootstrap failed; details suppressed to protect credentials.');process.exitCode=1;}
finally{await db.end();}
