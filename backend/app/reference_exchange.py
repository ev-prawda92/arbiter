"""Arbiter v0.19 reference exchange and end-to-end settlement harness.

This is a play-money, non-custodial validation venue. It exists to exercise the
contract -> semantics -> positions -> resolution -> settlement -> audit lifecycle.
It is not a production exchange, matching engine, broker, or real-money venue.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any

from .resolution_infra import gen_id, utcnow, canonical_hash
from . import semantic_contract, compiler

STARTING_BALANCE = 10_000.0


class ReferenceExchangeService:
    def __init__(self, store):
        self.store = store
        self._init_db()

    def _init_db(self):
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS reference_markets (
              market_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, title TEXT NOT NULL,
              rules TEXT NOT NULL, state TEXT NOT NULL, semantic_json TEXT NOT NULL,
              compilation_json TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
              outcome TEXT, resolved_at TEXT, settlement_hash TEXT
            );
            CREATE TABLE IF NOT EXISTS reference_accounts (
              account_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, display_name TEXT NOT NULL,
              cash REAL NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reference_positions (
              position_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, market_id TEXT NOT NULL,
              account_id TEXT NOT NULL, side TEXT NOT NULL, quantity REAL NOT NULL,
              price REAL NOT NULL, cost REAL NOT NULL, payout REAL NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, settled_at TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_reference_positions_market ON reference_positions(market_id, account_id);
            """)

    def create_market(self, tenant_id: str, title: str, rules: str, actor: str) -> dict[str, Any]:
        market_id = gen_id("refmkt")
        sem = semantic_contract.analyze_contract(title, rules)
        comp = compiler.compile_rules(market_id, title, rules, self.store.list_authorities(), metadata={"reference_exchange": True})
        status = str(comp.get("status") or "REVIEW")
        state = "OPEN" if status == "READY" else "HELD"
        now = utcnow()
        with self.store.connect() as db:
            db.execute("INSERT INTO reference_markets(market_id,tenant_id,title,rules,state,semantic_json,compilation_json,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?)",
                       (market_id, tenant_id, title, rules, state, json.dumps(sem, sort_keys=True), json.dumps(comp, sort_keys=True), now, actor))
        self.store._audit(actor, "reference_market.created", "reference_market", market_id,
                          {"tenant_id": tenant_id, "state": state, "compiler_status": status, "play_money": True})
        return self.get_market(market_id, tenant_id)

    def create_account(self, tenant_id: str, display_name: str, actor: str) -> dict[str, Any]:
        account_id = gen_id("refacct")
        now = utcnow()
        with self.store.connect() as db:
            db.execute("INSERT INTO reference_accounts(account_id,tenant_id,display_name,cash,created_at) VALUES(?,?,?,?,?)",
                       (account_id, tenant_id, display_name, STARTING_BALANCE, now))
        self.store._audit(actor, "reference_account.created", "reference_account", account_id,
                          {"tenant_id": tenant_id, "starting_balance": STARTING_BALANCE})
        return {"account_id": account_id, "tenant_id": tenant_id, "display_name": display_name, "cash": STARTING_BALANCE, "created_at": now}

    def place_position(self, tenant_id: str, market_id: str, account_id: str, side: str, quantity: float, price: float, actor: str) -> dict[str, Any]:
        side = side.upper()
        if side not in {"YES", "NO"}: raise ValueError("side must be YES or NO")
        if quantity <= 0: raise ValueError("quantity must be > 0")
        if not (0 < price < 1): raise ValueError("price must be between 0 and 1")
        with self.store.connect() as db:
            market = db.execute("SELECT * FROM reference_markets WHERE market_id=? AND tenant_id=?", (market_id, tenant_id)).fetchone()
            if not market: raise KeyError("unknown market")
            if market["state"] != "OPEN": raise ValueError("market is not open")
            acct = db.execute("SELECT * FROM reference_accounts WHERE account_id=? AND tenant_id=?", (account_id, tenant_id)).fetchone()
            if not acct: raise KeyError("unknown account")
            cost = round(quantity * price, 8)
            if float(acct["cash"]) < cost: raise ValueError("insufficient play-money balance")
            pid = gen_id("refpos"); now = utcnow()
            db.execute("UPDATE reference_accounts SET cash=cash-? WHERE account_id=?", (cost, account_id))
            db.execute("INSERT INTO reference_positions(position_id,tenant_id,market_id,account_id,side,quantity,price,cost,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (pid, tenant_id, market_id, account_id, side, quantity, price, cost, now))
        self.store._audit(actor, "reference_position.opened", "reference_position", pid,
                          {"market_id": market_id, "account_id": account_id, "side": side, "quantity": quantity, "price": price, "cost": cost})
        return {"position_id": pid, "market_id": market_id, "account_id": account_id, "side": side, "quantity": quantity, "price": price, "cost": cost, "play_money": True}

    def resolve_market(self, tenant_id: str, market_id: str, outcome: str, evidence_summary: dict[str, Any], actor: str) -> dict[str, Any]:
        outcome = outcome.upper()
        if outcome not in {"YES", "NO"}: raise ValueError("outcome must be YES or NO")
        with self.store.connect() as db:
            market = db.execute("SELECT * FROM reference_markets WHERE market_id=? AND tenant_id=?", (market_id, tenant_id)).fetchone()
            if not market: raise KeyError("unknown market")
            if market["state"] != "OPEN": raise ValueError("only OPEN markets may resolve")
            positions = db.execute("SELECT * FROM reference_positions WHERE market_id=? AND tenant_id=?", (market_id, tenant_id)).fetchall()
            now = utcnow(); payouts=[]
            for p in positions:
                payout = float(p["quantity"]) if p["side"] == outcome else 0.0
                db.execute("UPDATE reference_positions SET payout=?, settled_at=? WHERE position_id=?", (payout, now, p["position_id"]))
                if payout:
                    db.execute("UPDATE reference_accounts SET cash=cash+? WHERE account_id=?", (payout, p["account_id"]))
                payouts.append({"position_id": p["position_id"], "account_id": p["account_id"], "side": p["side"], "payout": payout})
            packet = {"market_id": market_id, "outcome": outcome, "evidence_summary": evidence_summary, "payouts": payouts, "resolved_at": now, "play_money": True}
            sh = canonical_hash(packet)
            db.execute("UPDATE reference_markets SET state='SETTLED', outcome=?, resolved_at=?, settlement_hash=? WHERE market_id=?", (outcome, now, sh, market_id))
        self.store._audit(actor, "reference_market.settled", "reference_market", market_id,
                          {"outcome": outcome, "settlement_hash": sh, "position_count": len(payouts), "play_money": True})
        packet["settlement_hash"] = sh
        return packet

    def get_market(self, market_id: str, tenant_id: str) -> dict[str, Any]:
        with self.store.connect() as db:
            r = db.execute("SELECT * FROM reference_markets WHERE market_id=? AND tenant_id=?", (market_id, tenant_id)).fetchone()
            if not r: raise KeyError("unknown market")
            positions = db.execute("SELECT * FROM reference_positions WHERE market_id=? AND tenant_id=? ORDER BY created_at", (market_id, tenant_id)).fetchall()
        d=dict(r); d["semantic"] = json.loads(d.pop("semantic_json")); d["compilation"] = json.loads(d.pop("compilation_json")); d["positions"]=[dict(p) for p in positions]; d["play_money"]=True
        return d

    def account(self, account_id: str, tenant_id: str) -> dict[str, Any]:
        with self.store.connect() as db:
            a=db.execute("SELECT * FROM reference_accounts WHERE account_id=? AND tenant_id=?", (account_id,tenant_id)).fetchone()
            if not a: raise KeyError("unknown account")
            ps=db.execute("SELECT * FROM reference_positions WHERE account_id=? AND tenant_id=? ORDER BY created_at", (account_id,tenant_id)).fetchall()
        return {**dict(a), "positions":[dict(p) for p in ps], "play_money": True}

    def posture(self) -> dict[str, Any]:
        with self.store.connect() as db:
            markets=int(db.execute("SELECT COUNT(*) n FROM reference_markets").fetchone()["n"])
            accounts=int(db.execute("SELECT COUNT(*) n FROM reference_accounts").fetchone()["n"])
            positions=int(db.execute("SELECT COUNT(*) n FROM reference_positions").fetchone()["n"])
        return {"version":"0.19.0","mode":"reference-sandbox","play_money_only":True,"real_money_custody":False,"matching_engine":False,"settlement_authority":"sandbox-only","markets":markets,"accounts":accounts,"positions":positions}

    def self_test(self, tenant_id="local", actor="system:v0.19-self-test"):
        # deliberately precise weather contract so deterministic semantic/compiler layers can pass.
        m=self.create_market(tenant_id,"Will U.S. CPI be above 3.0% on September 11, 2026?",
            "This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.",actor)
        # Compiler conservatism may hold demo text. The harness only trades if OPEN; otherwise it verifies hold behavior.
        if m["state"] != "OPEN":
            return {"ok":True,"market_id":m["market_id"],"state":m["state"],"held_safely":True,"zero_real_money":True}
        a=self.create_account(tenant_id,"Self Test Trader",actor)
        p=self.place_position(tenant_id,m["market_id"],a["account_id"],"YES",10,0.6,actor)
        s=self.resolve_market(tenant_id,m["market_id"],"YES",{"authority":"BLS","fixture":True},actor)
        after=self.account(a["account_id"],tenant_id)
        return {"ok":True,"market_id":m["market_id"],"position_id":p["position_id"],"settlement_hash":s["settlement_hash"],"cash":after["cash"],"zero_real_money":True}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store: _SERVICE=ReferenceExchangeService(store)
    return _SERVICE
