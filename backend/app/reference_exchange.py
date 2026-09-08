"""Arbiter v0.26 reference exchange and end-to-end settlement sandbox.

Play-money only. This reference venue exists to exercise the full lifecycle:
contract -> semantics/compiler -> market -> orders/trades -> evidence -> resolution ->
settlement -> audit. It is not a broker, DCM, custody system, or real-money venue.
"""
from __future__ import annotations
import json, sqlite3
from typing import Any
from .resolution_infra import gen_id, utcnow, canonical_hash
from . import semantic_contract, compiler

STARTING_BALANCE=10_000.0
VERSION="0.26.0"

class ReferenceExchangeService:
    def __init__(self,store):self.store=store;self._init_db()
    def _init_db(self):
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS reference_markets(
              market_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, title TEXT NOT NULL,
              rules TEXT NOT NULL, state TEXT NOT NULL, semantic_json TEXT NOT NULL,
              compilation_json TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
              outcome TEXT, resolved_at TEXT, settlement_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS reference_accounts(
              account_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, display_name TEXT NOT NULL,
              cash REAL NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reference_positions(
              position_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, market_id TEXT NOT NULL,
              account_id TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL,
              price REAL NOT NULL, cost REAL NOT NULL, payout REAL NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, settled_at TEXT, trade_id TEXT
            );
            CREATE TABLE IF NOT EXISTS reference_orders(
              order_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, market_id TEXT NOT NULL,
              account_id TEXT NOT NULL, side TEXT NOT NULL, limit_price REAL NOT NULL,
              quantity REAL NOT NULL, remaining REAL NOT NULL, reserved_cash REAL NOT NULL,
              state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reference_trades(
              trade_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, market_id TEXT NOT NULL,
              yes_order_id TEXT NOT NULL, no_order_id TEXT NOT NULL,
              yes_account_id TEXT NOT NULL, no_account_id TEXT NOT NULL,
              yes_price REAL NOT NULL, no_price REAL NOT NULL, quantity REAL NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_reference_positions_market ON reference_positions(market_id,account_id);
            CREATE INDEX IF NOT EXISTS ix_reference_orders_book ON reference_orders(market_id,side,state,limit_price,created_at);
            CREATE INDEX IF NOT EXISTS ix_reference_trades_market ON reference_trades(market_id,created_at);
            """)
            # Backward-compatible migration for v0.19 databases.
            if isinstance(db, sqlite3.Connection):
                cols={r[1] for r in db.execute("PRAGMA table_info(reference_positions)").fetchall()}
                if "trade_id" not in cols:
                    db.execute("ALTER TABLE reference_positions ADD COLUMN trade_id TEXT")
            else:
                row=db.execute("SELECT 1 AS present FROM information_schema.columns WHERE table_name=? AND column_name=?",("reference_positions","trade_id")).fetchone()
                if not row:
                    db.execute("ALTER TABLE reference_positions ADD COLUMN trade_id TEXT")
    def create_market(self,tenant_id,title,rules,actor):
        mid=gen_id("refmkt");sem=semantic_contract.analyze_contract(title,rules);comp=compiler.compile_rules(mid,title,rules,self.store.list_authorities(),metadata={"reference_exchange":True});status=str(comp.get("status") or "REVIEW");state="OPEN" if status=="READY" else "HELD";now=utcnow()
        with self.store.connect() as db:db.execute("INSERT INTO reference_markets(market_id,tenant_id,title,rules,state,semantic_json,compilation_json,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?)",(mid,tenant_id,title,rules,state,json.dumps(sem,sort_keys=True),json.dumps(comp,sort_keys=True),now,actor))
        self.store._audit(actor,"reference_market.created","reference_market",mid,{"tenant_id":tenant_id,"state":state,"compiler_status":status,"play_money":True})
        return self.get_market(mid,tenant_id)
    def create_account(self,tenant_id,display_name,actor):
        aid=gen_id("refacct");now=utcnow()
        with self.store.connect() as db:db.execute("INSERT INTO reference_accounts(account_id,tenant_id,display_name,cash,created_at) VALUES(?,?,?,?,?)",(aid,tenant_id,display_name,STARTING_BALANCE,now))
        self.store._audit(actor,"reference_account.created","reference_account",aid,{"tenant_id":tenant_id,"starting_balance":STARTING_BALANCE})
        return {"account_id":aid,"tenant_id":tenant_id,"display_name":display_name,"cash":STARTING_BALANCE,"created_at":now}
    def _validate_trade_inputs(self,side,quantity,price):
        side=side.upper()
        if side not in {"YES","NO"}:raise ValueError("side must be YES or NO")
        if quantity<=0:raise ValueError("quantity must be > 0")
        if not 0<price<1:raise ValueError("price must be between 0 and 1")
        return side
    def place_position(self,tenant_id,market_id,account_id,side,quantity,price,actor):
        """Legacy direct-fill helper retained for deterministic sandbox tests."""
        side=self._validate_trade_inputs(side,quantity,price)
        with self.store.connect() as db:
            m=db.execute("SELECT * FROM reference_markets WHERE market_id=? AND tenant_id=?",(market_id,tenant_id)).fetchone();a=db.execute("SELECT * FROM reference_accounts WHERE account_id=? AND tenant_id=?",(account_id,tenant_id)).fetchone()
            if not m:raise KeyError("unknown market")
            if m["state"]!="OPEN":raise ValueError("market is not open")
            if not a:raise KeyError("unknown account")
            cost=round(quantity*price,8)
            if float(a["cash"])<cost:raise ValueError("insufficient play-money balance")
            pid=gen_id("refpos");now=utcnow();db.execute("UPDATE reference_accounts SET cash=cash-? WHERE account_id=?",(cost,account_id));db.execute("INSERT INTO reference_positions(position_id,tenant_id,market_id,account_id,side,quantity,price,cost,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(pid,tenant_id,market_id,account_id,side,quantity,price,cost,now))
        self.store._audit(actor,"reference_position.opened","reference_position",pid,{"market_id":market_id,"account_id":account_id,"side":side,"quantity":quantity,"price":price,"cost":cost,"legacy_direct_fill":True})
        return {"position_id":pid,"market_id":market_id,"account_id":account_id,"side":side,"quantity":quantity,"price":price,"cost":cost,"play_money":True}
    def place_order(self,tenant_id,market_id,account_id,side,quantity,limit_price,actor):
        side=self._validate_trade_inputs(side,quantity,limit_price);now=utcnow();reserve=round(quantity*limit_price,8);oid=gen_id("reford")
        with self.store.connect() as db:
            m=db.execute("SELECT * FROM reference_markets WHERE market_id=? AND tenant_id=?",(market_id,tenant_id)).fetchone();a=db.execute("SELECT * FROM reference_accounts WHERE account_id=? AND tenant_id=?",(account_id,tenant_id)).fetchone()
            if not m:raise KeyError("unknown market")
            if m["state"]!="OPEN":raise ValueError("market is not open")
            if not a:raise KeyError("unknown account")
            if float(a["cash"])<reserve:raise ValueError("insufficient play-money balance")
            db.execute("UPDATE reference_accounts SET cash=cash-? WHERE account_id=?",(reserve,account_id));db.execute("INSERT INTO reference_orders(order_id,tenant_id,market_id,account_id,side,limit_price,quantity,remaining,reserved_cash,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(oid,tenant_id,market_id,account_id,side,limit_price,quantity,quantity,reserve,"OPEN",now,now))
        trades=self._match_order(tenant_id,oid,actor)
        self.store._audit(actor,"reference_order.placed","reference_order",oid,{"market_id":market_id,"account_id":account_id,"side":side,"quantity":quantity,"limit_price":limit_price,"play_money":True})
        return {"order":self.get_order(tenant_id,oid),"trades":trades,"play_money":True}
    def _match_order(self,tenant_id,order_id,actor):
        trades=[]
        while True:
            with self.store.connect() as db:
                taker=db.execute("SELECT * FROM reference_orders WHERE tenant_id=? AND order_id=?",(tenant_id,order_id)).fetchone()
                if not taker or taker["state"]!="OPEN" or float(taker["remaining"])<=1e-12:break
                opp="NO" if taker["side"]=="YES" else "YES"
                # Price-time priority. Opposite limit must make complementary prices sum to at least 1.
                maker=db.execute("SELECT * FROM reference_orders WHERE tenant_id=? AND market_id=? AND side=? AND state='OPEN' AND account_id<>? AND limit_price>=? ORDER BY limit_price DESC,created_at ASC LIMIT 1",(tenant_id,taker["market_id"],opp,taker["account_id"],1-float(taker["limit_price"]))).fetchone()
                if not maker:break
                qty=min(float(taker["remaining"]),float(maker["remaining"]))
                if maker["side"]=="YES":yes_price=float(maker["limit_price"]);no_price=round(1-yes_price,8);yes_order=maker;no_order=taker
                else:no_price=float(maker["limit_price"]);yes_price=round(1-no_price,8);no_order=maker;yes_order=taker
                # Limits are maximum buy prices; matching predicate guarantees both executions respect limits.
                if yes_price>float(yes_order["limit_price"])+1e-9 or no_price>float(no_order["limit_price"])+1e-9:break
                tid=gen_id("reftrade");now=utcnow();db.execute("INSERT INTO reference_trades(trade_id,tenant_id,market_id,yes_order_id,no_order_id,yes_account_id,no_account_id,yes_price,no_price,quantity,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(tid,tenant_id,taker["market_id"],yes_order["order_id"],no_order["order_id"],yes_order["account_id"],no_order["account_id"],yes_price,no_price,qty,now))
                for order,px,side in ((yes_order,yes_price,"YES"),(no_order,no_price,"NO")):
                    limit=float(order["limit_price"]);actual=round(qty*px,8);reserved_at_limit=round(qty*limit,8);refund=max(0.0,round(reserved_at_limit-actual,8));new_rem=round(float(order["remaining"])-qty,8);new_reserved=max(0.0,round(float(order["reserved_cash"])-reserved_at_limit,8));state="FILLED" if new_rem<=1e-12 else "OPEN"
                    if refund:db.execute("UPDATE reference_accounts SET cash=cash+? WHERE account_id=?",(refund,order["account_id"]))
                    db.execute("UPDATE reference_orders SET remaining=?,reserved_cash=?,state=?,updated_at=? WHERE order_id=?",(new_rem,new_reserved,state,now,order["order_id"]))
                    pid=gen_id("refpos");db.execute("INSERT INTO reference_positions(position_id,tenant_id,market_id,account_id,side,quantity,price,cost,created_at,trade_id) VALUES(?,?,?,?,?,?,?,?,?,?)",(pid,tenant_id,taker["market_id"],order["account_id"],side,qty,px,actual,now,tid))
            trade={"trade_id":tid,"market_id":taker["market_id"],"yes_order_id":yes_order["order_id"],"no_order_id":no_order["order_id"],"yes_price":yes_price,"no_price":no_price,"quantity":qty,"play_money":True};trades.append(trade);self.store._audit(actor,"reference_trade.executed","reference_trade",tid,trade)
        return trades
    def cancel_order(self,tenant_id,order_id,actor):
        with self.store.connect() as db:
            o=db.execute("SELECT * FROM reference_orders WHERE tenant_id=? AND order_id=?",(tenant_id,order_id)).fetchone()
            if not o:raise KeyError("unknown order")
            if o["state"]!="OPEN":raise ValueError("only OPEN orders may be cancelled")
            refund=float(o["reserved_cash"]);now=utcnow();db.execute("UPDATE reference_accounts SET cash=cash+? WHERE account_id=?",(refund,o["account_id"]));db.execute("UPDATE reference_orders SET state='CANCELLED',remaining=0,reserved_cash=0,updated_at=? WHERE order_id=?",(now,order_id))
        self.store._audit(actor,"reference_order.cancelled","reference_order",order_id,{"refund":refund,"play_money":True});return self.get_order(tenant_id,order_id)
    def get_order(self,tenant_id,order_id):
        with self.store.connect() as db:r=db.execute("SELECT * FROM reference_orders WHERE tenant_id=? AND order_id=?",(tenant_id,order_id)).fetchone()
        if not r:raise KeyError("unknown order")
        return dict(r)
    def order_book(self,tenant_id,market_id):
        with self.store.connect() as db:rows=db.execute("SELECT * FROM reference_orders WHERE tenant_id=? AND market_id=? AND state='OPEN' ORDER BY side,limit_price DESC,created_at",(tenant_id,market_id)).fetchall()
        yes=[dict(r) for r in rows if r["side"]=="YES"];no=[dict(r) for r in rows if r["side"]=="NO"]
        return {"market_id":market_id,"yes":yes,"no":no,"play_money":True}
    def resolve_market(self,tenant_id,market_id,outcome,evidence_summary,actor):
        outcome=outcome.upper()
        if outcome not in {"YES","NO"}:raise ValueError("outcome must be YES or NO")
        with self.store.connect() as db:
            m=db.execute("SELECT * FROM reference_markets WHERE market_id=? AND tenant_id=?",(market_id,tenant_id)).fetchone()
            if not m:raise KeyError("unknown market")
            if m["state"]!="OPEN":raise ValueError("only OPEN markets may resolve")
            # Cancel all resting orders and release their reserved play-money before settlement.
            open_orders=db.execute("SELECT * FROM reference_orders WHERE market_id=? AND tenant_id=? AND state='OPEN'",(market_id,tenant_id)).fetchall()
            for o in open_orders:
                if float(o["reserved_cash"]):db.execute("UPDATE reference_accounts SET cash=cash+? WHERE account_id=?",(float(o["reserved_cash"]),o["account_id"]))
                db.execute("UPDATE reference_orders SET state='CANCELLED',remaining=0,reserved_cash=0,updated_at=? WHERE order_id=?",(utcnow(),o["order_id"]))
            ps=db.execute("SELECT * FROM reference_positions WHERE market_id=? AND tenant_id=?",(market_id,tenant_id)).fetchall();now=utcnow();payouts=[]
            for p in ps:
                payout=float(p["quantity"]) if p["side"]==outcome else 0.0;db.execute("UPDATE reference_positions SET payout=?,settled_at=? WHERE position_id=?",(payout,now,p["position_id"]));
                if payout:db.execute("UPDATE reference_accounts SET cash=cash+? WHERE account_id=?",(payout,p["account_id"]))
                payouts.append({"position_id":p["position_id"],"account_id":p["account_id"],"side":p["side"],"payout":payout})
            packet={"market_id":market_id,"outcome":outcome,"evidence_summary":evidence_summary,"payouts":payouts,"cancelled_resting_orders":len(open_orders),"resolved_at":now,"play_money":True};sh=canonical_hash(packet);db.execute("UPDATE reference_markets SET state='SETTLED',outcome=?,resolved_at=?,settlement_hash=? WHERE market_id=?",(outcome,now,sh,market_id))
        self.store._audit(actor,"reference_market.settled","reference_market",market_id,{"outcome":outcome,"settlement_hash":sh,"position_count":len(payouts),"play_money":True});packet["settlement_hash"]=sh;return packet
    def get_market(self,market_id,tenant_id):
        with self.store.connect() as db:
            r=db.execute("SELECT * FROM reference_markets WHERE market_id=? AND tenant_id=?",(market_id,tenant_id)).fetchone()
            if not r:raise KeyError("unknown market")
            ps=db.execute("SELECT * FROM reference_positions WHERE market_id=? AND tenant_id=? ORDER BY created_at",(market_id,tenant_id)).fetchall();ts=db.execute("SELECT * FROM reference_trades WHERE market_id=? AND tenant_id=? ORDER BY created_at",(market_id,tenant_id)).fetchall()
        d=dict(r);d["semantic"]=json.loads(d.pop("semantic_json"));d["compilation"]=json.loads(d.pop("compilation_json"));d["positions"]=[dict(p) for p in ps];d["trades"]=[dict(t) for t in ts];d["order_book"]=self.order_book(tenant_id,market_id);d["play_money"]=True;return d
    def account(self,account_id,tenant_id):
        with self.store.connect() as db:
            a=db.execute("SELECT * FROM reference_accounts WHERE account_id=? AND tenant_id=?",(account_id,tenant_id)).fetchone()
            if not a:raise KeyError("unknown account")
            ps=db.execute("SELECT * FROM reference_positions WHERE account_id=? AND tenant_id=? ORDER BY created_at",(account_id,tenant_id)).fetchall();os=db.execute("SELECT * FROM reference_orders WHERE account_id=? AND tenant_id=? ORDER BY created_at",(account_id,tenant_id)).fetchall()
        return {**dict(a),"positions":[dict(p) for p in ps],"orders":[dict(o) for o in os],"play_money":True}
    def posture(self):
        with self.store.connect() as db:
            counts={k:int(db.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]) for k,table in {"markets":"reference_markets","accounts":"reference_accounts","positions":"reference_positions","orders":"reference_orders","trades":"reference_trades"}.items()}
        return {"version":VERSION,"mode":"reference-sandbox","play_money_only":True,"real_money_custody":False,"matching_engine":"sandbox price-time complementary matcher","settlement_authority":"sandbox-only",**counts}
    def self_test(self,tenant_id="local",actor="system:v0.26-self-test"):
        m=self.create_market(tenant_id,"Will U.S. CPI be above 3.0% on September 11, 2026?","This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.",actor)
        if m["state"]!="OPEN":return {"ok":True,"market_id":m["market_id"],"state":m["state"],"held_safely":True,"zero_real_money":True,"matching_exercised":False}
        a=self.create_account(tenant_id,"YES Trader",actor);b=self.create_account(tenant_id,"NO Trader",actor);o1=self.place_order(tenant_id,m["market_id"],a["account_id"],"YES",10,0.62,actor);o2=self.place_order(tenant_id,m["market_id"],b["account_id"],"NO",10,0.40,actor);market=self.get_market(m["market_id"],tenant_id)
        if not market["trades"]:return {"ok":False,"reason":"orders did not match","market":market}
        s=self.resolve_market(tenant_id,m["market_id"],"YES",{"authority":"BLS","fixture":True},actor);aa=self.account(a["account_id"],tenant_id);bb=self.account(b["account_id"],tenant_id)
        total=round(float(aa["cash"])+float(bb["cash"]),8)
        return {"ok":len(market["trades"])==1 and abs(total-2*STARTING_BALANCE)<1e-6,"market_id":m["market_id"],"trade":market["trades"][0],"settlement_hash":s["settlement_hash"],"cash_conserved":total,"zero_real_money":True,"matching_exercised":True}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store:_SERVICE=ReferenceExchangeService(store)
    return _SERVICE
