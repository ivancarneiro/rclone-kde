# Runbook de Implementación ODD: CodeGraph + MemPalace (Mínimo) + Grill-Me + Ponytail

> **Instrucción para el Agente (Antigravity IDE):**
> Lee este documento completo y ejecuta cada fase de forma secuencial y autónoma en la raíz del proyecto actual utilizando tus herramientas de terminal y gestión de archivos. No pidas confirmación paso a paso salvo error bloqueante. Al terminar, entrega el resumen de verificación de la Fase 5.

## Requisitos previos

Antes de iniciar, verifica en terminal que el entorno Linux cuente con:

- `git`
- `node` y `npx` (Node.js ≥ 18, requerido por CodeGraph y `skills`)
- `uv` (obligatorio para resolver e instalar MemPalace aplicando `--excludes`)

```bash
command -v git node npx uv
```

---

## Fase 1: Limpieza de SDD y Preparación del Repositorio

**Objetivo:** Archivar las especificaciones pesadas de `spec-kit` / SDD sin perder decisiones críticas y proteger el repositorio frente a archivos locales generados por las herramientas.

1. **Inspeccionar y archivar SDD:** Busca carpetas de especificaciones previas (`.specify/`, `.speckit/`, `specs/`, `docs/specs/`). Si existen, muévelas a `docs/archive-sdd/` (créalo si no existe) para evitar que contaminen el contexto diario. Conserva únicamente archivos de glosario o decisiones arquitectónicas irreversibles (`GLOSSARY.md`, `ADR/`).

2. **Actualizar `.gitignore`:** Verifica si ya existen y, sin duplicar entradas previas, añade al final de `.gitignore`:

```gitignore
# Local AI Code Graph & Memory
.codegraph/
.mempalace/
mempalace.yaml
entities.json
```

---

## Fase 2: Instalación e Indexación de CodeGraph + Git Hooks

**Objetivo:** Configurar el mapa estructural del código y automatizar su sincronización incremental de forma portable y sin sobrescribir hooks previos.

1. **Inicializar e indexar el código fuente:** En repositorios nuevos es obligatorio ejecutar `init -y` antes de poder usar `index` o `sync`. Ejecuta en la raíz del proyecto:

```bash
npx -y @colbymchenry/codegraph init -y
npx -y @colbymchenry/codegraph status
```

Comprueba además que `.codegraph/errors.log` no exista o esté vacío.

2. **Configurar Git Hooks automáticos sin sobrescribir hooks existentes:** Detecta el directorio real de hooks del repositorio (soportando `core.hooksPath` personalizado como `.githooks` además de `.git/hooks`) y la ruta del binario `node` para que funcione en shells no interactivas:

```bash
HOOKS_DIR="$(git config --get core.hooksPath || echo ".git/hooks")"
NODE_BIN_DIR="$(dirname "$(command -v node)")"
mkdir -p "$HOOKS_DIR"

for hook in post-commit post-merge post-checkout; do
  HOOK_FILE="$HOOKS_DIR/$hook"
  if [ ! -f "$HOOK_FILE" ]; then
    printf '#!/bin/sh\n' > "$HOOK_FILE"
  fi
  if ! grep -q '@colbymchenry/codegraph sync' "$HOOK_FILE"; then
    cat <<EOF >> "$HOOK_FILE"

# Sincronización incremental silenciosa de CodeGraph
export PATH="${NODE_BIN_DIR}:\$HOME/.local/bin:\$PATH"
if [ -d ".codegraph" ]; then
    npx -y @colbymchenry/codegraph sync --quiet >/dev/null 2>&1 &
fi
EOF
  fi
  chmod +x "$HOOK_FILE"
done
```

---

## Fase 3: Instalación Mínima de MemPalace (Exclusión de Librerías Innecesarias) + MCPs

