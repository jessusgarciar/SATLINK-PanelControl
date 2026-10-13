# Preparación de PostgreSQL en Windows

## Instalación existente

Antes de instalar, revisa herramientas, servicios, directorios y puertos:

```powershell
Get-Command psql, pg_ctl -ErrorAction SilentlyContinue
Get-Service *postgres* -ErrorAction SilentlyContinue
Get-ChildItem 'C:/Program Files/PostgreSQL' -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 5432,5433 -State Listen -ErrorAction SilentlyContinue
```

Comprueba también aplicaciones instaladas en Windows: que `psql` no esté en el PATH no demuestra que PostgreSQL no exista. Si ya hay una instalación, conserva su clúster y bases; no ejecutes `initdb` sobre su directorio de datos ni cambies su configuración. El administrador de esa instancia deberá autorizar el acceso si se decide reutilizarla.

En esta computadora no se detectó una instalación previa en las comprobaciones realizadas. Se preparó una instancia portátil separada, con PostgreSQL 17.11 y puerto 5433.

## Reproducir una instalación portátil nueva

La [página oficial para Windows](https://www.postgresql.org/download/windows/) remite a los [binarios de EDB](https://www.enterprisedb.com/download-postgresql-binaries). Descarga el archivo Windows x86-64 de PostgreSQL 17 y verifica la versión extraída. La preparación actual utilizó el enlace oficial EDB `https://sbp.enterprisedb.com/getfile.jsp?fileid=1260616`.

Desde la raíz del proyecto, en una computadora sin esta instalación local:

```powershell
if (Test-Path .local/postgresql) { throw 'La instalación local ya existe. No sobrescribir.' }
New-Item -ItemType Directory -Path .local/postgresql | Out-Null
Invoke-WebRequest 'https://sbp.enterprisedb.com/getfile.jsp?fileid=1260616' -OutFile "$env:TEMP/satlink-postgresql-17.zip"
Expand-Archive -LiteralPath "$env:TEMP/satlink-postgresql-17.zip" -DestinationPath .local/postgresql
./.local/postgresql/pgsql/bin/postgres.exe --version
```

Confirma que el puerto 5433 esté libre antes de preparar el clúster:

```powershell
if (Get-NetTCPConnection -LocalPort 5433 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Puerto 5433 ocupado. Conserva la instancia existente y elige otro puerto.'
}
if (Test-Path .local/postgresql/data) { throw 'El directorio de datos ya existe. No reinicializar.' }
./.local/postgresql/pgsql/bin/initdb.exe -D .local/postgresql/data -U satlink_dev --encoding=UTF8 --locale=C --auth-local=reject --auth-host=sspi
if ($LASTEXITCODE -ne 0) { throw 'No continuar: falló initdb.' }
```

Configura únicamente este clúster nuevo. SSPI utiliza la identidad Windows actual y un mapeo explícito del usuario y dominio; la [documentación de PostgreSQL](https://www.postgresql.org/docs/17/sspi-auth.html) explica este método:

```powershell
$satlinkIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name.Split('\')
$satlinkPrincipal = $satlinkIdentity[1] + '@' + $satlinkIdentity[0]
@"
host all satlink_dev 127.0.0.1/32 sspi include_realm=1 map=satlink_windows
host all satlink_dev ::1/128 sspi include_realm=1 map=satlink_windows
"@ | Set-Content .local/postgresql/data/pg_hba.conf -Encoding ascii
"satlink_windows $satlinkPrincipal satlink_dev" | Set-Content .local/postgresql/data/pg_ident.conf -Encoding ascii
@"
listen_addresses = '127.0.0.1'
port = 5433
timezone = 'UTC'
log_timezone = 'UTC'
"@ | Set-Content .local/postgresql/data/postgresql.auto.conf -Encoding ascii
```

Inicia y crea una base vacía solo en el clúster recién preparado:

```powershell
./.local/postgresql/pgsql/bin/pg_ctl.exe -D .local/postgresql/data -l .local/postgresql/server.log -w start
./.local/postgresql/pgsql/bin/pg_isready.exe -h 127.0.0.1 -p 5433
./.local/postgresql/pgsql/bin/createdb.exe -h 127.0.0.1 -p 5433 -U satlink_dev -w satlink_dev
./.local/postgresql/pgsql/bin/psql.exe -h 127.0.0.1 -p 5433 -U satlink_dev -d satlink_dev -w -c '\conninfo'
```

No hay tablas de aplicación, migraciones ni contraseñas configuradas. SSPI requiere iniciar la conexión con la cuenta Windows autorizada; copiar el directorio de datos a otra computadora no reproduce su identidad. En otra plataforma será necesario preparar la autenticación apropiada antes del desarrollo.

Los pasos habituales de inicio y parada aparecen en el README principal. El clúster se conserva al detener el proceso; nunca borres su carpeta para reiniciar el servidor.
