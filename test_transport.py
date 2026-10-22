"""Exercise result-file transport without Sibelius or a network connection."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


class TransportTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for transport tests')
    def test_proof_identity_rows_survive_daemon_transport(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copy2(Path(__file__).parent/'connection_daemon.mjs', root/'connection_daemon.mjs')
            runtime = root/'runtime'; job = runtime/'jobs'/'proof-test'
            job.mkdir(parents=True); (job/'manifest.json').write_text('{}')
            (root/'fake-websocket.mjs').write_text('''
globalThis.WebSocket = class {
  handlers = {};
  constructor(url) {
    if (url !== 'ws://127.0.0.1:1898') throw Error('Unexpected endpoint');
    setTimeout(() => this.handlers.open(), 0);
  }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  send(raw) {
    const request = JSON.parse(raw);
    const response = request.message === 'connect' ? {sessionToken:'fixture'} : {
      message:'invokePluginResponse', result:true,
      returnValue:{job:process.env.CSB_TEST_JOB, 'identity.tsv':['SCORE|Fixture|/tmp/fixture.sib|1|1|true']}
    };
    setTimeout(() => this.handlers.message({data:JSON.stringify(response)}), 0);
  }
  close() { this.handlers.close(); }
};
''')
            process = subprocess.Popen([shutil.which('node'), '--import', str(root/'fake-websocket.mjs'),
                                        str(root/'connection_daemon.mjs')],
                                       env=dict(os.environ, CSB_TEST_JOB=str(job)),
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            def wait_for(path):
                deadline = time.monotonic()+10
                while not path.exists():
                    if process.poll() is not None:
                        self.fail('Fixture daemon exited: '+process.communicate()[1])
                    if time.monotonic() > deadline:
                        self.fail('Fixture daemon timeout: '+str(path))
                    time.sleep(0.02)
            try:
                wait_for(runtime/'connection.json')
                deadline = time.monotonic()+10
                while json.loads((runtime/'connection.json').read_text())['status'] != 'ready':
                    if time.monotonic() > deadline: self.fail('No fixture handshake')
                    time.sleep(0.02)
                invocation = dict(id='a'*32, method='GetLastResult', args=[], job=str(job))
                (runtime/'invoke.json').write_text(json.dumps(invocation))
                reply = runtime/('reply-'+invocation['id']+'.json'); wait_for(reply)
                result = json.loads(reply.read_text())
                self.assertEqual(result['returnValue']['rows']['identity.tsv'], 1)
                self.assertEqual((job/'identity.tsv').read_text(encoding='utf-16').strip(),
                                 'SCORE|Fixture|/tmp/fixture.sib|1|1|true')
                self.assertFalse((job/'before.tsv').exists())
            finally:
                if process.poll() is None: process.terminate()
                process.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
