# Runbook de Implementación ODD: CodeGraph + MemPalace + Grill-Me + Ponytail

Instrucción para el Agente (Gemini Pro en Antigravity IDE):
Lee este documento completo y ejecuta cada fase de forma secuencial y autónoma en la raíz del proyecto actual utilizando tus herramientas de terminal y gestión de archivos. No pidas confirmación paso a paso salvo error bloqueante. Al terminar, entrega el resumen de verificación de la Fase 5.

Fase 1: Limpieza de SDD y Preparación del Repositorio

Objetivo: Archivar las especificaciones pesadas de spec-kit / SDD sin perder decisiones críticas y proteger el repositorio de archivos locales.
1. Inspeccionar y archivar SDD: Busca carpetas de especificaciones previas (.speckit/, specs/, docs/specs/). Si existen, muévelas a docs/archive-sdd/ (créalo si no existe) para evitar que ensucien el contexto diario. Conserva únicamente archivos de glosario o decisiones arquitectónicas irreversibles (GLOSSARY.md, ADR/).
2. Actualizar .gitignore: Verifica que .gitignore incluya las siguientes exclusiones para evitar subir bases de datos locales a GitLab:gitignore
# Local AI Code Graph & Memory
.codegraph/
.mempalace/
Usa el código con precaución.

Fase 2: Instalación e Indexación de CodeGraph + Git Hooks

Objetivo: Configurar el mapa estructural del código y automatizar su sincronización incremental en Linux.
1. Indexar el código fuente: Ejecuta en la raíz del proyecto:bash
npx -y @colbymchenry/codegraph index
Usa el código con precaución.
2. Crear Git Hooks automáticos: Escribe el archivo .git/hooks/post-commit para sincronizar el grafo en segundo plano sin bloquear la terminal:bash
#!/bin/sh
# Sincronización incremental silenciosa de CodeGraph
if [ -d ".codegraph" ]; then
    npx -y @colbymchenry/codegraph sync --quiet >/dev/null 2>&1 &
fi
Usa el código con precaución.
3. Permisos y cobertura de ramas: Ejecuta:bash
chmod +x .git/hooks/post-commit
cp .git/hooks/post-commit .git/hooks/post-merge
cp .git/hooks/post-commit .git/hooks/post-checkout
Usa el código con precaución.

Fase 3: Instalación y Configuración de MemPalace (Memoria Persistente)

Objetivo: Instalar MemPalace de forma aislada en Linux, inicializar el palacio de memoria para decisiones ODD y registrar ambos servidores MCP (codegraph y mempalace) en Antigravity.
1. Instalar paquete Python aislado: Verifica si pipx o uv están disponibles en el sistema Linux; instala mempalace asegurando que el ejecutable mempalace-mcp quede en el PATH (~/.local/bin/):bash
pipx install mempalace || uv tool install mempalace || pip install --user mempalace
Usa el código con precaución.
2. Inicializar el Palacio de Memoria: Ejecuta mempalace init en la raíz del proyecto (o en el directorio de configuración global ~/.mempalace) para generar la estructura base (palace.db y chroma/).
	• Nota crítica: No ejecutes mempalace mine sobre todo el código fuente del proyecto para evitar duplicar lo que ya hace CodeGraph y no inflar la base vectorial. Si existen archivos en GLOSSARY.md o ADR/, mínelos selectivamente.
3. Registrar MCPs en Antigravity IDE: Localiza ~/.gemini/antigravity/mcp_config.json (o ~/.gemini/config/mcp_config.json según tu instalación) y añade sin sobrescribir servidores previos:json
{
  "mcpServers": {
    "codegraph": {
      "command": "npx",
      "args": ["-y", "@colbymchenry/codegraph", "serve"]
    },
    "mempalace": {
      "command": "mempalace-mcp"
    }
  }
}
Usa el código con precaución.
(Nota: Si mempalace-mcp no está en el PATH global del entorno gráfico, reemplaza "command" por la ruta absoluta ~/.local/bin/mempalace-mcp).

Fase 4: Orquestación de Skills y Reglas ODD

