# Rutina de sesión de ASTRO

Esta lista mantiene cada sesión enfocada, comprobable y fácil de retomar.

## Al empezar

1. Leer `AGENTS.md` completo.
2. Leer `docs/plan.md` completo.
3. Leer las últimas entradas de `docs/log.md`.
4. Confirmar la fase indicada en la línea `Fase actual`.
5. Ejecutar `git status --short` para detectar cambios previos y no pisarlos.
6. Confirmar el sistema operativo y las herramientas necesarias para la fase.
7. Presentar: objetivo, qué se aprende, pasos, prueba, criterio de salida y registro.

## Durante la fase

1. Trabajar únicamente en la fase actual.
2. Explicar cada paso y cada línea de código antes de escribirla.
3. Mostrar el texto de los archivos antes de guardarlo.
4. Confirmar el permiso necesario antes de actuar. Una autorización expresa para toda la fase cubre los comandos y archivos ordinarios dentro del repositorio; las acciones destructivas, compras, permisos externos y secretos se confirman en el momento correspondiente.
5. Mantener claves y contraseñas fuera de Git.
6. Comprobar cada cambio antes de continuar.
7. Anotar las ideas futuras sin incorporarlas a la fase actual.

## Al cerrar

1. Ejecutar la prueba definida para la fase.
2. Confirmar que se cumple literalmente el criterio de salida.
3. Enseñar la entrada propuesta para `docs/log.md`.
4. Añadir al diario qué se hizo, qué falló, qué se decidió y cuál es la siguiente fase.
5. Marcar la fase como hecha en `docs/plan.md` y actualizar `Fase actual`.
6. Registrar en `docs/decisiones.md` cualquier decisión importante.
7. Ejecutar `git diff --check`, revisar `git status` y comprobar que no hay secretos.
8. Crear un commit descriptivo y subirlo solo cuando esté autorizado.
9. Comprobar la puerta del bloque antes de abrir el bloque siguiente.

## Frase para retomar el proyecto

> Soy Jhony, programo a nivel básico. Estamos construyendo ASTRO según `docs/plan.md`. Lee `AGENTS.md`, la fase actual y las últimas entradas de `docs/log.md`; después continuamos desde ahí.
