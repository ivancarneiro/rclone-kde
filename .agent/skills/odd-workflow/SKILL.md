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

