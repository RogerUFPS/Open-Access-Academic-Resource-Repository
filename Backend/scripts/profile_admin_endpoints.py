"""
Mide los endpoints administrativos lentos sin pasar por el navegador ni Next.js.

Uso (solo lectura, no modifica datos):
    Get-Content Backend/scripts/profile_admin_endpoints.py | docker compose exec -T backend python manage.py shell

Para cada endpoint informa: estado HTTP, número de consultas, tiempo total,
tiempo en SQL, tiempo fuera de SQL (Python/serialización) y las consultas
más lentas o más repetidas.
"""
import time
from collections import Counter

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.account.models import User
from apps.platforms.models import LinkCheckLog

ENDPOINTS = [
    "/api/platforms/link-check-logs/?current=true",
    "/api/platforms/link-check-logs/?current=true&verification_status=unavailable",
    "/api/platforms/link-check-logs/?current=true&failure_confirmed=true",
    "/api/platforms/",
    "/api/journals/",
]
RUNS = 2

admin = User.objects.filter(is_superadmin=True, is_active=True).first()
client = APIClient()
client.force_authenticate(user=admin)

print(f"Base: {connection.settings_dict['HOST']}  pool={bool(connection.settings_dict['OPTIONS'].get('pool'))}")
print(f"LinkCheckLog total: {LinkCheckLog.objects.count()}")
print("=" * 78)

for url in ENDPOINTS:
    for run in range(1, RUNS + 1):
        with CaptureQueriesContext(connection) as ctx:
            start = time.perf_counter()
            response = client.get(url, HTTP_HOST="localhost")
            total = time.perf_counter() - start
        queries = ctx.captured_queries
        sql = sum(float(q["time"]) for q in queries)
        data = getattr(response, "data", None) or {}
        count = data.get("count") if isinstance(data, dict) else None
        print(
            f"{url}\n  intento={run} status={response.status_code} count={count} "
            f"consultas={len(queries)} total={total*1000:.0f}ms "
            f"sql={sql*1000:.0f}ms fuera_sql={(total-sql)*1000:.0f}ms "
            f"bytes={len(response.content)}"
        )
    slow = sorted(queries, key=lambda q: float(q["time"]), reverse=True)[:3]
    for q in slow:
        print(f"    lenta {float(q['time'])*1000:.0f}ms: {q['sql'][:220]}")
    repeated = Counter(q["sql"][:120] for q in queries).most_common(2)
    for sql_text, times in repeated:
        if times > 1:
            print(f"    repetida x{times}: {sql_text}")
    print("-" * 78)