**Objetivo:** Instalar MemPalace de forma aislada bloqueando dependencias opcionales pesadas, inicializar el proyecto sin duplicar el código fuente ya indexado en CodeGraph, y registrar ambos servidores MCP en Antigravity IDE.

> **Nota técnica sobre la poda de dependencias:** Por defecto, `mempalace` instala ~85 paquetes (~402 MB) al arrastrar dependencias opcionales/de servidor de `chromadb` y extras de CLI (`kubernetes`, `uvicorn`, `huggingface-hub`, `hf-xet`, `typer`, `rich`, `bcrypt`, `build`, `httpx2`, `flatbuffers`, `tzdata` y sus transitivas). Bloqueando esos 11 paquetes raíz mediante `uv --excludes`, el entorno aislado baja a **44 paquetes (~262 MB, ~140 MB de ahorro)** conservando intacto el piso mínimo requerido en runtime por `mempalace`, `chromadb` y `onnxruntime`.

### 1. Crear el archivo global de exclusiones

```bash
mkdir -p "$HOME/.config/mempalace"
cat <<'EOF' > "$HOME/.config/mempalace/excludes.txt"
kubernetes
uvicorn
bcrypt
typer
build
rich
hf-xet
huggingface-hub
httpx2
flatbuffers
tzdata
EOF
```

### 2. Instalar o podar MemPalace de forma idempotente con `uv`

Comprueba si el entorno de la herramienta `mempalace` ya existe y cuántos paquetes tiene:

```bash
MEMPALACE_PY="$HOME/.local/share/uv/tools/mempalace/bin/python"
EXCLUDES_FILE="$HOME/.config/mempalace/excludes.txt"

if [ ! -x "$MEMPALACE_PY" ]; then
  uv tool install mempalace --excludes "$EXCLUDES_FILE"
else
  PKG_COUNT="$(uv pip freeze --python "$MEMPALACE_PY" | wc -l)"
  if [ "$PKG_COUNT" -gt 50 ]; then
    uv tool install --force --reinstall mempalace --excludes "$EXCLUDES_FILE"
  else
    mempalace --version
  fi
fi

uv pip freeze --python "$MEMPALACE_PY" > "$HOME/.config/mempalace/requirements.lock"
```

- Verifica que el entorno quede limpio (~44 paquetes) y sin exclusiones filtradas:

```bash
wc -l "$HOME/.config/mempalace/requirements.lock"
! grep -E '^(kubernetes|uvicorn|huggingface-hub|hf-xet|typer|rich|bcrypt|build|httpx2|flatbuffers|tzdata)==' "$HOME/.config/mempalace/requirements.lock"
```

- **Para futuras actualizaciones** sin reintroducir paquetes innecesarios, ejecuta siempre:

```bash
uv tool install --upgrade mempalace --excludes "$HOME/.config/mempalace/excludes.txt"
```

### 3. Inicializar el proyecto en el Palacio de Memoria (sin minar código fuente)

Ejecuta la inicialización no interactiva en la raíz del proyecto (genera `mempalace.yaml` y `entities.json`, ya ignorados en `.gitignore`, conectados al palacio compartido en `~/.config/mempalace/palace`):

```bash
mempalace init --yes --no-llm .
```

- **Nota crítica:** NO uses `--auto-mine` ni ejecutes `mempalace mine .` sobre todo el código fuente para evitar duplicar el índice de CodeGraph e inflar ChromaDB.
- Si el proyecto cuenta con documentación arquitectónica crítica (`ADR/` o `GLOSSARY.md`), mínala selectivamente usando el nombre del proyecto como *wing*:

```bash
# Ejemplo (ejecutar solo si existen esos archivos/carpetas):
# mempalace mine ADR/ --wing <nombre_proyecto>
```

- Verifica el estado del palacio:

```bash
mempalace status
```

### 4. Registrar y validar los servidores MCP en Antigravity IDE

