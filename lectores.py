"""
lectores.py
-----------
Lee los tres tipos de Excel (Membresías, PagoYa y Saldos) y el histórico
del tablero HTML, y los convierte en tablas limpias listas para guardar.

Si algún día cambia el nombre de una columna en tus Excel, este es el
archivo que hay que ajustar.

PRIVACIDAD: de cada Excel solo se toman las columnas que usa el tablero.
Placa, cuenta bancaria, links, CURP/cédula visibles, id_users, vínculos a
otros archivos, observaciones y la columna SALDO de PagoYa NUNCA se leen.
La identificación se usa solo para cruzar archivos y se guarda cifrada
(ver base_datos.py).
"""

import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd
from python_calamine import CalamineWorkbook


class ErrorLectura(Exception):
    """Error con un mensaje claro para mostrar en pantalla."""


@dataclass
class Resultado:
    tabla: pd.DataFrame
    avisos: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# ----------------------------------------------------------------------
# Utilidades de texto, números, fechas y semanas
# ----------------------------------------------------------------------

MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic"]

CIUDADES_COLOMBIA = [
    "bogota", "medellin", "cali", "barranquilla", "cartagena", "bucaramanga",
    "pereira", "ibague", "santa marta", "armenia", "manizales", "villavicencio",
    "soacha", "zipaquira", "cajica", "cota", "funza", "madrid", "mosquera",
    "chia", "rionegro", "itagui", "soledad", "tunja", "valledupar", "girardot",
    "neiva",
]
CIUDADES_MEXICO = [
    "ciudad de mexico", "guadalajara", "monterrey", "queretaro", "puebla",
    "tijuana", "chihuahua", "culiacan", "leon", "saltillo", "tampico",
    "reynosa", "nuevo laredo", "cuautitlan izcalli",
]


# Precio vigente de las membresías en 2026 (por país y plan).
# Se usa solo cuando la fila no trae la columna "Saldo minimo".
PRECIOS_2026 = {
    ("Colombia", "basico"): 44900,
    ("Colombia", "blue"): 64900,
}


def precio_plan(pais, plan):
    return PRECIOS_2026.get((pais, normalizar_plan(plan)))


def fecha_desde_nombre(nombre_archivo):
    """'20260827_Lista_Oro...xlsx' -> 27/08/2026. Si no hay fecha al inicio, None."""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", nombre_archivo or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def normalizar(valor):
    """Minúsculas, sin tildes, sin guiones bajos y sin espacios dobles."""
    if valor is None:
        return ""
    s = unicodedata.normalize("NFD", str(valor))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace("_", " ")
    return re.sub(r"\s+", " ", s).strip()


def es_vacio(v):
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    return isinstance(v, str) and v.strip() == ""


