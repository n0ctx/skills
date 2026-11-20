// Test targets for javascript.yaml. `ruleid` = must match on the next line, `ok` = must not.
const fs = require('fs');
const cp = require('child_process');
const { exec, execSync, spawnSync } = cp;
const { readFileSync } = fs;

// ---------------------------------------------------------------- fetch-without-timeout
async function fetchCases(url, opts, signal) {
  // ruleid: gr.js.fetch-without-timeout
  await fetch(url);
  // ruleid: gr.js.fetch-without-timeout
  await fetch(url, { method: 'POST', body: '{}' });
  // ok: gr.js.fetch-without-timeout
  await fetch(url, { signal: AbortSignal.timeout(5000) });
  // ok: gr.js.fetch-without-timeout
  await fetch(url, { method: 'POST', signal });
  // ok: gr.js.fetch-without-timeout
  await fetch(url, { ...opts });
  // ok: gr.js.fetch-without-timeout
  await fetch(url, { ...opts, method: 'POST' });
  // ok: gr.js.fetch-without-timeout
  await fetch(url, opts);
  // ok: gr.js.fetch-without-timeout
  await client.fetch(url);
}

// ---------------------------------------------------------------- empty-catch
function emptyCatchCases() {
  try { risky(); }
  // ruleid: gr.js.empty-catch
  catch (e) {}

  try { risky(); }
  // ruleid: gr.js.empty-catch
  catch (e) {
    // ignore
  }

  try { risky(); }
  // ruleid: gr.js.empty-catch
  catch {}

  try { risky(); }
  // ok: gr.js.empty-catch
  catch (e) { console.error(e); }

  try { risky(); }
  // ok: gr.js.empty-catch
  catch (e) { throw new Error('wrapped', { cause: e }); }

  try { risky(); } finally { cleanup(); }
}

// ---------------------------------------------------------------- unbounded-retry
async function retryCases() {
  // ruleid: gr.js.unbounded-retry
  while (true) {
    try { await work(); } catch (e) { await sleep(1000); }
  }

  // ruleid: gr.js.unbounded-retry
  for (;;) {
    if (ready) {
      try { await work(); } catch (e) { log(e); }
    }
  }

  // ok: gr.js.unbounded-retry
  while (true) {
    try { await work(); break; } catch (e) { await sleep(1000); }
  }

  // ok: gr.js.unbounded-retry
  for (;;) {
    try { return await work(); } catch (e) { if (++n > 5) throw e; }
  }

  // ok: gr.js.unbounded-retry
  while (true) {
    try { await work(); } catch (e) { if (++n > 5) process.exit(1); }
  }

  // ok: gr.js.unbounded-retry
  while (true) {
    const msg = queue.shift();
    process(msg);
  }

  // ok: gr.js.unbounded-retry
  while (attempts < 5) {
    try { await work(); } catch (e) { attempts++; }
  }
}

// ---------------------------------------------------------------- sync-io-in-async
async function syncIoCases(p) {
  // ruleid: gr.js.sync-io-in-async
  const a = fs.readFileSync(p, 'utf8');
  // ruleid: gr.js.sync-io-in-async
  fs.writeFileSync(p, a);
  // ruleid: gr.js.sync-io-in-async
  execSync('git status');
  // ruleid: gr.js.sync-io-in-async
  cp.spawnSync('ls', ['-la']);
  // ruleid: gr.js.sync-io-in-async
  const b = readFileSync(p);
  // ok: gr.js.sync-io-in-async
  const c = await fs.promises.readFile(p, 'utf8');
  // ok: gr.js.sync-io-in-async
  await fsp.writeFile(p, c);
}
const arrowAsync = async (p) => {
  // ruleid: gr.js.sync-io-in-async
  return fs.appendFileSync(p, 'x');
};
const exprAsync = async function (p) {
  // ruleid: gr.js.sync-io-in-async
  return fs.readFileSync(p);
};
const arrowNoParens = async p => {
  if (p) {
    // ruleid: gr.js.sync-io-in-async
    return fs.readFileSync(p);
  }
};
const anonAsync = async function (p) {
  // ruleid: gr.js.sync-io-in-async
  return readFileSync(p);
};
const syncArrow = (p) => {
  // ok: gr.js.sync-io-in-async
  return fs.readFileSync(p);
};
// ok: gr.js.sync-io-in-async
const syncArrowExpr = (p) => fs.readFileSync(p);
const syncFnExpr = function (p) {
  // ok: gr.js.sync-io-in-async
  return fs.readFileSync(p);
};
const handlers = {
  // ok: gr.js.sync-io-in-async
  load(p) { return fs.readFileSync(p); },
  // ruleid: gr.js.sync-io-in-async
  async save(p) { return fs.writeFileSync(p, ''); },
};
class Svc {
  async load(p) {
    // ruleid: gr.js.sync-io-in-async
    return fs.readFileSync(p);
  }
  loadSync(p) {
    // ok: gr.js.sync-io-in-async
    return fs.readFileSync(p);
  }
}
function plainSync(p) {
  // ok: gr.js.sync-io-in-async
  return fs.readFileSync(p, 'utf8');
}
// ok: gr.js.sync-io-in-async
const topLevel = fs.readFileSync('config.json', 'utf8');

