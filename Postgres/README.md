# PostgreSQL local para desarrollo

Destinatario: integrantes del equipo que ejecutan el proyecto con Docker.

Opcional. Quien no active el perfil `localdb` sigue usando la base remota (Neon)
sin ningún cambio.

## Por qué

Con Neon, cada consulta tarda 100–200 ms solo en ir y volver (servidor en
`us-east-1`). Con PostgreSQL en Docker tarda ~1 ms. Medido en el panel
administrativo:

| Endpoint | Neon | Local |
| --- | ---: | ---: |
| `GET /api/platforms/` | varios segundos | ~26 ms |
| `GET /api/journals/` | ~1–3 s | ~21 ms |
| `GET /api/platforms/link-check-logs/?current=true` | ~0,4 s | ~59 ms |

No afecta producción.

## Contenido de esta carpeta

La carpeta `Postgres/` está versionada en el repositorio; se obtiene con `git pull`.

| Archivo | Uso | En Git |
| --- | --- | --- |
| `.env.example` | Plantilla de variables | Sí |
| `.env` | Copia personal con contraseñas (paso 2) | **No** (ignorado por `**/.env`) |
| `sync-from-remote.sh` | Copia Neon a la base local | Sí |
| `.gitattributes` | Mantiene el script con saltos de línea Linux en Windows | Sí |
| `README.md` | Esta guía | Sí |

`sync-from-remote.sh` se ejecuta dentro de un contenedor Linux, no en Windows:

1. Descarga una copia del esquema `public` de Neon con `pg_dump` (solo lectura).
2. Borra la base local y la crea vacía.
3. Carga la copia con `pg_restore`.

Servicios en `docker-compose.yml`:

| Servicio | Perfil | Uso |
| --- | --- | --- |
| `postgres` | `localdb` | PostgreSQL 18 con volumen `postgres-data`. Puerto `127.0.0.1:5433` para clientes como DBeaver. |
| `postgres-sync` | `localdb-sync` | Ejecuta la copia. Solo corre cuando se invoca. |

---

## Requisitos

- Docker Desktop abierto.
- Proyecto actualizado (`git pull` de la rama con estos cambios).
- `Backend/.env` funcionando con Neon.
- PowerShell abierto en la **raíz** del proyecto (la carpeta con `docker-compose.yml`).
  Comprobar con `ls`: deben aparecer `Backend`, `Frontend`, `Postgres` y `docker-compose.yml`.

## Paso 1 — Crear `Postgres/.env`

```powershell
Copy-Item Postgres/.env.example Postgres/.env
```

Abrir `Postgres/.env` y completarlo:

```dotenv
# Base local: credenciales inventadas, solo para este equipo
POSTGRES_DB=repositorio
POSTGRES_USER=repositorio
POSTGRES_PASSWORD=inventa-una-clave-local

# Base remota (Neon): copiar los DATABASE_* de Backend/.env
REMOTE_DATABASE_HOST=<DATABASE_HOST de Backend/.env>
REMOTE_DATABASE_PORT=5432
REMOTE_DATABASE_NAME=<DATABASE_NAME de Backend/.env>
REMOTE_DATABASE_USER=<DATABASE_USER de Backend/.env>
REMOTE_DATABASE_PASSWORD=<DATABASE_PASSWORD de Backend/.env>
REMOTE_DATABASE_SSLMODE=require
```

`POSTGRES_DB` y `POSTGRES_USER` solo admiten letras, números y `_`.

## Paso 2 — (Solo si hace falta) cambiar el puerto

Si en el paso 3 aparece `port is already allocated`, otro programa usa el puerto
`5433`. Crear o editar el archivo `.env` de la **raíz** del proyecto y agregar
únicamente:

```dotenv
LOCAL_POSTGRES_PORT=5434
```

Ese archivo solo debe contener variables `NOMBRE=valor`; no pegar comandos en él.

## Paso 3 — Levantar PostgreSQL local

```powershell
docker compose --profile localdb up -d postgres
```

La primera vez descarga `postgres:18-alpine` (~1 minuto).

## Paso 4 — Copiar Neon a la base local

```powershell
docker compose --profile localdb --profile localdb-sync run --rm postgres-sync
```

Salida esperada:

```text
1/3 Descargando copia de la base remota (solo lectura)...
2/3 Recreando la base local 'repositorio'...
3/3 Restaurando datos en la base local...
Copia completada. Base local 'repositorio' lista.
```

Neon solo se lee; no se modifica.

