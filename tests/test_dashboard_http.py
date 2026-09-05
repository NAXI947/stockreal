import asyncio
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from stockreal.audit_store import AuditStore
from stockreal.dashboard import handler_factory

class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name);self.store=await AuditStore(self.root/'db').start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_factory(self.root,asyncio.get_running_loop(),self.store))
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
    async def asyncTearDown(self):
        await asyncio.to_thread(self.server.shutdown);self.server.server_close();self.thread.join();await self.store.close();self.tmp.cleanup()
    async def request(self,body,headers=None,path='/api/holdings',method='PUT'):
        defaults={'Host':'127.0.0.1:18080','Origin':'http://127.0.0.1:18080','Content-Type':'application/json','X-StockReal-Config':'1'}
        defaults.update(headers or {})
        def run():
            req=Request('http://127.0.0.1:'+str(self.server.server_port)+path,data=json.dumps(body).encode(),headers=defaults,method=method)
            try:
                with urlopen(req,timeout=5) as response:return response.status,response.read()
            except HTTPError as error:return error.code,error.read()
        return await asyncio.to_thread(run)
    async def test_save_and_conflict(self):
        body={'expected_revision':0,'holdings':[{'symbol':'000001.SZ','reference_cost':None,'observation_level':'测试'}]}
        self.assertEqual((await self.request(body))[0],200)
        self.assertEqual((await self.request(body))[0],409)
        self.assertEqual((await self.store.holdings())['revision'],1)
        self.assertEqual((await self.store.budget_status('2026-09-05'))['used'],0)
    async def test_cross_site_and_header_rejected(self):
        for headers in [{'Origin':'http://evil.example'},{'Host':'evil.example'},{'X-StockReal-Config':''}]:
            self.assertEqual((await self.request({'holdings':[],'expected_revision':0},headers))[0],403)
        self.assertEqual((await self.store.holdings())['revision'],0)
    async def test_malformed_size_and_private_routes(self):
        self.assertEqual((await self.request({'token':'x'}))[0],400)
        self.assertEqual((await self.request({'x':'a'*17000}))[0],413)
        self.assertEqual((await self.request({}, {'Content-Type':'text/plain'}))[0],415)
        self.assertEqual((await self.request({},path='/.secrets/runtime-profiles.json',method='GET'))[0],404)
        self.assertEqual((await self.request({},method='POST'))[0],405)
