import {mkdir, copyFile, readFile} from 'node:fs/promises';
const manifest = JSON.parse(await readFile('.openai/hosting.json', 'utf8'));
if (!manifest.project_id || manifest.r2 !== 'BUCKET' || manifest.d1 !== null || manifest.static) throw new Error('Invalid Worker hosting manifest');
await mkdir('dist/server', {recursive: true});
await mkdir('dist/.openai', {recursive: true});
await copyFile('worker/index.js', 'dist/server/index.js');
await copyFile('.openai/hosting.json', 'dist/.openai/hosting.json');
console.log('Built Worker ESM artifact; no media payloads.');
