"""Seeded scenario generator: seed + fault list -> initial SettleSim state."""
from __future__ import annotations

import random
from typing import Sequence

from settlesim.sim import BATCH_SIZE, DISK_FULL_PCT, NOW, Bank, Ledger, Payout, SettleSim, Worker

DEV_FAULTS = ("F1", "F2", "F4", "F6", "F7")
MERCHANTS = ["Kiran Textiles", "Anand Traders", "Bharat Foods", "Meera Pharma", "Sundaram Auto",
             "Lotus Stationers", "Ganga Dairy", "Vikram Electricals", "Saraswati Books", "Patel Hardware"]


# Hero scenario (SPEC §7). Seed picked so the numbers match the demo narrative
# (queue 37, limit 5, 8 payouts before the 429); it does not change difficulty.
HERO_SEED = 323
HERO_FAULTS = ("F6", "F1", "F7")


def hero() -> SettleSim:
    return generate(HERO_SEED, HERO_FAULTS)


def _key(rng: random.Random) -> str:
    return "key-" + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(6))


def generate(seed: int, faults: Sequence[str]) -> SettleSim:
    bad = [f for f in faults if f not in DEV_FAULTS]
    if bad:
        raise ValueError(f"unsupported fault id(s): {bad}")
    f = set(faults)
    rng = random.Random(seed)
    # Draw every value first so unrelated values do not shift when the fault set changes.
    cred_id = f"cred-{rng.randrange(65536):04x}"
    cred_ok = NOW + rng.randrange(1, 31) * 86400
    cred_expired = NOW - rng.randrange(3600, 5 * 86400)
    key_a, key_b = _key(rng), _key(rng)
    rate_limit = rng.randrange(3, 7)
    conc_over = rate_limit + rng.randrange(2, 9)
    conc_ok = rng.randrange(1, rate_limit + 1)
    disk_ok, disk_full = rng.randrange(35, 71), rng.randrange(DISK_FULL_PCT, 100)
    conn_used, conn_max = rng.randrange(2, 9), 20
    queue_stopped, queue_full = rng.randrange(20, 61), rng.randrange(15, 51)
    payouts = [Payout(f"PO-{1001 + i}", rng.choice(MERCHANTS), rng.randrange(50, 951) * 100)
               for i in range(BATCH_SIZE)]

    queue = 0
    if "F6" in f:
        queue = queue_stopped
    if "F4" in f:
        queue = max(queue, queue_full)
    return SettleSim(
        Ledger(up=True, disk_pct=disk_full if "F4" in f else disk_ok, conn_used=conn_used, conn_max=conn_max),
        Worker(running="F6" not in f, queue_depth=queue),
        Bank(cred_id=cred_id, cred_expires_at=cred_expired if "F1" in f else cred_ok,
             vault_active_key=key_a, key_in_use=key_b if "F2" in f else key_a,
             max_concurrency=conc_over if "F7" in f else conc_ok, rate_limit=rate_limit),
        payouts,
    )
