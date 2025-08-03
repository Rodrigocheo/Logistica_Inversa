
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
DATA_DIR = Path(os.getenv("DATA_DIR", "/data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Files
PROD_PATH = Path(os.getenv("PROD_PATH", DATA_DIR / "Base_SKU2.xlsx"))
HIST_PATH = Path(os.getenv("HIST_PATH", DATA_DIR / "Registro_Escaneos.xlsx"))

# Excel sheets and columns
PROD_SHEET = os.getenv("PROD_SHEET", "Hoja2")
HIST_SHEET = os.getenv("HIST_SHEET", "Escaneos")
COL_COD = os.getenv("COL_COD", "Codigo")
COL_DESC = os.getenv("COL_DESC", "Descripcion")
COL_PREC = os.getenv("COL_PREC", "Precio")
COL_CENT = os.getenv("COL_CENT", "Centro")
HIST_COLS = [ "Codigo","Descripcion","Cantidad","Valorizado","Centro","Usuario","Fecha","Hora" ]

# ---------- App ----------
app = FastAPI(title="Escáner API (Cloud)", version="1.1")

# CORS (adjust in production to your domain)
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_productos() -> pd.DataFrame:
    if not PROD_PATH.exists():
        raise FileNotFoundError(f"Maestro no encontrado: {PROD_PATH}")
    df = pd.read_excel(PROD_PATH, sheet_name=PROD_SHEET, dtype={COL_COD: str})
    df[COL_COD] = df[COL_COD].astype(str).str.strip()
    return df

def append_historico(row_dict: dict):
    if HIST_PATH.exists():
        df_h = pd.read_excel(HIST_PATH, sheet_name=HIST_SHEET)
        df_h = pd.concat([df_h, pd.DataFrame([row_dict])], ignore_index=True)
    else:
        df_h = pd.DataFrame([[row_dict.get(c) for c in HIST_COLS]], columns=HIST_COLS)
    df_h = df_h.reindex(columns=HIST_COLS)
    with pd.ExcelWriter(HIST_PATH, engine="openpyxl", mode="w") as writer:
        df_h.to_excel(writer, index=False, sheet_name=HIST_SHEET)

class ScanIn(BaseModel):
    codigo: str = Field(..., min_length=1)
    cantidad: int = Field(..., ge=1)
    usuario: Optional[str] = None
    centro: Optional[str] = None

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

# Optional: upload maestro in cloud (POST form-data with file)
@app.post("/admin/upload-maestro")
async def upload_maestro(file: UploadFile = File(...), sheet: Optional[str] = Form(None)):
    data = await file.read()
    tmp = DATA_DIR / "tmp_upload.xlsx"
    with open(tmp, "wb") as f:
        f.write(data)
    # Validate columns
    _sheet = sheet or PROD_SHEET
    df = pd.read_excel(tmp, sheet_name=_sheet)
    for col in [COL_COD, COL_DESC, COL_PREC, COL_CENT]:
        if col not in df.columns:
            return {"ok": False, "error": f"Falta columna {col} en la hoja {_sheet}"}
    tmp.rename(PROD_PATH) if PROD_PATH.exists() else tmp.replace(PROD_PATH)
    return {"ok": True, "maestro": str(PROD_PATH)}
