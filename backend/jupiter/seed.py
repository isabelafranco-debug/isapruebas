import json
from .db import engine, one, query
from .geometry import seed_pilot
from .model import CATALOG_VERSION, CROPS, FAO

def seed_catalog(conn):
    for code, crop in CROPS.items():
        query(conn, """INSERT INTO crop_catalog(version,code,name,family,parameters)
           VALUES(:v,:c,:n,:f,CAST(:p AS jsonb)) ON CONFLICT DO NOTHING""",
           v=CATALOG_VERSION,c=code,n=crop["name"],f=crop["family"],
           p=json.dumps({**crop,"source":FAO,"status":"illustrative"}))
        lo, peak, end = crop["kc"]
        for stage,(duration,kc) in enumerate(zip(crop["days"],[lo,peak,peak,end]),start=1):
            query(conn, """INSERT INTO crop_stages(version,crop_code,stage,days,kc)
                VALUES(:v,:c,:s,:d,:k) ON CONFLICT DO NOTHING""",
                v=CATALOG_VERSION,c=code,s=stage,d=duration,k=kc)
    from itertools import permutations
    for seq in permutations(CROPS,3):
        query(conn, """INSERT INTO rotations(version,code,crops)
            VALUES(:v,:c,CAST(:p AS jsonb)) ON CONFLICT DO NOTHING""",
            v=CATALOG_VERSION,c="-".join(seq),p=json.dumps(seq))

def main():
    with engine.begin() as conn:
        seed_catalog(conn)
        users = query(conn, "SELECT id FROM users ORDER BY id FOR UPDATE").scalars()
        for owner in users:
            if not one(conn, "SELECT id FROM fields WHERE owner=:o AND pilot",o=owner):
                seed_pilot(conn,owner)

if __name__ == "__main__":
    main()
