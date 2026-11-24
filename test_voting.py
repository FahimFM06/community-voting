import concurrent.futures
import pytest
from voting import Store, ElectionError, tally, make_code, N

@pytest.fixture
def election(tmp_path):
    s = Store()
    s.path = tmp_path / 'test.sqlite3'
    codes = [make_code() for _ in range(N)]
    admin = [make_code() for _ in range(3)]
    s.setup([f'Member {i}' for i in range(1,N+1)], ['Admin A','Admin B','Admin C'], codes, admin)
    return s, codes, admin

def cyclic(v):
    return [((v-1+j)%N)+1 for j in range(1,N)]

def test_exact_tie():
    ids = list(range(1,N+1))
    priority = ids[::-1]
    r = tally(ids, {v:cyclic(v) for v in ids}, priority)
    assert [x['id'] for x in r] == priority
    assert all(x['points']==78 and x['counts']==[1]*12 for x in r)
    assert [x['position'] for x in r] == ids

def test_points_and_validation():
    ids = list(range(1,N+1))
    r = tally(ids, {v:[i for i in ids if i!=v] for v in ids}, ids)
    assert r[0]['id']==1 and r[0]['points']==144
    assert sum(x['points'] for x in r)==N*78
    with pytest.raises(ElectionError): tally(ids, {}, ids)

def test_roles_and_immutability(election):
    s, codes, admins = election
    with pytest.raises(ElectionError): s.login('admin', codes[0])
    with pytest.raises(ElectionError): s.login('member', admins[0])
    with pytest.raises(ElectionError): s.audit(codes[0])
    with pytest.raises(ElectionError): s.audit(admins[0])
    with pytest.raises(ElectionError): s.results('member',codes[0])
    with pytest.raises(ElectionError): s.submit(codes[0],list(range(1,13)))
    with pytest.raises(ElectionError): s.submit(codes[0],[2]*12)
    with pytest.raises(ElectionError): s.submit(admins[0],cyclic(1))
    assert s.overview('member',codes[0])['count']==0
    s.submit(codes[0],cyclic(1))
    with pytest.raises(ElectionError): s.submit(codes[0],cyclic(1))
    assert s.overview('member',codes[0])['submitted']
    for v in range(2,N+1): s.submit(codes[v-1],cyclic(v))
    final = s.results('member',codes[0])
    assert len(final)==N
    assert [x['name'] for x in final]==s.overview('member',codes[0])['priority']
    for admin in admins:
        assert len(s.audit(admin))==N
        assert s.results('admin',admin)==final
    with pytest.raises(ElectionError): s.audit(codes[0])
    with pytest.raises(ElectionError): s.submit(codes[0],cyclic(1))
    with pytest.raises(ElectionError): s.setup([f'Member {i}' for i in range(N)], ['A','B','C'],codes,admins)

def test_simultaneous_duplicate(election):
    s,codes,admins = election
    def attempt(_):
        try:
            s.submit(codes[0],cyclic(1))
            return True
        except ElectionError:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt,range(8)))==1
    assert s.overview('admin',admins[0])['count']==1

def test_initialization_status(tmp_path):
    s = Store()
    s.path = tmp_path / 'fresh.sqlite3'
    assert not s.initialized()
    s.setup([f'Member {i}' for i in range(N)], ['A','B','C'], [make_code() for _ in range(N)], [make_code() for _ in range(3)])
    assert s.initialized()