def a_texto(v):
    if es_vacio(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if s.startswith("#"):          # #REF!, #VALUE!, #N/A...
        return None
    return s


def a_numero(v):
    if es_vacio(v) or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace("$", "").replace(" ", "")
    if not s or s.startswith("#"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def a_fecha(v):
    if es_vacio(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:   # fecha "número" de Excel
        return date(1899, 12, 30) + timedelta(days=int(v))
    s = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):          # formato 2026-09-01...
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    try:
        f = pd.to_datetime(s, dayfirst=True, errors="coerce")
        return None if pd.isna(f) else f.date()
    except Exception:
        return None


def limpiar_id(v):
    """Deja cédulas, CURP e IDs siempre como texto, sin '.0' ni espacios."""
    s = a_texto(v)
    if s is None:
        return None
    s = re.sub(r"\s+", "", s).upper()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s or None


def pais_final(ciudad, pais):
    """Igual que el HTML: primero deduce el país por la ciudad, luego por la columna País."""
    c = normalizar(ciudad)
    if c:
        if any(m in c for m in CIUDADES_MEXICO):
            return "México"
        if any(m in c for m in CIUDADES_COLOMBIA):
            return "Colombia"
    p = normalizar(pais)
    if "colomb" in p or p in ("co", "col"):
        return "Colombia"
    if "mexic" in p or p in ("mx", "mex"):
        return "México"
    return "Sin país (revisar dato)"


def estado_retiro_canonico(v):
    n = normalizar(v)
    if not n:
        return None
    if "bloque" in n:
        return "Aliado bloqueado"
    if "fondos insuficientes" in n:
        return "Fondos insuficientes"
    if "aprobado" in n:
        return "Retiro Aprobado"
    if n == "pagoya":
        return "Pagoya"
    return str(v).strip()


def estado_aliado_canonico(v):
    n = normalizar(v)
    if n.startswith("activ"):
        return "activo"
    if "bloque" in n:
        return "bloqueado"
    return None


def clave_semana(d: date) -> str:
    anio, semana, _ = d.isocalendar()
    return f"{anio}-W{semana:02d}"


def lunes_de_semana(clave: str) -> date:
    anio, semana = clave.split("-W")
    return date.fromisocalendar(int(anio), int(semana), 1)


def etiqueta_semana(clave: str) -> str:
    lunes = lunes_de_semana(clave)
    domingo = lunes + timedelta(days=6)
    num = clave.split("-W")[1]
    return (f"Semana {num} · {lunes.day} {MESES_CORTOS[lunes.month - 1]} – "
            f"{domingo.day} {MESES_CORTOS[domingo.month - 1]} {domingo.year}")


# ----------------------------------------------------------------------
# Búsqueda de hojas y columnas
# ----------------------------------------------------------------------

def _abrir(contenido: bytes):
    try:
        return CalamineWorkbook.from_filelike(io.BytesIO(contenido))
    except Exception as e:
        raise ErrorLectura(
            f"No pude abrir el archivo como Excel (.xlsx). Detalle: {e}") from e


def _buscar_hoja(wb, condicion, preferidas=(), excluir=()):
    """Devuelve (nombre_hoja, fila_encabezado) de la primera hoja que cumpla la condición."""
    nombres = list(wb.sheet_names)
    orden = sorted(nombres, key=lambda n: 0 if any(p in normalizar(n) for p in preferidas) else 1)
    for nombre in orden:
        if any(x in normalizar(nombre) for x in excluir):
            continue
        try:
            filas = wb.get_sheet_by_name(nombre).to_python(nrows=5)
        except Exception:
            continue
        for i, fila in enumerate(filas[:5]):
            encabezado = [normalizar(c) for c in fila]
            if condicion(encabezado):
                return nombre, i
    return None, None


def _leer_hoja(wb, nombre, fila_encabezado):
    """Devuelve el encabezado y un recorrido fila por fila (ahorra memoria en archivos grandes)."""
    hoja = wb.get_sheet_by_name(nombre)
    filas = hoja.iter_rows()
    for _ in range(fila_encabezado):
        next(filas, None)
    encabezado = [normalizar(c) for c in next(filas, [])]
    datos = (f for f in filas if not all(es_vacio(c) for c in f))
    return encabezado, datos


def _col_exacta(enc, nombre):
    return enc.index(nombre) if nombre in enc else -1


def _col_contiene(enc, texto, excluir=None):
    for i, h in enumerate(enc):
        if texto in h and not (excluir and excluir in h):
            return i
    return -1


def _valor(fila, i):
    return fila[i] if 0 <= i < len(fila) else None


def _exigir(idx, obligatorias, nombre_archivo, hoja):
    faltan = [nombre for clave, nombre in obligatorias.items() if idx[clave] < 0]
    if faltan:
        raise ErrorLectura(
            f"En el archivo de {nombre_archivo} (hoja '{hoja}') no encontré estas columnas: "
            + ", ".join(faltan)
            + ". Revisa que el encabezado no haya cambiado de nombre.")


# ----------------------------------------------------------------------
# 1. MEMBRESÍAS (Lista Oro)
# ----------------------------------------------------------------------

def normalizar_plan(p):
    n = normalizar(p).replace("plan", "").strip()
    winback = "winback" in n
    if "basic" in n:
        n = "basico"
    elif "blue" in n:
        n = "blue"
    return "winback blue" if (winback and n == "blue") else n


def leer_membresias(contenido: bytes) -> Resultado:
    wb = _abrir(contenido)
    hoja, fila = _buscar_hoja(wb, lambda h: any("tipo membresia" in x for x in h),
                              preferidas=["lista oro"])
    if hoja is None:
        raise ErrorLectura(
            "No encontré una hoja con la estructura de Membresías (Lista Oro). "
            "Busco una hoja cuyo encabezado tenga la columna 'Tipo membresia'.")
    enc, datos = _leer_hoja(wb, hoja, fila)
    idx = {
        "nombre": _col_exacta(enc, "nombre"),
        "ident": _col_exacta(enc, "identificacion"),
        "plan": _col_contiene(enc, "tipo de plan"),
        "saldo_min": _col_contiene(enc, "saldo minimo"),
        "saldo": _col_contiene(enc, "saldo actual"),
        "disp": _col_contiene(enc, "disponible para retiro"),
        "ciudad": _col_exacta(enc, "ciudad"),
        "pais": _col_exacta(enc, "pais"),
        "fecha": _col_contiene(enc, "fecha deposito"),
        "est_ret": _col_contiene(enc, "estado retiro"),
        "est_ali": _col_contiene(enc, "estado aliado"),
        "mem_act": _col_contiene(enc, "membresia activa"),
    }
    _exigir(idx, {"ident": "identificacion", "plan": "Tipo de plan",
                  "est_ret": "estado retiro"}, "Membresías", hoja)

    avisos = []
    hoy = date.today()
    sin_fecha = 0
    registros = []
    for f in datos:
        ident = limpiar_id(_valor(f, idx["ident"]))
        nombre = a_texto(_valor(f, idx["nombre"]))
        if ident is None and nombre is None:
            continue
        fecha = a_fecha(_valor(f, idx["fecha"]))
        if fecha is None:
            sin_fecha += 1
        ciudad = a_texto(_valor(f, idx["ciudad"]))
        pais = pais_final(ciudad, _valor(f, idx["pais"]))
        plan = a_texto(_valor(f, idx["plan"]))
        valor_plan = a_numero(_valor(f, idx["saldo_min"]))
        registros.append({
            "semana": clave_semana(fecha or hoy),
            "fecha_deposito": fecha,
            "nombre": nombre,
            "identificacion": ident,
            "tipo_plan": plan,
            "valor_plan": valor_plan if valor_plan else precio_plan(pais, plan),
            "saldo_actual": a_numero(_valor(f, idx["saldo"])),
            "disponible": a_numero(_valor(f, idx["disp"])),
            "ciudad": ciudad,
            "pais": pais,
            "estado_retiro": estado_retiro_canonico(_valor(f, idx["est_ret"])),
            "estado_aliado": estado_aliado_canonico(_valor(f, idx["est_ali"])),
            "membresia_activa": a_texto(_valor(f, idx["mem_act"])),
        })
    if not registros:
        raise ErrorLectura(f"La hoja '{hoja}' de Membresías no tiene filas con datos.")
    tabla = pd.DataFrame(registros)
    fechas = tabla["fecha_deposito"].dropna()
    fecha_columna = fechas.mode().iloc[0] if not fechas.empty else None
    return Resultado(tabla, avisos, {"hoja": hoja, "fecha_columna": fecha_columna,
                                     "filas_sin_fecha": sin_fecha})


def asignar_fecha_deposito(tabla: pd.DataFrame, fecha: date) -> pd.DataFrame:
    """Cada Lista Oro es un depósito semanal: todas sus filas quedan con la fecha elegida."""
    return tabla.assign(fecha_deposito=fecha, semana=clave_semana(fecha))


# ----------------------------------------------------------------------
# 2. PAGOYA (hoja Validación)
# ----------------------------------------------------------------------

def leer_pagoya(contenido: bytes) -> Resultado:
    wb = _abrir(contenido)
    hoja, fila = _buscar_hoja(
        wb,
        lambda h: any("comision pago ya" in x for x in h) or "id retiro" in h,
        preferidas=["validacion"],
        excluir=["duplicad"],
    )
    if hoja is None:
        raise ErrorLectura(
            "No encontré la hoja de PagoYa. Busco una hoja (normalmente 'Validación') "
            "con la columna 'Comisión Pago Ya' o 'id_retiro'.")
    enc, datos = _leer_hoja(wb, hoja, fila)
    comision = _col_contiene(enc, "comision pago ya")
    if comision < 0:
        comision = _col_contiene(enc, "comision", excluir="%")
    idx = {
        "id_retiro": _col_exacta(enc, "id retiro"),
        "nombre": _col_exacta(enc, "nombre"),
        "ident": _col_exacta(enc, "identificacion"),
        "ciudad": _col_exacta(enc, "ciudad"),
        "pais": _col_exacta(enc, "pais"),
        "fecha": _col_exacta(enc, "fecha"),
        "fecha_val": _col_contiene(enc, "fecha validacion"),
        "vehiculo": _col_exacta(enc, "vehiculo"),
        "valor": _col_exacta(enc, "valor"),
        "comision": comision,
        "iva": _col_exacta(enc, "iva"),
        "estado": _col_exacta(enc, "estado"),
        "gps": _col_contiene(enc, "gps falso"),
        "bl": _col_contiene(enc, "black list"),
        "canc": _col_contiene(enc, "cancelacion"),
        "pago_parcial": _col_exacta(enc, "pago parcial"),
        "pagar": _col_exacta(enc, "pagar"),
        "est_ali": _col_contiene(enc, "estado aliado"),
    }
    _exigir(idx, {"ident": "identificacion", "valor": "valor",
                  "fecha": "fecha"}, "PagoYa", hoja)

    avisos = []
    hoy = date.today()
    sin_fecha = 0
    registros = []
    for f in datos:
        valor = a_numero(_valor(f, idx["valor"]))
        if valor is None:
            continue
        fecha = a_fecha(_valor(f, idx["fecha"]))
        fecha_val = a_fecha(_valor(f, idx["fecha_val"]))
        fecha_semana = fecha_val or fecha
        if fecha_semana is None:
            sin_fecha += 1
        canc = a_numero(_valor(f, idx["canc"]))
        if canc is not None and canc > 1:
            canc = canc / 100
        pagar = normalizar(_valor(f, idx["pagar"]))
        ciudad = a_texto(_valor(f, idx["ciudad"]))
        registros.append({
            "semana": clave_semana(fecha_semana or hoy),
            "id_retiro": limpiar_id(_valor(f, idx["id_retiro"])),
            "nombre": a_texto(_valor(f, idx["nombre"])),
            "identificacion": limpiar_id(_valor(f, idx["ident"])),
            "ciudad": ciudad,
            "pais": pais_final(ciudad, _valor(f, idx["pais"])),
            "fecha": fecha,
            "fecha_validacion": fecha_val,
            "vehiculo": a_texto(_valor(f, idx["vehiculo"])),
            "valor": valor,
            "comision": a_numero(_valor(f, idx["comision"])),
            "iva": a_numero(_valor(f, idx["iva"])),
            "estado": a_texto(_valor(f, idx["estado"])),
            "gps_falso": a_numero(_valor(f, idx["gps"])),
            "black_list": (a_texto(_valor(f, idx["bl"])) or "").upper() or None,
            "cancelacion": canc,
            "pago_parcial": a_numero(_valor(f, idx["pago_parcial"])),
            "pagar": None if not pagar else ("SI" if pagar in ("si", "ok") else "NO"),
            "estado_aliado": estado_aliado_canonico(_valor(f, idx["est_ali"])),
        })
    if not registros:
        raise ErrorLectura(f"La hoja '{hoja}' de PagoYa no tiene filas con valor.")
    tabla = pd.DataFrame(registros)
    # Si el mismo id_retiro aparece dos veces en el archivo, queda la última fila.
    con_id = tabla["id_retiro"].notna()
    repetidos = tabla[con_id].duplicated("id_retiro", keep="last")
    if repetidos.any():
        avisos.append(f"{int(repetidos.sum())} filas tenían un id_retiro repetido dentro del archivo; dejé una sola.")
        tabla = pd.concat([tabla[con_id][~repetidos], tabla[~con_id]], ignore_index=True)
    if sin_fecha:
        avisos.append(f"{sin_fecha} filas no tienen fecha; las asigné a la semana actual.")
    return Resultado(tabla, avisos, {"hoja": hoja})


# ----------------------------------------------------------------------
# 3. SALDOS DE ALIADOS
# ----------------------------------------------------------------------

def leer_saldos(contenido: bytes, fecha_corte: date) -> Resultado:
    wb = _abrir(contenido)

    def es_saldos(h):
        tiene_id = any("identificacion" in x for x in h) or "did" in h or "id users" in h
        tiene_saldo = (any(("saldo" in x or "acumulado" in x or "cupo" in x or "monto total" in x
                            or "disponible" in x) for x in h) or "total" in h)
        return tiene_id and tiene_saldo

    hoja, fila = _buscar_hoja(wb, es_saldos)
    if hoja is None:
        raise ErrorLectura(
            "No encontré una hoja de Saldos. Busco columnas de identificación "
            "('identificacion', 'did' o 'id_users') y de saldo ('Saldo', 'cupo' o 'total').")
    enc, datos = _leer_hoja(wb, hoja, fila)

    ident = _col_contiene(enc, "identificacion")
    if ident < 0:
        ident = _col_exacta(enc, "did")
    if ident < 0:
        ident = _col_exacta(enc, "id users")
    # Cómo se calcula el saldo, en orden de preferencia:
    #  1) columna "total" (viene en centavos -> se divide entre 100)
    #  2) columna "Saldo"
    #  3) Acumulado - AcumuladoNR (formato actual del archivo de saldos)
    #  4) columna "cupo", "monto total" o "disponible"
    usa_total = _col_exacta(enc, "total") >= 0
    col_acum = _col_exacta(enc, "acumulado")
    col_acum_nr = _col_exacta(enc, "acumuladonr")
    if col_acum_nr < 0:
        col_acum_nr = _col_exacta(enc, "acumulado nr")
    usa_acumulado = False
    col_saldo = _col_exacta(enc, "total") if usa_total else _col_contiene(enc, "saldo")
    if col_saldo < 0 and col_acum >= 0:
        usa_acumulado = True
    elif col_saldo < 0:
        for palabra in ("cupo", "monto total", "disponible"):
            col_saldo = _col_contiene(enc, palabra)
            if col_saldo >= 0:
                break
    if col_saldo < 0 and not usa_acumulado:
        raise ErrorLectura(f"En la hoja '{hoja}' de Saldos no encontré con qué calcular el saldo.")
    idx = {
        "ident": ident,
        "nombre": _col_exacta(enc, "nombre"),
        "ciudad": _col_exacta(enc, "ciudad"),
        "pais": _col_exacta(enc, "pais"),
        "saldo": col_saldo,
    }
    avisos = []
    if usa_total:
        avisos.append("El archivo trae la columna 'total', que viene en centavos: la dividí entre 100.")
    if usa_acumulado:
        avisos.append("Saldo calculado como Acumulado − AcumuladoNR.")

    semana = clave_semana(fecha_corte)
    registros = []
    sin_ident = 0
    for f in datos:
        if usa_acumulado:
            saldo = ((a_numero(_valor(f, col_acum)) or 0.0)
                     - (a_numero(_valor(f, col_acum_nr)) or 0.0))
        else:
            saldo = a_numero(_valor(f, idx["saldo"])) or 0.0
        saldo = round(saldo, 2)
        if not saldo:
            continue            # igual que el HTML: se omiten saldos en cero o vacíos
        if usa_total:
            saldo = saldo / 100
        ident_v = limpiar_id(_valor(f, idx["ident"]))
        if ident_v is None:
            sin_ident += 1
        ciudad = a_texto(_valor(f, idx["ciudad"]))
        registros.append({
            "fecha_corte": fecha_corte,
            "semana": semana,
            "identificacion": ident_v,
            "nombre": a_texto(_valor(f, idx["nombre"])),
            "ciudad": ciudad,
            "pais": pais_final(ciudad, _valor(f, idx["pais"])),
            "saldo": saldo,
        })
    if not registros:
        raise ErrorLectura(f"La hoja '{hoja}' de Saldos no tiene aliados con saldo distinto de cero.")
    if sin_ident:
        avisos.append(f"{sin_ident} aliados no tienen identificación (did); se guardan, "
                      "pero no se podrán cruzar con PagoYa.")
    return Resultado(pd.DataFrame(registros), avisos, {"hoja": hoja})


# ----------------------------------------------------------------------
# 4. HISTÓRICO DEL TABLERO HTML (se usa una sola vez)
# ----------------------------------------------------------------------

def leer_historico_html(contenido: bytes) -> dict:
    texto = contenido.decode("utf-8", errors="replace")
    marca = "const SEED_DATA = "
    pos = texto.find(marca)
    if pos < 0:
        raise ErrorLectura("Este HTML no trae datos guardados (no encontré 'SEED_DATA').")
    datos, _ = json.JSONDecoder().raw_decode(texto[pos + len(marca):])

    memb = []
    for sem in datos.get("membresiaWeeks", []):
        for r in sem["rows"]:
            ciudad = a_texto(r.get("ciu"))
            pais = pais_final(ciudad, r.get("pais"))
            memb.append({
                "semana": sem["weekKey"], "fecha_deposito": None,
                "nombre": a_texto(r.get("nom")),
                "identificacion": limpiar_id(r.get("ident")),
                "tipo_plan": a_texto(r.get("plan")),
                "valor_plan": precio_plan(pais, r.get("plan")),
                "saldo_actual": a_numero(r.get("saldo")), "disponible": a_numero(r.get("disp")),
                "ciudad": ciudad, "pais": pais,
                "estado_retiro": estado_retiro_canonico(r.get("estRet")),
                "estado_aliado": estado_aliado_canonico(r.get("estAli")),
                "membresia_activa": a_texto(r.get("memAct")),
            })

    pago = []
    for sem in datos.get("pagoyaWeeks", []):
        for r in sem["rows"]:
            ciudad = a_texto(r.get("c"))
            canc = a_numero(r.get("ca"))
            if canc is not None and canc > 1:
                canc = canc / 100
            pg = normalizar(r.get("pg"))
            pago.append({
                "semana": sem["weekKey"], "id_retiro": None,
                "nombre": a_texto(r.get("n")),
                "identificacion": limpiar_id(r.get("d")), "ciudad": ciudad,
                "pais": pais_final(ciudad, r.get("p")),
                "fecha": a_fecha(r.get("f")), "fecha_validacion": None,
                "vehiculo": a_texto(r.get("v")),
                "valor": a_numero(r.get("va")) or 0.0, "comision": a_numero(r.get("co")),
                "iva": a_numero(r.get("iv")), "estado": None,
                "gps_falso": a_numero(r.get("g")),
                "black_list": (a_texto(r.get("b")) or "").upper() or None,
                "cancelacion": canc, "pago_parcial": None,
                "pagar": None if not pg else ("SI" if pg in ("si", "ok") else "NO"),
                "estado_aliado": estado_aliado_canonico(r.get("e")),
            })

    # Los saldos y precios del HTML NO se importan: los saldos venían en centavos
    # y los precios eran de años anteriores.
    return {
        "membresias": pd.DataFrame(memb),
        "pagoya": pd.DataFrame(pago),
    }