## Paso 5 — Apuntar el backend a la base local

En `Backend/.env`, comentar las líneas de Neon con `#` y agregar las locales:

```dotenv
# Remota (Neon)
# DATABASE_HOST=...neon.tech
# DATABASE_NAME=...
# DATABASE_USER=...
# DATABASE_PASSWORD=...
# DATABASE_SSLMODE=require

# Local (Docker)
DATABASE_HOST=postgres
DATABASE_PORT=5432
DATABASE_NAME=repositorio
DATABASE_USER=repositorio
DATABASE_PASSWORD=<la misma POSTGRES_PASSWORD del paso 1>
DATABASE_SSLMODE=disable
```

- El puerto es **5432** (interno de Docker), aunque se haya cambiado en el paso 2.
- Si existe `POSTGRES_HOST=...` en `Backend/.env`, comentarlo: tiene prioridad
  sobre `DATABASE_HOST`.

## Paso 6 — Reconstruir y levantar todo

```powershell
docker compose build backend
docker compose --profile localdb up -d --force-recreate
docker compose exec backend python manage.py migrate
```

`migrate` aplica las migraciones de la rama actual que todavía no estén en Neon.

## Paso 7 — Verificar

```powershell
docker compose exec backend python manage.py shell -c "from django.db import connection; print(connection.settings_dict['HOST'])"
```

Debe imprimir `postgres`. Si imprime un host `neon.tech`, revisar el paso 5 y
repetir el paso 6.

Abrir `http://localhost:3000` e iniciar sesión con el usuario habitual (la copia
incluye los usuarios de Neon). El panel administrativo debe cargar en menos de 1 s.

---

## Uso diario

Levantar siempre con el perfil:

```powershell
docker compose --profile localdb up -d
```

## Actualizar la copia con datos nuevos de Neon

```powershell
docker compose --profile localdb --profile localdb-sync run --rm postgres-sync
docker compose exec backend python manage.py migrate
```

**Advertencia:** borra y recrea la base local. Se pierde todo lo creado localmente.

## Volver a Neon

En `Backend/.env`, quitar los `#` de las líneas de Neon y comentar las locales. Luego:

```powershell
docker compose up -d --force-recreate backend worker beat
```

## Conectarse con DBeaver u otro cliente

| Campo | Valor |
| --- | --- |
| Host | `127.0.0.1` |
| Puerto | `5433` (o `LOCAL_POSTGRES_PORT`) |
| Base | `POSTGRES_DB` |
| Usuario / contraseña | `POSTGRES_USER` / `POSTGRES_PASSWORD` |
| SSL | Desactivado |

---

## Errores comunes

| Error | Causa y solución |
| --- | --- |
| `port is already allocated` | Puerto ocupado: paso 2. |
| `server version mismatch` | Neon usa una versión mayor que la imagen local. Agregar `LOCAL_POSTGRES_IMAGE=postgres:<versión>-alpine` al `.env` raíz, borrar el volumen (ver abajo) y repetir desde el paso 3. |
| `unexpected character ... in variable name` | Un `.env` contiene texto que no es una variable; corregir la línea indicada. |
| `Falta REMOTE_DATABASE_...` | Falta ese valor en `Postgres/.env` (paso 1). |
| `password authentication failed` (paso 4) | Credenciales de Neon incorrectas en `Postgres/.env`. |
| `password authentication failed` (backend) | `DATABASE_PASSWORD` de `Backend/.env` no coincide con `POSTGRES_PASSWORD`. Si se cambió la contraseña después de crear la base, borrar el volumen y repetir. |
| `Cannot find path ... Postgres` | La terminal no está en la raíz del proyecto (`cd ..`). |
| El admin sigue lento | El backend sigue en Neon: paso 7. |

Borrar el volumen local (elimina la base local, no afecta Neon):

```powershell
docker compose --profile localdb down
docker volume rm open-access-academic-resource-repository_postgres-data
```

Si el nombre no coincide, buscarlo con `docker volume ls | findstr postgres`.

## Precauciones

- La copia contiene **usuarios, correos y sesiones reales**. No compartir el
  volumen, dumps ni `Postgres/.env`.
- Con la base local, `worker` y `beat` también la usan: si `RESEND_API_KEY` está
  configurada, el monitoreo de enlaces puede enviar correos reales.
- Los cambios locales **no llegan a Neon**.
- Las imágenes de RustFS no se copian; las URLs apuntan al bucket de cada entorno.