Inspecciona si existen `~/.gemini/config/mcp_config.json` y/o `~/.gemini/antigravity/mcp_config.json`. Actualiza **todos los que existan** (o crea `~/.gemini/config/mcp_config.json` si no existe ninguno) **fusionando** en `mcpServers` sin sobrescribir ni borrar servidores previos ni sus variables de entorno.

Reglas obligatorias en la configuración:
- **`codegraph`:** DEBE incluir `"--mcp"` en `"args"` (`["-y", "@colbymchenry/codegraph", "serve", "--mcp"]`). Sin `--mcp`, Antigravity falla con `connection closed: calling "initialize": EOF`.
- **`mempalace`:** Resuelve la ruta absoluta real (`MEMPALACE_MCP="$(command -v mempalace-mcp || echo "$HOME/.local/bin/mempalace-mcp")"`) y escribe esa ruta expandida en `"command"` (JSON no expande `~` ni `$HOME`).

Estructura resultante esperada dentro de `mcpServers` (ejemplo de referencia; sustituye `/ruta/absoluta/a/mempalace-mcp` por el valor real resuelto):

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "npx",
      "args": [
        "-y",
        "@colbymchenry/codegraph",
        "serve",
        "--mcp"
      ]
    },
    "mempalace": {
      "command": "/ruta/absoluta/a/mempalace-mcp"
    }
  }
}
```

Valida la sintaxis JSON y realiza un *smoke test* JSON-RPC `initialize` por stdio sobre ambos servidores para confirmar que ambos responden con `"result"` y `"serverInfo"`:

```bash
for cfg in "$HOME/.gemini/config/mcp_config.json" "$HOME/.gemini/antigravity/mcp_config.json"; do
  [ -f "$cfg" ] && python3 -m json.tool "$cfg" >/dev/null
done

MSG='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"odd-verify","version":"1.0"}}}'
MEMPALACE_MCP="$(command -v mempalace-mcp || echo "$HOME/.local/bin/mempalace-mcp")"

printf '%s\n' "$MSG" | timeout 10 npx -y @colbymchenry/codegraph serve --mcp 2>/dev/null | head -n 1
printf '%s\n' "$MSG" | timeout 10 "$MEMPALACE_MCP" 2>/dev/null | head -n 1
```

---

## Fase 4: Orquestación de Skills y Reglas ODD

**Objetivo:** Verificar la disponibilidad de `grill-me`, instalar las skills de `ponytail` y `mempalace`, crear la skill orquestadora `odd-workflow` y activar la regla permanente del proyecto.

1. **Auditar e instalar Skills:**
   - Verifica que `grill-me` esté disponible (ya sea integrada de forma nativa en Antigravity IDE mediante el comando `/grill-me`, o instalada globalmente en `~/.gemini/antigravity/skills/` o `~/.agents/skills/`). No la dupliques localmente si ya está disponible.
   - Instala las skills de proyecto de forma no interactiva:

```bash
npx -y skills add DietrichGebert/ponytail -y
npx -y skills add MemPalace/mempalace -y
```

   *(Fallback: Si `npx skills` solicita selección de agente o confirmación interactiva, ejecuta con `-a antigravity -s '*' -y`, o descarga directamente los `SKILL.md` correspondientes desde GitHub en `.agents/skills/`).*

2. **Crear Skill Orquestadora (`.agent/skills/odd-workflow/SKILL.md`):**

````markdown
---
name: odd-workflow
description: Flujo de desarrollo orientado a resultados (ODD) integrando MemPalace, CodeGraph, Grill-Me y Ponytail.
---
# Protocolo Maestro ODD

Está prohibido redactar documentos de especificación tipo SDD/spec-kit. Toda tarea debe ejecutarse en estas 4 fases estrictas:

## Fase A: Contexto Histórico y Estructural (MemPalace + CodeGraph)
1. **Recuperar decisiones previas (MemPalace):** Consulta `mempalace` (`mempalace_search` / `wake-up`) en el *wing* de este proyecto para verificar reglas de negocio, errores resueltos y acuerdos previos antes de proponer soluciones.
2. **Mapear el código real (CodeGraph):** Usa el servidor MCP `codegraph` (`codegraph_explore`, `codegraph_impact`) para inspeccionar nodos y dependencias (`callers` / `callees`). Prohibido leer archivos completos a ciegas.

## Fase B: Definición de Outcome (Grill-Me)
1. Para tareas no triviales, aplica la entrevista estructurada tipo `/grill-me`.
2. Entrevista al usuario por rondas breves con recomendaciones técnicas hasta fijar el **criterio de éxito verificable (Outcome)** y los casos borde. Espera confirmación antes de programar.

## Fase C: Implementación Mínima (Ponytail)
1. Aplica `ponytail` (nivel `full`): aplica YAGNI estricto, reutiliza funciones existentes detectadas en CodeGraph y realiza ediciones quirúrgicas sin dependencias innecesarias.

## Fase D: Validación y Persistencia de Memoria
1. **Pruebas:** Ejecuta o crea los tests automatizados que verifiquen el Outcome acordado.
2. **Guardar acuerdo (MemPalace):** Antes de cerrar la tarea, guarda de forma literal (*verbatim*) en `mempalace` el **Outcome alcanzado, las decisiones tomadas y las reglas de negocio definidas** durante la sesión (organizado por el nombre del proyecto y el módulo modificado). No guardes código fuente crudo en MemPalace.
````

3. **Crear Regla Permanente de Proyecto (`.agent/rules/odd_mandate.md`):**

```markdown
# Mandato de Arquitectura ODD

