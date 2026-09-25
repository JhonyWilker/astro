# Inventario técnico de ASTRO

25 de septiembre de 2026

Este inventario recoge los equipos y dispositivos disponibles al comenzar el proyecto. No contiene contraseñas, claves, números de serie, direcciones MAC ni direcciones IP públicas.

## Equipo principal de desarrollo

**HP Victus by HP Laptop 16-d1xxx**

- Uso: ordenador principal de Jhony; se desplaza entre casa y restaurante.
- Sistema operativo: Windows 11 Pro de 64 bits, versión 10.0.26200, compilación 26200.
- Procesador: Intel Core i7-12700H, 14 núcleos y 20 procesadores lógicos.
- Memoria: 16 GB de RAM.
- Almacenamiento: SSD interno de 512 GB; 345 GB utilizados y 130,9 GB libres durante el inventario.
- Gráfica integrada: Intel Iris Xe Graphics.
- Gráfica dedicada: NVIDIA GeForce RTX 3060 Laptop, 6 GB de memoria.
- Red: adaptador MediaTek MT7921 Wi‑Fi 6.
- Acceso remoto: Tailscale instalado y activo.

### Periféricos disponibles

- Micrófono USB HyperX QuadCast S.
- Auriculares Razer Barracuda X 2.4 con micrófono.
- Micrófonos y altavoces integrados.
- Cámara HP Wide Vision HD.
- Monitor HP 25x.

El portátil y el micrófono HyperX son suficientes para comenzar las futuras pruebas de voz. La elección definitiva del micrófono se hará en el bloque de voz.

## Herramientas de desarrollo

- Python 3.14.7.
- Git 2.53.0 para Windows.
- Visual Studio Code 1.109.3 de 64 bits.

Las tres herramientas están instaladas y responden desde PowerShell en el portátil principal.

## Dispositivos móviles

- iPhone 15 Pro Max con iOS 26.
- iPad Air de 13 pulgadas, modelo 2026, con iPadOS 26.

El iPhone será el dispositivo móvil principal de ASTRO. La primera versión usará una app web; la app nativa llegará en fases posteriores.

## Torre del restaurante

**Dell OptiPlex 7040 SFF**

- Ubicación: restaurante.
- Uso previsto: permanecer en el restaurante como posible nodo local del negocio.
- Procesador: Intel Core i5; modelo y generación pendientes de confirmar.
- Memoria: 32 GB de RAM.
- Almacenamiento: disco duro mecánico de 1 TB.
- Gráfica dedicada: no tiene.
- Sistema operativo: todavía no instalado.
- Red: conexión Ethernet disponible.
- SAI/UPS: no tiene.

No se considera el cerebro principal de ASTRO. Su función concreta se decidirá más adelante según las necesidades del restaurante. Antes de usarla como servidor convendrá valorar un SSD y un SAI/UPS.

## Otro ordenador del restaurante

- Sistema operativo: Anarchy Linux, basado en Arch Linux.
- Uso actual: reproducción de vídeos en el local.
- Función en ASTRO: ninguna asignada por ahora.

Anarchy Linux no se elegirá como sistema del futuro servidor de ASTRO. El plan mantiene Ubuntu Server LTS para los equipos servidores.

## Redes

Hay dos conexiones independientes:

### Casa

- Operador: Movistar.
- Conexión: fibra óptica de 1 Gb/s simétrico.
- Router: modelo Movistar con Wi‑Fi 6; modelo exacto pendiente.

### Restaurante

- Operador: Movistar.
- Conexión: fibra óptica de 1 Gb/s simétrico.
- Router: modelo Movistar con Wi‑Fi 6; modelo exacto pendiente.

No hay todavía VPS, NAS ni otro servidor preparado para funcionar las 24 horas. El VPS se contratará en la fase 9a.

## Dispositivos de casa

- Un televisor.
- Un dispositivo Alexa; modelo pendiente.
- Tres cámaras previstas, todavía sin instalar.

## Dispositivos del restaurante

- Cinco televisores.
- Una PlayStation 5 en la oficina.
- Nueve cámaras.
- Sistema de alarma.
- Ordenador con Anarchy Linux para vídeos.
- Torre Dell OptiPlex 7040 SFF.

## Pendientes para fases futuras

- Confirmar el modelo exacto del Intel Core i5 de la torre Dell.
- Confirmar los modelos de routers y dispositivos solo cuando una integración los necesite.
- Decidir la función definitiva de la torre Dell.
- Elegir el futuro equipo doméstico que ejecutará voz, cámaras y Home Assistant.
- Contratar y configurar el VPS en la fase prevista.
