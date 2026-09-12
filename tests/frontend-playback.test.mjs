// Run without npm dependencies: node --experimental-vm-modules --test tests/frontend-playback.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import { promisify } from 'node:util';
import { stripTypeScriptTypes } from 'node:module';
import { fileURLToPath } from 'node:url';
import { normalizeProcessRequest, pipelineArguments } from '../app/api/process/request.ts';

const root = fileURLToPath(new URL('../', import.meta.url));
const playback = {
  provider: 'youtube', youtube_url: 'https://www.youtube.com/watch?v=jfKfPfyJRdk',
  video_id: 'jfKfPfyJRdk', title: 'Exact title & punctuation — from metadata',
  embed_url: 'https://www.youtube.com/embed/jfKfPfyJRdk',
  recording_url: 'https://www.youtube.com/watch?v=jfKfPfyJRdk',
};
const artifacts = {
  'payload.json': { playback, source_media: { resolved_ref: '/local/meeting.mp4', playback } },
  'layout.json': { children: [{ props: { content: `<iframe src="${playback.embed_url}" title="Exact title"></iframe>` } }] },
  'validation.json': { ok: true, chapter_count: 3, agenda_count: 2 },
  'manifest.json': { outputs: { html: 'meeting.html' } },
  'meeting.html': `<iframe src="${playback.embed_url}" title="Exact title"></iframe>`,
};

async function loadRoute(t, { worker = '', missing = '', commandError = null, upstream } = {}) {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'postmeet-frontend-'));
  t.after(() => fs.rmSync(cwd, { recursive: true, force: true }));
  const calls = [];
  const context = vm.createContext({
    Request, Response, process: { cwd: () => cwd, env: { POSTMEET_WORKER_URL: worker } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return new Response(JSON.stringify(upstream || { ok: true, payload: artifacts['payload.json'], html: artifacts['meeting.html'] }));
    },
  });
  const modules = {
    'next/server': { NextResponse: { json: (data, init) => new Response(JSON.stringify(data), init) } },
    fs: { default: fs }, path: { default: path }, util: { promisify },
    './request': { normalizeProcessRequest, pipelineArguments },
    '../../publication': { finalizePublication: async (result, request) => {
      calls.push({ publication: true, request });
      return result;
    } },
    child_process: {
      execFile: (command, args, options, callback) => {
        calls.push({ command, args, options });
        if (commandError) return callback(commandError);
        const out = args[args.indexOf('--output-dir') + 1];
        for (const [name, data] of Object.entries(artifacts)) {
          if (name !== missing) fs.writeFileSync(path.join(out, name), typeof data === 'string' ? data : JSON.stringify(data));
        }
        callback(null, '', '');
      },
    },
  };
  const code = stripTypeScriptTypes(fs.readFileSync(path.join(root, 'app/api/process/route.ts'), 'utf8'));
  const route = new vm.SourceTextModule(code, { context });
  await route.link((specifier) => {
    const exports = modules[specifier];
    assert.ok(exports, `Unexpected dependency: ${specifier}`);
    return new vm.SyntheticModule(Object.keys(exports), function () {
      for (const [name, value] of Object.entries(exports)) this.setExport(name, value);
    }, { context });
  });
  await route.evaluate();
  return {
    calls,
    post: (body) => route.namespace.POST(new Request('http://localhost/api/process', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
    })),
  };
}

test('local processing source is separate from canonical YouTube association', () => {
  const input = normalizeProcessRequest({ filePath: ' upload/tmp/meeting.mp4 ', source: 'ignored', youtube_url: playback.youtube_url });
  assert.equal(input.source, 'upload/tmp/meeting.mp4');
  assert.equal(input.youtubeUrl, playback.youtube_url);
  assert.deepEqual(pipelineArguments(input, '/out'), [
    '-m', 'postmeet.cli', 'run', 'upload/tmp/meeting.mp4', '--output-dir', '/out', '--youtube-url', playback.youtube_url,
  ]);
});

