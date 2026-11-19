# Rclone Manager - Project Instructions & Ponytail Mode

## Flujo de Trabajo (Git Flow)
- **Rama `master`**: Reservada estrictamente para producción. NUNCA hacer push directo.
- **Rama `staging`**: Rama principal de desarrollo y pruebas del stack actual.
- **Rama `feature/rust-migration`**: Rama activa para la evolución y migración del core a Rust.
- **Merge a master**: Solo mediante Pull Request (PR) real (`gh pr create`).
- **Validación**: Mandatorio superar todos los hooks locales de git antes de abrir un PR.

## Convenciones de Commits (MANDATORIO)
- **Conventional Commits**: Cada commit DEBE respetar el estándar `tipo(ámbito): descripción` (ej: `feat(core): add async rclone client`, `fix(mount): clean zombie mounts`).
- Tipos válidos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- El hook local `.githooks/commit-msg` bloquea cualquier mensaje que no cumpla el estándar.

## Seguridad & Pre-Commit (MANDATORIO)
El hook `.githooks/pre-commit` valida automáticamente:
1. **Secretos:** `gitleaks` previene el commit de tokens, passwords o claves privadas.
2. **Sintaxis:** Validación sintáctica de Rust (`cargo fmt`, `cargo check`), Bash (`bash -n`) y Python (`py_compile`).
3. **CVEs:** `cargo audit` verifica vulnerabilidades en dependencias.

## Política de Rust Puro y Duro (NON-NEGOTIABLE)
- En la rama `feature/rust-migration` está terminantemente prohibido agregar o commitear archivos de la versión anterior en Python (`.py`, `pyproject.toml`, `uv.lock`, etc.).
- El pre-commit hook bloquea activamente cualquier commit que contenga archivos Python.
- El proyecto debe evolucionar como una aplicación Rust 100% nativa.

## Ponytail Mode (Senior Dev Minimalist Philosophy)
- El mejor código es el que nunca se escribe.
- YAGNI estricto: cero wrappers, abstracciones o flexibilidad prematura que nadie ha solicitado.
- Toda lógica no trivial debe estar respaldada por un test o aserción.
- Usar los comandos `/ponytail`, `/ponytail-review`, `/ponytail-audit` y `/ponytail-debt`.
