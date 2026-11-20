// TypeScript-only syntax checks for javascript.yaml.
import fs from 'node:fs';
import { execSync } from 'node:child_process';

interface Row { id: number }

async function load(url: string, init?: RequestInit): Promise<Response> {
  // ruleid: gr.js.fetch-without-timeout
  const a = await fetch(url);
  // ruleid: gr.js.fetch-without-timeout
  const b = await fetch(url, { method: 'GET' as const });
  // ok: gr.js.fetch-without-timeout
  const c = await fetch(url, { signal: AbortSignal.timeout(5_000) } satisfies RequestInit);
  return a;
}

function swallow(): void {
  try { run(); }
  // ruleid: gr.js.empty-catch
  catch (e: unknown) {}

  try { run(); }
  // ok: gr.js.empty-catch
  catch (e: unknown) { report(e as Error); }
}

async function poll(): Promise<void> {
  // ruleid: gr.js.unbounded-retry
  while (true) {
    try { await step<number>(); } catch (e: unknown) { await sleep(500); }
  }
}

async function bounded(): Promise<number> {
  for (;;) {
    // ok: gr.js.unbounded-retry
    try { return await step<number>(); } catch (e: unknown) { if (tries++ > 3) throw e; }
  }
}

class Repo {
  private async read(path: string): Promise<string> {
    // ruleid: gr.js.sync-io-in-async
    return fs.readFileSync(path, 'utf8');
  }
  private readSync(path: string): string {
    // ok: gr.js.sync-io-in-async
    return fs.readFileSync(path, 'utf8');
  }
  async find(db: Db, id: string): Promise<Row[]> {
    // ruleid: gr.js.sql-string-build
    const rows = await db.query<Row>(`SELECT id FROM t WHERE name = '${id}'`);
    // ok: gr.js.sql-string-build
    const safe = await db.query<Row>('SELECT id FROM t WHERE name = $1', [id]);
    return rows;
  }
}

function sh(dir: string): void {
  // ruleid: gr.js.child-process-injection
  execSync(`ls ${dir}` as string);
  // ok: gr.js.child-process-injection
  execSync('ls -la', { encoding: 'utf8' });
}

function dyn(src: string): unknown {
  // ruleid: gr.js.eval
  return eval(src as string);
}
