import sys, json, subprocess, time, urllib.request, threading
sys.path.insert(0, "src")
from safety_protocol.guard_service import GuardService

# Build an in-process guard with a token, exercise auth on /guard.
cfg = {
    "agent_id": "g", "user_id": "alice", "guard_token": "s3cret",
    "budget_limit": 50.0, "approval_threshold_cost": 10.0,
    "allowed_action_types": ["api_call"],
    "scope_rules": [{"action_type": "api_call", "allowed_targets": ["alpha/search"],
                     "match": "exact", "methods": ["POST"], "max_cost": 5.0,
                     "param_schema": {"required": ["q"], "properties": {"q": {"type": "string"}}, "additional_properties": False}}],
}
svc = GuardService(cfg)

def call(path, body, token=None, method="POST"):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request("http://127.0.0.1:8099" + path, data=data, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code

# Expose the same service over a threaded HTTP server on 8099
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import safety_protocol.guard_service as gs
class H(BaseHTTPRequestHandler):
    service = svc
    def log_message(self, *a): pass
    def _send(self, c, p):
        b = json.dumps(p).encode(); self.send_response(c)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length", 0)); return json.loads(self.rfile.read(n).decode()) if n else {}
    def do_GET(self):
        if self.service.auth.enabled and self.path == "/audit" and not self.service.auth.check(dict(self.headers)):
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/health": return self._send(200, self.service.health())
        if self.path == "/audit": return self._send(200, {"events": self.service.audit()})
        return self._send(404, {"error": "x"})
    def do_POST(self):
        b = self._body()
        if self.service.auth.enabled and self.path in gs._PROTECTED_ROUTES and not self.service.auth.check(dict(self.headers)):
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/guard": return self._send(200, self.service.guard(b.get("action_type",""), b.get("target",""), method=b.get("method"), params=b.get("params"), cost=float(b.get("cost",0.0))))
        return self._send(404, {"error": "x"})

httpd = ThreadingHTTPServer(("127.0.0.1", 8099), H)
t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
time.sleep(0.3)

ok = True
def chk(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name); ok = ok and cond

chk("POST /guard WITHOUT token -> 401", call("/guard", {"action_type":"api_call","target":"alpha/search","method":"POST","params":{"q":"x"}}) == 401)
chk("POST /guard WITH token -> 200", call("/guard", {"action_type":"api_call","target":"alpha/search","method":"POST","params":{"q":"x"}}, "s3cret") == 200)
chk("GET /audit WITHOUT token -> 401", call("/audit", None, method="GET") == 401)
httpd.shutdown()
print("RESULT:", "ALL PASS" if ok else "FAILURES")
sys.exit(0 if ok else 1)
