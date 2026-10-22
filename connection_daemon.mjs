#!/usr/bin/env node
// One live, loopback-only Sibelius Connect session; avoids repeated handshakes.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), 'runtime');
fs.mkdirSync(root, {recursive:true, mode:0o700});
const snapshotFiles = ['before.tsv','context.tsv','after.tsv','context-before.tsv','context-after.tsv','identity.tsv'];
const statePath = path.join(root, 'connection.json');
const inbox = path.join(root, 'invoke.json');
const prior = (() => {try {return JSON.parse(fs.readFileSync(statePath,'utf8'));} catch {return {};}})();
if (prior.pid) {
  try { process.kill(prior.pid,0); throw new Error('A bridge connection daemon is already running'); }
  catch (e) { if (e.code !== 'ESRCH') throw e; }
}
let ready = false, busy = null;
let lastId = null;
try { lastId = JSON.parse(fs.readFileSync(inbox,'utf8')).id; } catch {}
const state = (status) => fs.writeFileSync(statePath, JSON.stringify({pid:process.pid,status}), {mode:0o600});
state('connecting');
const ws = new WebSocket('ws://127.0.0.1:1898');
ws.addEventListener('open', () => ws.send(JSON.stringify({message:'connect',clientName:'Codex Score Bridge',handshakeVersion:'1.0',plugins:['ScoreBridge']})));
ws.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.sessionToken) {
    ready = true; state('ready'); console.log(JSON.stringify({ready:true}));
  } else if (message.message === 'invokePluginResponse' && busy) {
    const payload = message.returnValue ?? message.return_value;
    let summary = payload;
    if (payload && typeof payload === 'object' && snapshotFiles.some(name => Array.isArray(payload[name]))) {
      const actualRoot = fs.realpathSync(path.join(root, 'jobs')) + path.sep;
      const reportedJob = payload.job || busy.job;
      if (!reportedJob) throw new Error('Native response has no job identity');
      const actualJob = fs.realpathSync(reportedJob);
      if (!actualJob.startsWith(actualRoot) || !fs.existsSync(path.join(actualJob,'manifest.json'))) throw new Error('Native response points outside a known job');
      if (busy.job && fs.realpathSync(busy.job) !== actualJob) throw new Error('Native response belongs to another job');
      const counts = {};
      for (const name of snapshotFiles) {
        const rows = payload[name];
        if (rows === undefined) continue;
        if (!Array.isArray(rows) || !rows.every(row => typeof row === 'string')) throw new Error('Invalid native snapshot response');
        const contents = Buffer.concat([Buffer.from([0xff,0xfe]), Buffer.from(rows.join('\r\n')+'\r\n', 'utf16le')]);
        fs.writeFileSync(path.join(actualJob,name),contents,{mode:0o600});
        counts[name] = rows.length;
      }
      summary = {job:reportedJob, rows:counts};
    } else if (payload && typeof payload === 'object') {
      summary = Object.fromEntries(Object.entries(payload).filter(([key,value]) => !Array.isArray(value)));
    }
    const reply = {id:busy.id, message:message.message, result:message.result, returnValue:summary};
    fs.writeFileSync(path.join(root, `reply-${busy.id}.json`), JSON.stringify(reply), {mode:0o600});
    console.log(JSON.stringify(reply));
    busy = null; state('ready');
  }
});
const poll = setInterval(() => {
  if (!ready || busy) return;
  let request;
  try { request = JSON.parse(fs.readFileSync(inbox,'utf8')); } catch {return;}
  if (request.id === lastId) return;
  if (!/^[a-f0-9]{32}$/.test(request.id) || !['Run','OpenScore','RecoverJob','ProtocolTest','ScoreStatus','GetLastResult','ShowPart'].includes(request.method) || !Array.isArray(request.args)) {
    state('invalid invocation'); return;
  }
  if (request.method === 'Run' && request.args.length !== 0) return;
  if (request.method === 'ProtocolTest' && request.args.length !== 0) return;
  if (request.method === 'ScoreStatus' && request.args.length !== 0) return;
  if (request.method === 'GetLastResult' && request.args.length !== 0) return;
  if (request.method === 'ShowPart' && (request.args.length !== 2 || !path.isAbsolute(request.args[0]) || !request.args[0].endsWith('.sib') || !/^(score|[1-9]\d*(,[1-9]\d*)*(#[0-9]+)?)$/.test(request.args[1]))) return;
  if (request.method === 'OpenScore' && (request.args.length !== 1 || !path.isAbsolute(request.args[0]) || !request.args[0].endsWith('.sib'))) return;
  if (request.method === 'RecoverJob' && (request.args.length !== 1 || !path.isAbsolute(request.args[0]) || !fs.realpathSync(request.args[0]).startsWith(fs.realpathSync(path.join(root,'jobs'))+path.sep))) return;
  lastId = request.id; busy = request; state('running');
  ws.send(JSON.stringify({message:'invokePlugin',name:'ScoreBridge',method:request.method,args:request.args}));
}, 200);
ws.addEventListener('error', () => { state('connection failed'); console.error('Could not connect to local Sibelius'); });
ws.addEventListener('close', () => { clearInterval(poll); state('disconnected'); process.exitCode = busy ? 1 : 0; });
process.on('SIGTERM', () => { clearInterval(poll); state('stopped'); ws.close(); });
