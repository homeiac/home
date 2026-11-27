// Same scoped-role bootstrap pattern as immich_sync/bootstrap.mjs (#217).
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');
const db=new Client();
try {
  await db.connect();
  await db.query("SET log_statement='none'");
  await db.query('BEGIN');
  await db.query('SELECT pg_advisory_xact_lock(244,1)');
  if(!(await db.query("SELECT 1 FROM pg_roles WHERE rolname='waffles_worker'")).rowCount)
    await db.query('CREATE ROLE waffles_worker LOGIN');
  const statement=(await db.query("SELECT format('ALTER ROLE waffles_worker PASSWORD %L',$1::text) command",[process.env.ROLE_PASSWORD])).rows[0].command;
  await db.query(statement);
  await db.query('GRANT CONNECT ON DATABASE photo_enrichment TO waffles_worker');
  await db.query('CREATE SCHEMA IF NOT EXISTS waffles AUTHORIZATION waffles_worker');
  await db.query('SET LOCAL ROLE waffles_worker');
  await db.query(await fs.readFile('/code/schema.sql','utf8'));
  await db.query('COMMIT');
  console.log('Isolated Waffles queue schema ready');
} catch(e) {
  try{await db.query('ROLLBACK');}catch{}
  console.error('Waffles schema bootstrap failed:',e.code??'unknown');process.exitCode=1;
} finally {await db.end();}