- **División estricta de conocimiento:** Usa `codegraph` exclusivamente para estructura y dependencias del código; usa `mempalace` exclusivamente para decisiones arquitectónicas, reglas de negocio y acuerdos de sesiones previas.
- **Archivo histórico:** Ignora `docs/archive-sdd/` salvo orden explícita del usuario.
- **Activación por defecto:** Ante cualquier solicitud de desarrollo, refactorización o bugfix, ejecuta automáticamente el protocolo de la skill `odd-workflow`.
```

---

## Fase 5: Verificación Final (Checklist del Agente)

Al finalizar, presenta al usuario un resumen breve confirmando con datos observados:

1. **SDD y `.gitignore`:** Carpeta `docs/archive-sdd/` (si aplicaba SDD previo) y exclusiones confirmadas en `.gitignore` (`.codegraph/`, `.mempalace/`, `mempalace.yaml`, `entities.json`).
2. **CodeGraph y Hooks Git:** Cantidad de archivos, nodos y aristas indexados según `codegraph status` (confirmando 0 errores en `.codegraph/errors.log`) y ruta/permisos (`+x`) de los hooks `post-commit`, `post-merge` y `post-checkout`.
3. **MemPalace mínimo:** Presencia de `~/.config/mempalace/excludes.txt`, conteo exacto de paquetes en `requirements.lock` (~44 paquetes, 0 paquetes excluidos presentes), ruta del binario `mempalace-mcp` y estado saludable de `mempalace status` sin minado masivo de código fuente.
4. **Servidores MCP en Antigravity:** Archivos `mcp_config.json` actualizados sin borrar servidores previos, flag `--mcp` presente en `codegraph`, ruta absoluta en `mempalace`, JSON válido y handshake stdio `initialize` confirmado en ambos.
5. **Skills y Reglas ODD:** Disponibilidad confirmada de `/grill-me`, skills instaladas (`ponytail*`, `mempalace*`, `.agent/skills/odd-workflow/SKILL.md`) y regla `.agent/rules/odd_mandate.md` creada.
6. **Acción para el usuario:** Recordatorio de recargar la ventana de Antigravity IDE (`Developer: Reload Window`) y probar una invocación en vivo de `mempalace_status` y `codegraph_explore` para confirmar la activación de ambos servidores MCP.
