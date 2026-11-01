import pytest
from caas.multiscope import Memory,Principal,Denied,Conflict
def test_isolation_and_promotion(tmp_path):
    m=Memory(str(tmp_path/"m.db"))
    a=Principal("t","alice",frozenset({"eng"}))
    b=Principal("t","bob",frozenset({"eng"}))
    other=Principal("other","alice")
    m.create_scope(a,"personal","alice")
    m.create_scope(a,"team","eng")
    original=m.write(a,"personal","alice","Apollo decision","chat")
    assert m.search(b,"Apollo",[("personal","alice")])["items"]==[]
    assert m.search(other,"Apollo",[("personal","alice")])["items"]==[]
    m.grant(a,"team","eng","group:eng","read")
    promoted=m.promote(a,original["id"],"team","eng")
    assert promoted["id"]!=original["id"]
    assert len(m.search(b,"Apollo",[("team","eng")])["items"])==1
    with pytest.raises(Denied): m.write(b,"team","eng","oops","chat")
    m.revoke(a,"team","eng","group:eng","read")
    assert m.search(b,"Apollo",[("team","eng")])["items"]==[]
def test_revision(tmp_path):
    m=Memory(str(tmp_path/"m.db"));a=Principal("t","a")
    m.create_scope(a,"personal","a")
    r=m.write(a,"personal","a","old","chat")
    assert m.revise(a,r["id"],"new",1)["version"]==2
    with pytest.raises(Conflict): m.revise(a,r["id"],"stale",1)
    m.revise(a,r["id"],"",2,delete=True)
    assert m.search(a,"new",[("personal","a")])["items"]==[]