Objetivo: Reutilizar la skill global grill-me, instalar ponytail y mempalace, y crear la skill maestra odd-workflow.
1. Auditar e instalar Skills:
	• Verifica que grill-me exista en el directorio global de skills (~/.gemini/antigravity/skills/ o ~/.agents/skills/). No la dupliques si ya es global.
	• Instala las skills faltantes ejecutando:bash
npx -y skills add DietrichGebert/ponytail
npx -y skills add MemPalace/mempalace
Usa el código con precaución.
(Fallback: Si npx skills solicita confirmación interactiva, descarga SKILL.md directamente desde GitHub a .agent/skills/ponytail/SKILL.md).
2. Crear Skill Orquestadora (.agent/skills/odd-workflow/SKILL.md):markdown
---
name: odd-workflow
description: Flujo de desarrollo orientado a resultados (ODD) integrando MemPalace, CodeGraph, Grill-Me y Ponytail.
---
# Protocolo Maestro ODD

Está prohibido redactar documentos de especificación tipo SDD/spec-kit. Toda tarea debe ejecutarse en estas 4 fases estrictas:

## Fase A: Contexto Histórico y Estructural (MemPalace + CodeGraph)
1. **Recuperar decisiones previas (MemPalace):** Consulta `mempalace` (`search` / `wake-up`) en el *wing* de este proyecto para verificar reglas de negocio, errores resueltos y acuerdos previos antes de proponer soluciones.
2. **Mapear el código real (CodeGraph):** Usa el servidor MCP `codegraph` (`explore`, `impact`) para inspeccionar nodos y dependencias (`callers` / `callees`). Prohibido leer archivos completos a ciegas.

## Fase B: Definición de Outcome (Grill-Me)
1. Para tareas no triviales, activa la skill global `grill-me`.
2. Entrevista al usuario por rondas breves con recomendaciones técnicas hasta fijar el **criterio de éxito verificable (Outcome)** y los casos borde. Espera confirmación antes de programar.

## Fase C: Implementación Mínima (Ponytail)
1. Aplica `ponytail` (nivel `full`): aplica YAGNI estricto, reutiliza funciones existentes detectadas en CodeGraph y realiza ediciones quirúrgicas sin dependencias innecesarias.

## Fase D: Validación y Persistencia de Memoria
1. **Pruebas:** Ejecuta o crea los tests automatizados que verifiquen el Outcome acordado.
2. **Guardar acuerdo (MemPalace):** Antes de cerrar la tarea, guarda de forma literal (*verbatim*) en `mempalace` el **Outcome alcanzado, las decisiones tomadas y las reglas de negocio definidas** durante la sesión (organizado por el nombre del proyecto y el módulo modificado). No guardes código fuente crudo en MemPalace.
Usa el código con precaución.
3. Crear Regla Permanente de Proyecto (.agent/rules/odd_mandate.md):markdown
# Mandato de Arquitectura ODD

- **División estricta de conocimiento:** Usa `codegraph` exclusivamente para estructura y dependencias del código; usa `mempalace` exclusivamente para decisiones arquitectónicas, reglas de negocio y acuerdos de sesiones previas.
- **Archivo histórico:** Ignora `docs/archive-sdd/` salvo orden explícita del usuario.
- **Activación por defecto:** Ante cualquier solicitud de desarrollo, refactorización o bugfix, ejecuta automáticamente el protocolo de la skill `odd-workflow`.
Usa el código con precaución.

Fase 5: Verificación Final (Checklist del Agente)

Al finalizar, presenta al usuario un resumen breve confirmando:
1. Cantidad de archivos/símbolos indexados en .codegraph/ y permisos (+x) de los hooks de Git.
2. Ruta del binario mempalace-mcp y confirmación de inicialización de MemPalace.
3. Ubicación de las skills (grill-me global, ponytail, mempalace y odd-workflow local).
4. Recordatorio para recargar la ventana de Antigravity IDE (Developer: Reload Window) para activar ambos servidores MCP.
Cuando ejecutes este Runbook en tu proyecto y recargues Antigravity IDE, si quieres puedo ayudarte a migrar selectivamente tus documentos críticos (ADR o reglas de negocio de tus antiguos archivos spec-kit) hacia el primer wing de MemPalace para que el agente arranque con todo el contexto histórico limpio.