test('direct sources and generic media URLs are not classified as YouTube by TypeScript', () => {
  for (const source of ['https://example.org/recording.mp4', playback.youtube_url]) {
    const input = normalizeProcessRequest({ source });
    assert.equal(input.source, source);
    assert.equal(input.youtubeUrl, '');
    assert.ok(!pipelineArguments(input, '/out').includes('--youtube-url'));
  }
  const input = normalizeProcessRequest({ file_path: 'local.wav', media_url: 'https://example.org/recording.mp4', siteUrl: 'https://example.org' });
  assert.equal(input.source, 'local.wav');
  assert.equal(input.youtubeUrl, '');
  assert.ok(pipelineArguments(input, '/out').includes('--media-url'));
  assert.ok(pipelineArguments(input, '/out').includes('--site-url'));
});

test('request aliases are trimmed and non-string source values never become fake paths', () => {
  assert.equal(normalizeProcessRequest({ source: {}, youtubeUrl: ' ', youtube_url: playback.youtube_url }).source, playback.youtube_url);
  assert.equal(normalizeProcessRequest({ filePath: 42, source: false }).source, '');
});

test('local API exports all canonical pipeline artifacts unchanged', async (t) => {
  const route = await loadRoute(t);
  const response = await route.post({ filePath: '/local/meeting.mp4', youtube_url: playback.youtube_url });
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(route.calls[0].command, 'python3');
  assert.equal(route.calls[0].args[3], '/local/meeting.mp4');
  assert.ok(route.calls[0].args.includes('--youtube-url'));
  assert.deepEqual(result.payload.playback, playback);
  assert.deepEqual(result.layout, artifacts['layout.json']);
  assert.equal(result.html, artifacts['meeting.html']);
  assert.deepEqual(result.manifest, artifacts['manifest.json']);
  assert.deepEqual(result.counts, { items: 0, chapters: 3, agenda: 2 });
  assert.ok(!result.html.includes('<video'));
});

test('metadata failures and incomplete artifacts fail closed instead of exporting fallback players', async (t) => {
  for (const options of [{ commandError: new Error('YouTube metadata unavailable') }, { missing: 'meeting.html' }, { missing: 'payload.json' }]) {
    const route = await loadRoute(t, options);
    const response = await route.post({ source: 'local.wav', youtubeUrl: playback.youtube_url });
    assert.equal(response.status, 500);
    const result = await response.json();
    assert.ok(result.error);
    assert.equal(result.html, undefined);
    assert.equal(result.layout, undefined);
  }
});

test('worker forwarding preserves backend playback and keeps local source precedence', async (t) => {
  const route = await loadRoute(t, { worker: 'https://worker.example/' });
  const response = await route.post({ filePath: 'local.wav', source: playback.youtube_url, youtube_url: playback.youtube_url, mode: 'bundle' });
  const body = JSON.parse(route.calls[0].options.body);
  assert.equal(route.calls[0].url, 'https://worker.example/process');
  assert.equal(body.source, 'local.wav');
  assert.equal(body.youtubeUrl, playback.youtube_url);
  assert.equal(body.youtube_url, playback.youtube_url);
  assert.equal(body.mode, 'bundle'); // Worker-specific modes remain pass-through.
  assert.deepEqual((await response.json()).payload.playback, playback);
});

test('invalid API bodies do not start a worker or Python process', async (t) => {
  const route = await loadRoute(t);
  for (const body of [null, [], {}, { source: { bad: true } }]) {
    assert.equal((await route.post(body)).status, 400);
  }
  assert.equal(route.calls.length, 0);
});

test('UI exports backend artifacts without constructing a second player or reclassifying direct URLs', () => {
  const page = fs.readFileSync(path.join(root, 'app/page.tsx'), 'utf8');
  assert.ok(page.includes('const effectiveYoutubeUrl = youtubeUrl.trim()'));
  assert.ok(page.includes('if (mode === "upload" && file)'));
  assert.ok(page.includes('result.payload?.playback?.provider === "youtube"'));
  assert.ok(page.includes('result.payload.playback.title'));
  for (const target of ['downloadJson(result.layout', 'downloadJson(result.payload', 'downloadHtml(result.html)', 'JSON.stringify(result.layout', '...result.payload']) assert.ok(page.includes(target));
  assert.ok(!/<video\b|<iframe\b|extractYoutube|youtube\.com\/embed\//i.test(page));
  const config = fs.readFileSync(path.join(root, 'app/api/config/route.ts'), 'utf8');
  assert.ok(!config.includes('hf.space'), 'Unconfigured local deployments must not silently use a different remote backend');
});
