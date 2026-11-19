# Mandato de Arquitectura ODD

- **División estricta de conocimiento:** Usa `codegraph` exclusivamente para estructura y dependencias del código; usa `mempalace` exclusivamente para decisiones arquitectónicas, reglas de negocio y acuerdos de sesiones previas.
- **Archivo histórico:** Ignora `docs/archive-sdd/` salvo orden explícita del usuario.
- **Activación por defecto:** Ante cualquier solicitud de desarrollo, refactorización o bugfix, ejecuta automáticamente el protocolo de la skill `odd-workflow`.

