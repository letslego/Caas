"""Multi-scope CaaS: transactional memory, ACLs, versioning and promotion."""
import sqlite3, uuid
from dataclasses import dataclass
from datetime import datetime,timezone
SCOPES={"personal","team","project","organization","agent","task"}
LEVELS={"public":0,"internal":1,"confidential":2,"restricted":3}
def utc(): return datetime.now(timezone.utc).isoformat()
@dataclass(frozen=True)
class Principal:
    tenant:str
    subject:str
    groups:frozenset[str]=frozenset()
    clearance:str="internal"
    purposes:frozenset[str]=frozenset({"assistant"})
class Denied(PermissionError): pass
class Conflict(ValueError): pass
class Memory:
    def __init__(self,path=":memory:"):
        self.db=sqlite3.connect(path,isolation_level=None,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS scopes(tenant TEXT,kind TEXT,id TEXT,owner TEXT,classification TEXT,PRIMARY KEY(tenant,kind,id));
        CREATE TABLE IF NOT EXISTS grants(tenant TEXT,kind TEXT,scope_id TEXT,subject TEXT,permission TEXT,PRIMARY KEY(tenant,kind,scope_id,subject,permission));
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,tenant TEXT,kind TEXT,scope_id TEXT,content TEXT,source TEXT,memory_type TEXT,classification TEXT,purpose TEXT,version INTEGER,status TEXT,created_by TEXT,created_at TEXT,origin_id TEXT);
        CREATE INDEX IF NOT EXISTS idx_scope ON memories(tenant,kind,scope_id,status);
        CREATE TABLE IF NOT EXISTS revisions(id TEXT,version INTEGER,content TEXT,status TEXT,actor TEXT,at TEXT,PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS audit(at TEXT,tenant TEXT,actor TEXT,action TEXT,resource TEXT);
        """)
    def log(self,p,action,resource):
        self.db.execute("INSERT INTO audit VALUES (?,?,?,?,?)",(utc(),p.tenant,p.subject,action,resource))
    def scope(self,p,kind,sid):
        return self.db.execute("SELECT * FROM scopes WHERE tenant=? AND kind=? AND id=?",(p.tenant,kind,sid)).fetchone()
    def allowed(self,p,kind,sid,permission):
        s=self.scope(p,kind,sid)
        if not s or LEVELS.get(p.clearance,-1)<LEVELS[s["classification"]]: return False
        if kind=="personal": return sid==p.subject
        if s["owner"]==p.subject: return True
        subjects=["user:"+p.subject]+["group:"+g for g in p.groups]
        marks=",".join("?" for _ in subjects)
        return self.db.execute(f"SELECT 1 FROM grants WHERE tenant=? AND kind=? AND scope_id=? AND permission IN (?,'admin') AND subject IN ({marks}) LIMIT 1",(p.tenant,kind,sid,permission,*subjects)).fetchone() is not None
    def create_scope(self,p,kind,sid,classification="internal"):
        if kind not in SCOPES or classification not in LEVELS or not sid: raise ValueError("Invalid scope")
        if kind=="personal" and sid!=p.subject: raise Denied("Personal scope owner mismatch")
        with self.db:
            self.db.execute("INSERT INTO scopes VALUES (?,?,?,?,?)",(p.tenant,kind,sid,p.subject,classification))
            self.log(p,"scope.create",kind+"/"+sid)
    def grant(self,p,kind,sid,subject,permission):
        if kind=="personal" or permission not in {"read","write","admin"} or not subject.startswith(("user:","group:")): raise ValueError("Invalid grant")
        if not self.allowed(p,kind,sid,"admin"): raise Denied("Grant denied")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO grants VALUES (?,?,?,?,?)",(p.tenant,kind,sid,subject,permission))
            self.log(p,"grant",kind+"/"+sid+"/"+subject)
    def revoke(self,p,kind,sid,subject,permission):
        if not self.allowed(p,kind,sid,"admin"): raise Denied("Revoke denied")
        with self.db:
            self.db.execute("DELETE FROM grants WHERE tenant=? AND kind=? AND scope_id=? AND subject=? AND permission=?",(p.tenant,kind,sid,subject,permission))
            self.log(p,"revoke",kind+"/"+sid+"/"+subject)
    def write(self,p,kind,sid,content,source,memory_type="fact",classification="internal",purpose="assistant",origin_id=None):
        if not self.allowed(p,kind,sid,"write"): raise Denied("Write denied")
        if purpose not in p.purposes or classification not in LEVELS: raise Denied("Purpose/classification denied")
        if LEVELS[classification]>LEVELS.get(p.clearance,-1) or LEVELS[classification]<LEVELS[self.scope(p,kind,sid)["classification"]]: raise Denied("Classification denied")
        if not content.strip() or not source.strip(): raise ValueError("Content/source required")
        mid=uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(mid,p.tenant,kind,sid,content,source,memory_type,classification,purpose,1,"active",p.subject,utc(),origin_id))
            self.db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)",(mid,1,content,"active",p.subject,utc()))
            self.log(p,"write",mid)
        return self.get(p,mid,purpose)
    def get(self,p,mid,purpose="assistant"):
        r=self.db.execute("SELECT * FROM memories WHERE tenant=? AND id=? AND status='active'",(p.tenant,mid)).fetchone()
        if r is None: raise KeyError(mid)
        if purpose not in p.purposes or r["purpose"]!=purpose or LEVELS.get(p.clearance,-1)<LEVELS[r["classification"]] or not self.allowed(p,r["kind"],r["scope_id"],"read"): raise Denied("Read denied")
        return dict(r)
    def search(self,p,query,scopes,purpose="assistant",limit=20,max_chars=6000):
        if purpose not in p.purposes or not 1<=limit<=100 or not 1<=max_chars<=100000: raise Denied("Invalid query")
        words=[w.casefold() for w in query.split() if w]
        if not words: return {"context":"","items":[],"manifest":[]}
        rows=[]
        for kind,sid in set(tuple(s) for s in scopes):
            if not self.allowed(p,kind,sid,"read"): continue
            rows+=self.db.execute("SELECT * FROM memories WHERE tenant=? AND kind=? AND scope_id=? AND purpose=? AND status='active'",(p.tenant,kind,sid,purpose)).fetchall()
        rows=[r for r in rows if LEVELS.get(p.clearance,-1)>=LEVELS[r["classification"]] and any(w in r["content"].casefold() for w in words)]
        rows.sort(key=lambda r:(sum(r["content"].casefold().count(w) for w in words),r["created_at"]),reverse=True)
        items=[];budget=max_chars
        for r in rows:
            if len(items)>=limit: break
            if len(r["content"])<=budget: items.append(dict(r));budget-=len(r["content"])
        return {"context":"\n\n".join(r["content"] for r in items),"items":items,"manifest":[{"id":r["id"],"source":r["source"],"version":r["version"],"scope":r["kind"]+"/"+r["scope_id"]} for r in items]}
    def revise(self,p,mid,content,expected_version,delete=False):
        r=self.get(p,mid)
        if not self.allowed(p,r["kind"],r["scope_id"],"write"): raise Denied("Update denied")
        if not delete and not content.strip(): raise ValueError("Empty content")
        with self.db:
            c=self.db.execute("UPDATE memories SET content=?,version=version+1,status=? WHERE id=? AND version=? AND status='active'",("" if delete else content,"deleted" if delete else "active",mid,expected_version))
            if c.rowcount!=1: raise Conflict("Version conflict")
            self.db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)",(mid,expected_version+1,"" if delete else content,"deleted" if delete else "active",p.subject,utc()))
            self.log(p,"delete" if delete else "revise",mid)
        return None if delete else self.get(p,mid)
    def promote(self,p,mid,target_kind,target_id,purpose="assistant"):
        source=self.get(p,mid,purpose)
        if not self.allowed(p,target_kind,target_id,"write"): raise Denied("Promotion denied")
        return self.write(p,target_kind,target_id,source["content"],"promotion:"+mid,source["memory_type"],source["classification"],purpose,mid)
