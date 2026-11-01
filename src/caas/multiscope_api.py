"""Multi-scope API. Dev-only headers; production identity middleware required."""
import os
from fastapi import FastAPI,Depends,Header,HTTPException
from pydantic import BaseModel
from .multiscope import Memory,Principal,Denied,Conflict
app=FastAPI(title="CaaS multi-scope",version="0.3")
memory=Memory(os.getenv("CAAS_SCOPED_DB","scoped.db"))
class Scope(BaseModel):
    kind:str
    scope_id:str
    classification:str="internal"
class Grant(BaseModel):
    kind:str
    scope_id:str
    subject:str
    permission:str
class Write(BaseModel):
    kind:str
    scope_id:str
    content:str
    source:str
    memory_type:str="fact"
    classification:str="internal"
    purpose:str="assistant"
class Search(BaseModel):
    query:str
    scopes:list[tuple[str,str]]
    purpose:str="assistant"
    limit:int=20
    max_chars:int=6000
class Update(BaseModel):
    content:str=""
    expected_version:int
    delete:bool=False
class Promote(BaseModel):
    target_kind:str
    target_id:str
    purpose:str="assistant"
def principal(x_verified_tenant:str|None=Header(None),x_verified_subject:str|None=Header(None),x_verified_groups:str=Header("")):
    if os.getenv("CAAS_UNSAFE_DEV_HEADERS")!="1": raise HTTPException(503,"Verified identity middleware required")
    if not x_verified_tenant or not x_verified_subject: raise HTTPException(401,"Missing identity")
    return Principal(x_verified_tenant,x_verified_subject,frozenset(filter(None,x_verified_groups.split(","))))
def run(fn):
    try: return fn()
    except Denied: raise HTTPException(403,"Forbidden")
    except KeyError: raise HTTPException(404,"Not found")
    except Conflict as e: raise HTTPException(409,str(e))
    except ValueError as e: raise HTTPException(422,str(e))
@app.get("/healthz")
def health(): return {"status":"ok"}
@app.post("/v1/scopes")
def scope(req:Scope,p:Principal=Depends(principal)):
    return run(lambda:memory.create_scope(p,req.kind,req.scope_id,req.classification)) or {"ok":True}
@app.post("/v1/grants")
def grant(req:Grant,p:Principal=Depends(principal)):
    return run(lambda:memory.grant(p,req.kind,req.scope_id,req.subject,req.permission)) or {"ok":True}
@app.delete("/v1/grants")
def revoke(req:Grant,p:Principal=Depends(principal)):
    return run(lambda:memory.revoke(p,req.kind,req.scope_id,req.subject,req.permission)) or {"ok":True}
@app.post("/v1/memories")
def write(req:Write,p:Principal=Depends(principal)):
    return run(lambda:memory.write(p,**req.model_dump()))
@app.get("/v1/memories/{mid}")
def get(mid:str,p:Principal=Depends(principal)):
    return run(lambda:memory.get(p,mid))
@app.patch("/v1/memories/{mid}")
def update(mid:str,req:Update,p:Principal=Depends(principal)):
    return run(lambda:memory.revise(p,mid,**req.model_dump())) or {"deleted":True}
@app.post("/v1/memories/{mid}/promote")
def promote(mid:str,req:Promote,p:Principal=Depends(principal)):
    return run(lambda:memory.promote(p,mid,**req.model_dump()))
@app.post("/v1/context:retrieve")
def search(req:Search,p:Principal=Depends(principal)):
    return run(lambda:memory.search(p,**req.model_dump()))