// ---------------------------------------------------------------- child-process-injection
function execCases(dir, branch, re) {
  // ruleid: gr.js.child-process-injection
  exec(`ls ${dir}`);
  // ruleid: gr.js.child-process-injection
  execSync('git checkout ' + branch);
  // ruleid: gr.js.child-process-injection
  cp.exec(`rm -rf ${dir}/tmp`, cb);
  // ruleid: gr.js.child-process-injection
  execAsync(`git log ${branch}`);
  // ok: gr.js.child-process-injection
  exec('ls -la');
  // ok: gr.js.child-process-injection
  exec(`git status`);
  // ok: gr.js.child-process-injection
  execSync('git ' + 'status');
  // ok: gr.js.child-process-injection
  execSync('git ' + 'log ' + '--oneline');
  // ok: gr.js.child-process-injection
  cp.execFile('ls', [dir]);
  // ok: gr.js.child-process-injection
  const m = re.exec(`${dir}/x`);
  // ok: gr.js.child-process-injection
  exec(command);
}

// ---------------------------------------------------------------- sql-string-build
async function sqlCases(db, id, table, sql) {
  // ruleid: gr.js.sql-string-build
  await db.query(`SELECT * FROM users WHERE id = ${id}`);
  // ruleid: gr.js.sql-string-build
  await db.execute('DELETE FROM sessions WHERE user_id = ' + id);
  // ruleid: gr.js.sql-string-build
  await knex.raw(`UPDATE ${table} SET seen = 1`);
  // ruleid: gr.js.sql-string-build
  await pool.query("SELECT * FROM t WHERE a = '" + id + "' AND b = 1");
  // ok: gr.js.sql-string-build
  await db.query(sql`SELECT * FROM users WHERE id = ${id}`);
  // ok: gr.js.sql-string-build
  await db.query('SELECT * FROM users WHERE id = $1', [id]);
  // ok: gr.js.sql-string-build
  await db.query(`SELECT * FROM users WHERE id = 1`);
  // ok: gr.js.sql-string-build
  await db.query('SELECT * FROM users ' + 'WHERE active = 1');
  // ok: gr.js.sql-string-build
  await db.query('SELECT * FROM users ' + 'WHERE active = 1 ' + 'ORDER BY id');
  // ok: gr.js.sql-string-build
  await gql.query(`query { user(id: ${id}) { name } }`);
  // ok: gr.js.sql-string-build
  await db.query(query);
}

// ---------------------------------------------------------------- tls-verify-disabled
function tlsCases(isProd) {
  // ruleid: gr.js.tls-verify-disabled
  const a = new https.Agent({ rejectUnauthorized: false });
  // ruleid: gr.js.tls-verify-disabled
  agent.options.rejectUnauthorized = false;
  // ruleid: gr.js.tls-verify-disabled
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
  // ruleid: gr.js.tls-verify-disabled
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
  // ok: gr.js.tls-verify-disabled
  const b = new https.Agent({ rejectUnauthorized: true });
  // ok: gr.js.tls-verify-disabled
  const c = new https.Agent({ rejectUnauthorized: isProd });
  // ok: gr.js.tls-verify-disabled
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '1';
  // ok: gr.js.tls-verify-disabled
  delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
}

// ---------------------------------------------------------------- eval
function evalCases(code, body) {
  // ruleid: gr.js.eval
  eval(code);
  // ruleid: gr.js.eval
  eval('(' + body + ')');
  // ruleid: gr.js.eval
  new Function(body);
  // ruleid: gr.js.eval
  new Function('a', 'b', body);
  // ruleid: gr.js.eval
  eval(`return ${code}`);
  // ok: gr.js.eval
  eval('1 + 1');
  // ok: gr.js.eval
  new Function('a', 'b', 'return a + b');
  // ok: gr.js.eval
  redis.eval(script, 0);
  // ok: gr.js.eval
  const f = JSON.parse(body);
  // ok: gr.js.eval
  const evaluate = (x) => math.eval(x);
}
