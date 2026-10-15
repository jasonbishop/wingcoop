// Dev-server routes that let the viewer browse and open the simulator's logs.
//
//   GET /api/runs          every log under the log folders: [{ root, path, size, mtime }]
//   GET /api/log?path=…    one log. A .jsonl.gz comes back as JSON Lines text, a .json as it is
//   GET /api/cards         wingsim/data/cards.json (the card reference native logs need)
//
// Folders are relative to the wingcoop repository root (the parent of viewer/):
// logs/ and docs/samples/ by default, plus anything in WINGSIM_LOGS (separated by ':').
// Works with `vite` and `vite preview`. Nothing here writes anything.

import { createReadStream, promises as fs } from 'node:fs';
import { createGunzip } from 'node:zlib';
import { join, resolve, relative, sep, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const LOG_FILE = /\.(jsonl\.gz|jsonl|json)$/;

function logRoots() {
  const roots = [
    { name: 'logs', dir: join(REPO, 'logs') },
    { name: 'docs/samples', dir: join(REPO, 'docs', 'samples') },
  ];
  for (const extra of (process.env.WINGSIM_LOGS || '').split(':').filter(Boolean)) {
    const dir = isAbsolute(extra) ? extra : resolve(process.cwd(), extra);
    // named relative to the repository (e.g. "../logs"), so addresses stay short
    roots.push({ name: relative(REPO, dir).split(sep).join('/') || '.', dir });
  }
  return roots;
}

async function walk(dir, base = dir, out = []) {
  let entries;
  try { entries = await fs.readdir(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) await walk(p, base, out);
    else if (LOG_FILE.test(e.name)) {
      const st = await fs.stat(p);
      out.push({ path: relative(base, p).split(sep).join('/'), size: st.size, mtime: st.mtimeMs });
    }
  }
  return out;
}

// "root/relative/path" -> absolute file, refusing anything outside the log folders
function locate(path) {
  for (const root of logRoots()) {
    if (path !== root.name && !path.startsWith(root.name + '/')) continue;
    const file = resolve(root.dir, path.slice(root.name.length + 1));
    if (file.startsWith(root.dir + sep) && LOG_FILE.test(file)) return file;
  }
  return null;
}

function send(res, status, body, type = 'application/json') {
  res.statusCode = status;
  res.setHeader('Content-Type', `${type}; charset=utf-8`);
  res.setHeader('Cache-Control', 'no-store');
  res.end(typeof body === 'string' ? body : JSON.stringify(body));
}

async function handle(req, res, next) {
  const url = new URL(req.url, 'http://localhost');
  if (!url.pathname.startsWith('/api/')) return next();
  try {
    if (url.pathname === '/api/runs') {
      const files = [];
      for (const root of logRoots()) {
        for (const f of await walk(root.dir)) {
          // an exported .json next to its native log is the same game; list the native one
          if (f.path.endsWith('.json') && (await exists(join(root.dir, f.path.replace(/\.json$/, '.jsonl.gz'))))) continue;
          files.push({ root: root.name, ...f, path: `${root.name}/${f.path}` });
        }
      }
      return send(res, 200, { files });
    }
    if (url.pathname === '/api/cards') {
      return send(res, 200, await fs.readFile(join(REPO, 'wingsim', 'data', 'cards.json'), 'utf8'));
    }
    if (url.pathname === '/api/log') {
      const file = locate(url.searchParams.get('path') || '');
      if (!file || !(await exists(file))) return send(res, 404, { error: 'No such log.' });
      res.statusCode = 200;
      res.setHeader('Cache-Control', 'no-store');
      if (file.endsWith('.json')) {
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        return createReadStream(file).pipe(res);
      }
      res.setHeader('Content-Type', 'application/x-ndjson; charset=utf-8');
      const stream = createReadStream(file);
      return (file.endsWith('.gz') ? stream.pipe(createGunzip()) : stream).pipe(res);
    }
    return send(res, 404, { error: 'Unknown route.' });
  } catch (err) {
    return send(res, 500, { error: String(err?.message || err) });
  }
}

const exists = p => fs.access(p).then(() => true, () => false);

export default function logApi() {
  return {
    name: 'wingcoop-log-api',
    configureServer(server) { server.middlewares.use(handle); },
    configurePreviewServer(server) { server.middlewares.use(handle); },
  };
}
