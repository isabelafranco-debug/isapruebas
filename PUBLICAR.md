# Publicar Júpiter Jr en internet

La aplicación incluye un contenedor de publicación que sirve React y FastAPI desde el mismo origen HTTPS. El contenedor ejecuta las migraciones y el catálogo al arrancar, inicia la API y el procesador de trabajos, y los supervisa. Los productores pueden crear su cuenta desde computadoras y celulares. El GPS requiere permiso del dispositivo y HTTPS.

## Render

1. Crea o abre una cuenta en GitHub y sube el contenido de esta carpeta a un repositorio propio. El archivo `render.yaml` debe estar en la raíz del repositorio. Si usas el ZIP, extrae primero la carpeta `Jupiter-Jr` y sube su contenido.
2. En Render, inicia sesión, elige **New → Blueprint** y conecta ese repositorio. La configuración declara un servicio web Free y una base PostgreSQL 16 Free. Confirma que ambos recursos muestran precio cero antes de crearlos. El almacenamiento de archivos se conserva en la base mediante `DATABASE_FILE_STORAGE=1` y se recupera en el directorio temporal cuando hace falta.
3. Render construye la imagen del `Dockerfile` de la raíz y proporciona la conexión privada de la base. Al arrancar, las migraciones habilitan PostGIS. La aplicación configura su origen HTTPS a partir de `RENDER_EXTERNAL_URL` y usa cookies seguras.
4. Espera a que el servicio esté **Live** y abre la URL HTTPS que Render muestre en su panel. Comprueba que `/api/health` responde con `{"status":"ok"}`. Crea una cuenta nueva y prueba el lote piloto, el análisis y la descarga del PDF. Prueba la misma URL en el celular con datos móviles.
5. Conserva la base entre despliegues. La configuración está preparada para una instancia web que comparte los archivos temporales con su procesador. Para un dominio propio, configura `APP_PUBLIC_URL` con su origen HTTPS y reinicia el servicio.

La cuenta de Render es necesaria para crear los recursos. La URL pública definitiva se obtiene después del despliegue. El ZIP contiene la configuración de publicación y el frontend compilado. La base gratuita caduca a los 30 días y admite hasta 1 GB. El servicio se suspende después de 15 minutos sin tráfico y tarda aproximadamente un minuto en reactivarse. Los límites de memoria y consumo del plan gratuito deben comprobarse durante la prueba pública de los informes.

## Otros proveedores con Docker

Construye la imagen desde la raíz con `docker build -t jupiter-jr .`. Configura una base PostgreSQL con permisos para crear la extensión PostGIS, un volumen persistente montado en `/private`, y las variables `DATABASE_URL`, `APP_PUBLIC_URL` y `PORT`. `APP_PUBLIC_URL` debe ser el origen público HTTPS, por ejemplo `https://agricultura.example.org`. El proveedor debe enviar tráfico al puerto indicado por `PORT`, cuyo valor predeterminado es `10000`. El servicio necesita espacio para Chromium y memoria suficiente para generar los gráficos y el PDF.

## Si el despliegue falla

- Si Render solicita conectar GitHub, completa la autorización de tu repositorio en el navegador y vuelve a crear el Blueprint desde el panel.
- Si falla `CREATE EXTENSION postgis`, revisa que la base admita PostGIS y que su usuario tenga permisos para habilitarlo.
- Si la aplicación pide `APP_PUBLIC_URL`, asigna el origen HTTPS mostrado por el proveedor. En Render se obtiene automáticamente de `RENDER_EXTERNAL_URL`.
- Si el registro devuelve un error de origen, verifica que la URL usada en el navegador coincida con el origen configurado. Reinicia después de cambiar las variables.
- Si el PDF falla por falta de memoria, revisa los registros del servicio y aumenta la memoria del contenedor. El Dockerfile instala Chromium y sus bibliotecas.
- Si faltan informes después de reiniciar, confirma que `DATABASE_FILE_STORAGE=1` se haya activado antes de generarlos y que la base PostgreSQL sea la misma.
- Si el GPS falla en el teléfono, revisa el permiso de ubicación del navegador y que la URL empiece por HTTPS. La selección manual del mapa permite continuar.

## Entrega ZIP

Ejecuta `python scripts/package-project.py` después de compilar el frontend. El archivo se guarda en `deliverables/Jupiter-Jr-proyecto.zip`, junto con su SHA-256. Se incluyen el código, los archivos de despliegue, el CSV de referencia y el frontend compilado. Las cuentas y los documentos de las pruebas quedan en el almacenamiento local de la instalación.

Consulta las condiciones vigentes del proveedor antes de crear recursos. [Planes y precios](https://render.com/pricing), [Blueprints](https://render.com/docs/blueprint-spec), [PostGIS](https://render.com/docs/postgresql-extensions), [Discos persistentes](https://render.com/docs/disks).
