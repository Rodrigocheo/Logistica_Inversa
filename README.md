
# API Cloud (Render) - Escáner
- Persistencia en `/data` con Render Disk (1GB).
- Maestro: `/data/Base_SKU2.xlsx` (hoja: Hoja2).
- Registro: `/data/Registro_Escaneos.xlsx` (hoja: Escaneos).

## Deploy rápido
1) Sube `backend_cloud/` a un repo (GitHub).
2) Conecta el repo en Render → selecciona `render.yaml` (Infra as Code).
3) Render creará el servicio web y el disco montado en `/data`.
4) Sube tu maestro vía endpoint:
   - `POST /admin/upload-maestro` (form-data `file=@Base_SKU2.xlsx`, opcional `sheet=Hoja2`).
5) Prueba `/health` y luego `POST /scan`.

## Variables
- TZ=America/Santiago
- DATA_DIR=/data
- PROD_SHEET=Hoja2
- HIST_SHEET=Escaneos
- ALLOW_ORIGINS=*
