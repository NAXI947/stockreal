"""Loopback-only personal configuration and diagnostics; no collector."""
import asyncio
import json
import signal
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from stockreal.audit_store import AuditStore
from stockreal.runtime_gate import status

async def snapshot(root,store):
    now=datetime.now(ZoneInfo('Asia/Shanghai'));gate=status(root,now)
    contracts=json.loads((root/'contracts/endpoints.json').read_text())
    evidence_path=root/'docs/stage0/field-evidence.json'
    evidence=json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    # Explicit projection: no origins, query templates, credentials, raw responses,
    # reference hashes, personal configuration history or arbitrary document paths.
    probes=[{k:r.get(k) for k in ('endpoint_code','http_status','business_status','row_count','elapsed_ms','quality_flags')} for r in evidence.get('results',[])]
    budget=await store.budget_status(now.date().isoformat())
    return {'generated_at':now.isoformat(),'mode':'DIAGNOSTIC_PREVIEW','gate':gate,
        'contracts':{'total':len(contracts),'passed':sum(c.get('contract_status')=='CONTRACT_PASS' for c in contracts)},
        'holdings':await store.holdings(),'audit':await store.summary(),'budget':budget,
        'manual_evidence':{'observed_at':evidence.get('observed_at'),'attempts':evidence.get('attempts',0),'probes':probes,
             'board':{k:evidence.get('board',{}).get(k) for k in ('page_count','unique_codes','declared_count','observed_coverage_complete','atomic_snapshot_verified','breadth_available')}},
        'metrics':dict.fromkeys(['Breadth','SectorHeatScore','DivergenceBaseScore','DivergenceScore','ClosingScore']),
        'signals':[],'candidates':[],'automatic_execution':False,'production_eligible':False}

def handler_factory(root,loop,store):
    class Handler(BaseHTTPRequestHandler):
        server_version='StockReal';sys_version=''
        def log_message(self,*args):pass
        def send_content(self,code,data,content_type):
            self.send_response(code);self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers();self.wfile.write(data)
        def do_GET(self):
            host=self.headers.get('Host','')
            if host not in {'127.0.0.1:18080','localhost:18080'}:
                self.send_content(403,b'Forbidden host','text/plain');return
            path=urlsplit(self.path).path
            if path in {'/api/status','/healthz'}:
                try:
                    data=asyncio.run_coroutine_threadsafe(snapshot(root,store),loop).result(timeout=5)
                    if path=='/healthz':data={'status':'ok','mode':data['mode'],'automatic_execution':False,'production_eligible':False}
                    self.send_content(200,json.dumps(data,ensure_ascii=False).encode(),'application/json; charset=utf-8')
                except Exception:self.send_content(503,b'{"status":"unavailable"}','application/json')
                return
            assets={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if path not in assets:self.send_content(404,b'Not found','text/plain');return
            name,kind=assets[path];self.send_content(200,(root/'web'/name).read_bytes(),kind)
        def do_PUT(self):
            host=self.headers.get('Host','')
            if host not in {'127.0.0.1:18080','localhost:18080'} or self.headers.get('Origin')!='http://'+host or self.headers.get('X-StockReal-Config')!='1':
                self.send_content(403,b'{"error":"same-origin configuration request required"}','application/json');return
            if urlsplit(self.path).path!='/api/holdings':self.send_content(404,b'Not found','text/plain');return
            if self.headers.get('Content-Type')!='application/json' or self.headers.get('Transfer-Encoding'):
                self.send_content(415,b'{"error":"JSON content required"}','application/json');return
            try:
                length=int(self.headers.get('Content-Length','-1'))
                if length<0 or length>16384:self.send_content(413,b'{"error":"invalid body size"}','application/json');return
                self.connection.settimeout(5)
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError('incomplete request')
                body=json.loads(raw)
                if not isinstance(body,dict) or set(body)!={'holdings','expected_revision'}:raise ValueError('unexpected configuration fields')
                result=asyncio.run_coroutine_threadsafe(store.replace_holdings(body['holdings'],expected_revision=body['expected_revision']),loop).result(timeout=5)
                self.send_content(200,json.dumps(result).encode(),'application/json')
            except ValueError as error:
                conflict='revision conflict' in str(error)
                self.send_content(409 if conflict else 400,json.dumps({'error':'REVISION_CONFLICT' if conflict else 'INVALID_HOLDINGS'}).encode(),'application/json')
            except Exception:self.send_content(503,b'{"error":"temporarily unavailable"}','application/json')
        def do_POST(self):self.send_content(405,b'Read-only preview','text/plain')
    return Handler

async def main():
    root=Path('/workspace');store=await AuditStore(root/'data/stockreal.db').start()
    loop=asyncio.get_running_loop();server=ThreadingHTTPServer(('0.0.0.0',18080),handler_factory(root,loop,store))
    stopped=asyncio.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stopped.set)
    task=asyncio.create_task(asyncio.to_thread(server.serve_forever))
    try:await stopped.wait()
    finally:
        await asyncio.to_thread(server.shutdown);server.server_close();await task;await store.close()

if __name__=='__main__':asyncio.run(main())
