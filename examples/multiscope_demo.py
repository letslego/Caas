from caas.multiscope import Memory,Principal

db=Memory()
alice=Principal("acme","alice",frozenset({"platform"}))
bob=Principal("acme","bob",frozenset({"platform"}))
db.create_scope(alice,"personal","alice")
db.create_scope(alice,"team","platform")
db.grant(alice,"team","platform","group:platform","read")
private=db.write(alice,"personal","alice","Prefers short design reviews","conversation")
shared=db.write(alice,"team","platform","Architecture review is on Thursdays","meeting")
assert db.search(bob,"reviews",[("personal","alice")])["items"]==[]
print(db.search(bob,"Thursday",[("team","platform")])["context"])
