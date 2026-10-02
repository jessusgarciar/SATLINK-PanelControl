# Preparación para Git

Las reglas se administran desde la raíz: `.gitignore` excluye dependencias, entornos virtuales, PostgreSQL local, variables privadas, respaldos y archivos temporales. `.gitattributes` normaliza finales de línea y conserva documentos y recursos binarios. `.editorconfig` define el formato común de edición.

Se deben versionar los manifiestos, archivos de bloqueo, configuración del proyecto, fuentes de Vite, documentación, reporte de referencia y archivos `.gitkeep` que conservan carpetas vacías. Los archivos de migración futuros también se versionarán; no existe una regla que excluya archivos `.sql` en general.

## Revisar y preparar un commit

Desde la raíz en PowerShell:

```powershell
git status --short
git status --short --ignored
git add --dry-run .
```

El segundo comando permite comprobar que `.local`, `backend/.venv`, `frontend/node_modules` y `frontend/dist` están excluidos. El tercero muestra qué archivos se agregarían sin prepararlos todavía.

Cuando hayas revisado la lista:

```powershell
git add .
git diff --cached --stat
git diff --cached --check
git diff --cached
git commit -m "Prepara entorno inicial de SATLINK"
```

Revisa el contenido que vas a incluir: `.gitignore` no detecta secretos escritos dentro de archivos permitidos y no retira archivos que ya estén versionados. Las plantillas `.env.example` pueden versionarse, pero solo deben contener valores de ejemplo.

## Identidad y repositorio remoto

Consulta tu identidad antes de crear un commit:

```powershell
git config user.name
git config user.email
git remote -v
```

Si falta la identidad, define tus propios datos para este repositorio con `git config user.name` y `git config user.email`. No se configura una identidad ajena ni un remoto de ejemplo automáticamente.

Para publicar, crea o elige el repositorio remoto correcto y configura su URL con `git remote add origin` antes de ejecutar `git push -u origin main`. Esta preparación no crea commits ni publica archivos.
