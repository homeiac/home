// Import verified local model files and exercise Ollama's native vision API.
import { createHash } from 'node:crypto';
import { createReadStream, createWriteStream } from 'node:fs';
import { link, mkdir, readFile, rename, rm, stat, writeFile } from 'node:fs/promises';
import { pipeline } from 'node:stream/promises';
import { execFileSync } from 'node:child_process';

const endpoint = process.env.OLLAMA_ENDPOINT ?? 'http://127.0.0.1:11434';
const model = 'bonsai-27b';
const files = {
  'Bonsai-27B-Q1_0.gguf': '17ef842e47450caeb8eaa3ebfbbab5d2f2278b62b79be107985fb69a2f819aa0',
  'Bonsai-27B-mmproj-Q8_0.gguf': 'eb561d41a7bbeb0fcf04883c8af11078ef6cae0a66862a0b68443cfca495269d',
};

async function waitForServer() {
  const deadline = Date.now() + 300_000;
  while (Date.now() < deadline) {
    try {
      await request('/api/version', undefined, 5_000);
      return;
    } catch {
      await new Promise(resolve => setTimeout(resolve, 5_000));
    }
  }
  throw new Error('Ollama did not become ready');
}

async function request(path, body, timeout = 300_000) {
  const options = { signal: AbortSignal.timeout(timeout) };
  if (body) Object.assign(options, { method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body) });
  const response = await fetch(endpoint + path, options);
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(`${path}: ${response.status} ${data.error ?? ''}`);
  return data;
}

async function importModel() {
  await mkdir('/store/blobs', {recursive: true});
  for (const [name, hash] of Object.entries(files)) {
    const destination = `/store/blobs/sha256-${hash}`;
    const temp = destination + '.bonsai-import';
    const digest = createHash('sha256');
    try {
      await pipeline(createReadStream(`/source/${name}`), async function* (chunks) {
        for await (const chunk of chunks) {
          digest.update(chunk);
          yield chunk;
        }
      }, createWriteStream(temp));
      if (digest.digest('hex') !== hash) throw new Error(`SHA-256 mismatch: ${name}`);
      await rename(temp, destination);
    } finally {
      await rm(temp, {force: true});
    }
    console.log(`Verified and staged ${name}`);
  }
  await request('/api/create', { model, stream: false,
    files: Object.fromEntries(Object.entries(files).map(([name, digest]) => [name, `sha256:${digest}`])),
    renderer: 'qwen3.5', parser: 'qwen3.5', parameters: {num_ctx: 8192} });
  const info = await request('/api/show', {model});
  console.log(JSON.stringify({event: 'imported', capabilities: info.capabilities, details: info.details}));
  if (!info.capabilities?.includes('vision')) throw new Error('Imported model has no vision capability');
}

async function promoteModel() {
  const relative = `manifests/registry.ollama.ai/library/${model}/latest`;
  const data = await readFile(`/store/${relative}`);
  const manifest = JSON.parse(data);
  const layers = [manifest.config, ...manifest.layers];
  const digests = new Set(layers.map(layer => layer.digest));
  if (Object.values(files).some(hash => !digests.has(`sha256:${hash}`))) {
    throw new Error('Tested manifest does not reference both verified Bonsai files');
  }
  await mkdir('/store/models/blobs', {recursive: true});
  for (const {digest, size} of layers) {
    if (!/^sha256:[0-9a-f]{64}$/.test(digest)) throw new Error('Invalid manifest digest');
    const name = digest.replace(':', '-');
    const source = `/store/blobs/${name}`;
    const destination = `/store/models/blobs/${name}`;
    if ((await stat(source)).size !== size) throw new Error('Canary blob size mismatch');
    await link(source, destination).catch(error => { if (error.code !== 'EEXIST') throw error; });
    if ((await stat(destination)).size !== size) throw new Error('Existing production blob size mismatch');
  }
  const destination = `/store/models/${relative}`;
  await mkdir(destination.slice(0, destination.lastIndexOf('/')), {recursive: true});
  const temp = `${destination}.bonsai-canary`;
  try {
    await writeFile(temp, data);
    await link(temp, destination).catch(error => { if (error.code !== 'EEXIST') throw error; });
    if (!(await readFile(destination)).equals(data)) throw new Error('Refusing to overwrite a different Bonsai manifest');
  } finally {
    await rm(temp, {force: true});
  }
  console.log(JSON.stringify({event: 'promoted', model, layers: layers.length}));
}

function ffmpeg(args) {
  return execFileSync('ffmpeg', ['-v', 'error', '-nostdin', ...args], { maxBuffer: 8 * 1024 * 1024 });
}

async function visionCheck(name, images, question, expected) {
  console.log(JSON.stringify({event: 'started', name, frames: images.length}));
  const response = await request('/api/chat', {model, think: false, stream: false, keep_alive: '5m',
    options: {num_ctx: 8192, num_thread: 2, num_predict: 160, temperature: 0},
    messages: [{role: 'user', content: question, images: images.map(image => image.toString('base64'))}]}, 540_000);
  const raw = response.message?.content ?? '';
  const result = JSON.parse(raw.match(/\{[\s\S]*\}/)?.[0] ?? 'null');
  console.log(JSON.stringify({event: 'completed', name, frames: images.length,
    seconds: response.total_duration / 1e9, promptTokens: response.prompt_eval_count, content: raw}));
  if (!result?.summary || !Array.isArray(result.tags) || !expected.test(result.summary)) {
    throw new Error(`Invalid or visually incorrect ${name} caption`);
  }
}

if (process.env.PROMOTE_MODEL_ONLY === 'true') {
  await promoteModel();
  process.exit(0);
}
await waitForServer();
if (process.env.IMPORT_MODEL !== 'false') await importModel();
const photo = ffmpeg(['-f', 'lavfi', '-i', 'color=c=green:s=768x512', '-frames:v', '1', '-f', 'mjpeg', '-']);
await visionCheck('photo', [photo], 'What solid color covers this photo? Answer only with JSON containing summary and tags.', /\bgreen\b/i);

// Use actual decoded frames from a two-scene video, in reverse alphabetical color order.
const vid = '/tmp/bonsai-vision-canary.mp4';
ffmpeg(['-y', '-f', 'lavfi', '-i', 'color=c=red:s=768x512:r=2:d=2', '-f', 'lavfi', '-i', 'color=c=blue:s=768x512:r=2:d=2',
  '-filter_complex', 'concat=n=2:v=1:a=0', '-c:v', 'libx264', vid]);
const frames = Array.from({length: 8}, (_, i) => ffmpeg(['-ss', String(i / 2), '-i', vid, '-frames:v', '1', '-f', 'mjpeg', '-']));
if (frames.some(frame => !frame.length)) throw new Error('Failed to decode all eight video frames');
await visionCheck('video', frames, 'These images are eight frames from a video in chronological order. In summary, state the first and last colors in order. Answer only with JSON containing summary and tags.', /\bred\b.*\bblue\b/is);
const active = await request('/api/ps');
const models = active.models.map(({name, size, size_vram}) => ({name, size, size_vram}));
if (process.env.REQUIRE_GPU === 'true' && !models.some(entry => entry.name.split(':')[0] === model && entry.size_vram > 0)) {
  throw new Error('Bonsai vision passed but the model has no GPU allocation');
}
console.log(JSON.stringify({event:'passed', models}));
