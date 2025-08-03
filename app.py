import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from pathlib import Path

# ---------- Config ----------
TZ = ZoneInfo(os.getenv("TZ", "America/Santiago"))
# En Render no se puede escribir en /data sin Disk; usamos /tmp (efímero)
DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/logistica_inversa")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Files
PROD_PATH = Path(os.getenv("PROD_PATH", str(DATA_DIR / "Base_SKU2.xlsx")))
HIST_PATH = Path(os.getenv("HIST_PATH", str(DATA_DIR / "Registro_Escaneos.xlsx")))

# Excel sheets and columns
PROD_SHEET = os.getenv("PROD_SHEET", "Hoja2")
HIST_SHEET = os.getenv("HIST_SHEET", "Escaneos")
COL_COD = os.getenv("COL_COD", "Codigo")
COL_DESC = os.getenv("COL_DESC", "Descripcion")
COL_PREC = os.getenv("COL_PREC", "Precio")
COL_CENT = os.getenv("COL_CENT", "Centro")
HIST_COLS = ["Codigo","Descripcion","Cantidad","Valorizado","Centro","Usuario","Fecha","Hora"]

# ---------- App ----------
app = FastAPI(title="Escáner API (Cloud)", version="1.1")

# CORS (ajustar en producción)
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Helpers ----------
def load_productos() -> pd.DataFrame:
    if not Path(PROD_PATH).exists():
        raise FileNotFoundError(f"Maestro no encontrado: {PROD_PATH}")
    df = pd.read_excel(PROD_PATH, sheet_name=PROD_SHEET, dtype={COL_COD: str})
    df[COL_COD] = df[COL_COD].astype(str).str.strip()
    return df

def append_historico(row_dict: dict):
    if Path(HIST_PATH).exists():
        df_h = pd.read_excel(HIST_PATH, sheet_name=HIST_SHEET)
        df_h = pd.concat([df_h, pd.DataFrame([row_dict])], ignore_index=True)
    else:
        df_h = pd.DataFrame([[row_dict.get(c) for c in HIST_COLS]], columns=HIST_COLS)
    df_h = df_h.reindex(columns=HIST_COLS)
    with pd.ExcelWriter(HIST_PATH, engine="openpyxl", mode="w") as writer:
        df_h.to_excel(writer, index=False, sheet_name=HIST_SHEET)

# ---------- Models ----------
class ScanIn(BaseModel):
    codigo: str = Field(..., min_length=1)
    cantidad: int = Field(..., ge=1)
    usuario: Optional[str] = None
    centro: Optional[str] = None

# ---------- Routes ----------
@app.get("/health")
def health():
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "ok", "time": now, "data_dir": str(DATA_DIR)}

@app.post("/scan")
def scan_item(s: ScanIn):
    dfp = load_productos()
    code = s.codigo.strip()
    fila = dfp[dfp[COL_COD] == code]
    if fila.empty:
        desc = "DESCONOCIDO"
        precio = None
        centro = s.centro or None
    else:
        r = fila.iloc[0]
        desc = r.get(COL_DESC, None)
        precio = r.get(COL_PREC, None)
        centro = s.centro or r.get(COL_CENT, None)

    valorizado = None
    try:
        if pd.notna(precio):
            valorizado = float(precio) * int(s.cantidad)
    except Exception:
        valorizado = None

    now = datetime.now(TZ)
    row = {
        "Codigo": code,
        "Descripcion": desc,
        "Cantidad": int(s.cantidad),
        "Valorizado": valorizado,
        "Centro": centro,
        "Usuario": s.usuario,
        "Fecha": now.strftime("%Y-%m-%d"),
        "Hora": now.strftime("%H:%M:%S"),
    }
    append_historico(row)
    return {"ok": True, "saved": row}

# Subir/actualizar maestro (form-data: file=Excel, sheet opcional)
@app.post("/admin/upload-maestro")
async def upload_maestro(file: UploadFile = File(...), sheet: Optional[str] = Form(None)):
    data = await file.read()
    tmp = DATA_DIR / "tmp_upload.xlsx"
    with open(tmp, "wb") as f:
        f.write(data)

    _sheet = sheet or PROD_SHEET
    df = pd.read_excel(tmp, sheet_name=_sheet)
    for col in [COL_COD, COL_DESC, COL_PREC, COL_CENT]:
        if col not in df.columns:
            return {"ok": False, "error": f"Falta columna {col} en la hoja {_sheet}"}

    dest = Path(PROD_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    Path(tmp).replace(dest)
    return {"ok": True, "maestro": str(dest)}
# ---- Vistas en línea + descarga ----
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse, JSONResponse

@app.get("/admin/ver-historico", response_class=HTMLResponse)
def ver_historico():
    p = Path(HIST_PATH)
    if not p.exists():
        return "<h3>No hay histórico aún.</h3>"

    df = pd.read_excel(p, sheet_name=HIST_SHEET)

    # HTML simple con estilos y botones de descarga
    table_html = df.to_html(index=False, border=0)
    return f"""
    <html>
    <head>
      <meta charset="utf-8"/>
      <title>Registro de Escaneos</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; }}
        .actions a {{
          display:inline-block; margin-right:12px; padding:8px 12px; text-decoration:none; 
          border:1px solid #333; border-radius:6px;
        }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; }}
        th {{ background: #f3f3f3; }}
      </style>
    </head>
    <body>
      <h2>Registro de Escaneos</h2>
      <div class="actions">
        <a href="/admin/descargar-historico" target="_blank">Descargar Excel</a>
        <a href="/admin/historico.csv" target="_blank">Descargar CSV</a>
      </div>
      {table_html}
    </body>
    </html>
    """

@app.get("/admin/descargar-historico")
def descargar_historico():
    p = Path(HIST_PATH)
    if not p.exists():
        return JSONResponse({"ok": False, "error": "Aún no hay histórico"}, status_code=404)
    return FileResponse(path=str(p), filename="Registro_Escaneos.xlsx")

@app.get("/admin/historico.csv", response_class=PlainTextResponse)
def historico_csv():
    p = Path(HIST_PATH)
    if not p.exists():
        return "Aun no hay historico"
    df = pd.read_excel(p, sheet_name=HIST_SHEET)
    return df.to_csv(index=False)
