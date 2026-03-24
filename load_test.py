import asyncio
import httpx
import time
from dataclasses import dataclass, field
from collections import defaultdict

# ── Configurações ────────────────────────────────────────────────
URL           = "https://www.andreavermont.online/tradutoralmas"
TOTAL_USERS   = 5000
RAMP_UP_SEC   = 10      # tempo para subir todos os usuários (segundos)
DURATION_SEC  = 60      # duração total do teste (segundos)
TIMEOUT_SEC   = 10      # timeout por requisição
# ────────────────────────────────────────────────────────────────

@dataclass
class Stats:
    success:  int = 0
    failed:   int = 0
    total:    int = 0
    latencies: list = field(default_factory=list)
    status_codes: dict = field(default_factory=lambda: defaultdict(int))
    start_time: float = field(default_factory=time.time)

stats = Stats()
stop_event = asyncio.Event()


async def worker(client: httpx.AsyncClient):
    while not stop_event.is_set():
        t0 = time.monotonic()
        try:
            r = await client.get(URL, timeout=TIMEOUT_SEC)
            latency = time.monotonic() - t0
            stats.latencies.append(latency)
            stats.status_codes[r.status_code] += 1
            if 200 <= r.status_code < 400:
                stats.success += 1
            else:
                stats.failed += 1
        except Exception:
            stats.failed += 1
        finally:
            stats.total += 1


async def reporter():
    last = 0
    while not stop_event.is_set():
        await asyncio.sleep(5)
        elapsed   = time.time() - stats.start_time
        delta_req = stats.total - last
        rps       = delta_req / 5
        last      = stats.total
        avg_lat   = (sum(stats.latencies[-500:]) / len(stats.latencies[-500:]) * 1000
                     if stats.latencies else 0)
        print(f"[{elapsed:5.0f}s] total={stats.total:>7}  ok={stats.success:>7}  "
              f"err={stats.failed:>5}  rps={rps:>6.0f}  avg_lat={avg_lat:>6.1f}ms  "
              f"status={dict(stats.status_codes)}")


async def main():
    print(f"Iniciando teste de carga")
    print(f"  URL     : {URL}")
    print(f"  Usuários: {TOTAL_USERS}")
    print(f"  Duração : {DURATION_SEC}s  |  Ramp-up: {RAMP_UP_SEC}s")
    print("-" * 70)

    limits = httpx.Limits(
        max_connections=TOTAL_USERS + 100,
        max_keepalive_connections=TOTAL_USERS,
    )
    async with httpx.AsyncClient(limits=limits, http2=True) as client:
        reporter_task = asyncio.create_task(reporter())

        # ramp-up gradual
        delay = RAMP_UP_SEC / TOTAL_USERS
        tasks = []
        for _ in range(TOTAL_USERS):
            tasks.append(asyncio.create_task(worker(client)))
            await asyncio.sleep(delay)

        await asyncio.sleep(max(0, DURATION_SEC - RAMP_UP_SEC))
        stop_event.set()

        await asyncio.gather(*tasks, return_exceptions=True)
        reporter_task.cancel()

    # ── Resumo final ─────────────────────────────────────────────
    elapsed = time.time() - stats.start_time
    lats    = sorted(stats.latencies)
    p50     = lats[int(len(lats) * 0.50)] * 1000 if lats else 0
    p90     = lats[int(len(lats) * 0.90)] * 1000 if lats else 0
    p99     = lats[int(len(lats) * 0.99)] * 1000 if lats else 0

    print("\n" + "=" * 70)
    print("RESUMO")
    print(f"  Duração real   : {elapsed:.1f}s")
    print(f"  Total requests : {stats.total}")
    print(f"  Sucesso        : {stats.success}")
    print(f"  Erros          : {stats.failed}")
    print(f"  RPS médio      : {stats.total / elapsed:.1f}")
    print(f"  Latência p50   : {p50:.1f}ms")
    print(f"  Latência p90   : {p90:.1f}ms")
    print(f"  Latência p99   : {p99:.1f}ms")
    print(f"  Status codes   : {dict(stats.status_codes)}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
