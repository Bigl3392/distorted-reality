"""M12-only negative fixture. The canonical browser run never uses this wrapper."""
import argparse,json,sys,threading
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--snapshot",required=True);p.add_argument("--mode",choices=("transient","unbuildable"),required=True);p.add_argument("--stats",required=True);a=p.parse_args()
sys.path.insert(0,a.snapshot)
from tests.fakes.launch_fake import Launch
from control import packet
from unittest import mock
stats=Path(a.stats)
with stats.open("x"):pass
patch=mock.patch.object(packet,"build_incomplete",side_effect=packet.PacketError("M12 deliberately unbuildable packet fixture")) if a.mode=="unbuildable" else None
if patch:patch.start()
ln=Launch("incomplete",200,600)
original=ln.app
count=0
def wrapped(env,start_response):
 global count
 if env.get("REQUEST_METHOD")=="GET" and env.get("PATH_INFO","").endswith("/packet"):
  count+=1
  current=count
  if a.mode=="transient" and current<=2:
   with stats.open("a") as f:f.write(json.dumps({"count":current,"status":404,"fixture":"deliberate transient packet-read fault"})+"\n")
   raw=b'{"error":"packet not available yet"}'
   start_response("404 Not Found",[("Content-Type","application/json"),("Content-Length",str(len(raw)))])
   return [raw]
  def observed(status,headers,exc_info=None):
   with stats.open("a") as f:f.write(json.dumps({"count":current,"status":int(status[:3]),"fixture":"real WSGI response"})+"\n")
   return start_response(status,headers,exc_info)
  return original(env,observed)
 return original(env,start_response)
ln.httpd.set_app(wrapped)
manifest=ln.manifest();manifest["m12_negative_fixture"]=a.mode;manifest["fixture_source"]="tests/e2e/f5_negative_launcher.py";manifest["canonical_api_unchanged"]=True
print(json.dumps(manifest),flush=True)
def watch():
 sys.stdin.read();threading.Thread(target=ln.httpd.shutdown,daemon=True).start()
threading.Thread(target=watch,daemon=True).start()
try:ln.serve_forever()
except KeyboardInterrupt:pass
finally:
 ln.stop()
 if patch:patch.stop()
