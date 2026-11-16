# -*- coding: utf-8 -*-
"""
RO - Bloque Python Script de DWSIM (IronPython)            v4 (optimizada)
Modelo: solución-difusión + polarización de concentración (película)
        + discretización por elementos en serie + presión osmótica (Pitzer para NaCl).

CAMBIOS RESPECTO A v3
  - Ícono: se carga UNA sola vez (antes se recargaba el bitmap en cada cálculo).
  - Flux por elemento: método de la secante con arranque en caliente (antes punto fijo
    amortiguado, hasta 60 iteraciones). ~4-6 evaluaciones de pi por elemento en vez de ~40.
  - Constantes (rho_agua, A_phi, R*T) calculadas una vez; listas en vez de diccionarios.
  - DISENO_PRESION: falsa posición (Illinois) en vez de bisección.
  - TERMO: P redondeada a 0.1 bar (misma P para mezcla y agua pura) -> la caché sí acierta.
  - Valores por defecto ahora coinciden con este encabezado (antes el código usaba
    DISENO_AREA/VANTHOFF y el encabezado decía SIMULACION/PITZER).
  - Si TERMO falla, el respaldo es Pitzer (antes caía a Van't Hoff aunque el aviso decía Pitzer).
  - Validación de Modo / Metodo_Pi, y de solutos y caudal.
  - El log final reporta tiempo de cálculo y número de evaluaciones de pi.

=============================================================================
VARIABLES DEL PANEL "Scripting Variables"  (crear con el botón "+", SIN espacios)
Si una variable no existe en el panel, el script usa el valor por defecto indicado.
=============================================================================
Input (Text):                                         defecto
  Modo               SIMULACION | DISENO_AREA | DISENO_PRESION     SIMULACION
  Metodo_Pi          PITZER | VANTHOFF | TERMO                      PITZER
  Nom_Alimentacion   etiqueta de la corriente de entrada           F
  Nom_Permeado       etiqueta de la corriente de permeado          P
  Nom_Rechazo        etiqueta de la corriente de rechazo           R
  Ruta_icono         ruta del .jpg/.png del ícono; NONE = sin ícono  (ver RUTA_ICONO_DEF)

Input (Numbers):
  Area_elem          m2 por elemento                                37
  N_elem             elementos en serie por tubo                    7
  N_pv               tubos de presión en paralelo                   10
  A_agua_LMH_bar     permeabilidad al agua [L/(m2 h bar)]           1.0
  SR_nominal         rechazo nominal de sal [%] (hoja técnica)      99.7
  B_sal_m_s          paso de sal [m/s]; 0 = calcular desde SR       0
  Flux_ensayo_LMH    flux de ensayo del fabricante [LMH]            25
  Recovery_obj       recovery objetivo [%] (modos de diseño)        45
  Flux_diseno_LMH    flux de diseño [LMH] (DISENO_AREA)             15
  k_mt               coef. transferencia de masa [m/s]              3e-5
  Beta_fijo          factor de polarización fijo; 0 = calcular      0
  dP_nom_elem_bar    caída de presión por elemento [bar]            0.25
  Q_nom_elem_m3h     caudal por tubo de esa caída [m3/h]            12
  Exp_friccion       exponente dP ~ Q^n                             1.7
  P_permeado_bar     presión del permeado [bar abs]                 1.01325
  P_succion_bar      presión de succión de la bomba [bar abs]       1.01325
  Eficiencia_bomba   fracción (0-1)                                 0.80
  Eficiencia_ERD     recuperador de energía, fracción; 0 = sin ERD  0
  P_max_bar          tope de presión en DISENO_PRESION [bar]        120
  Phi_osm            coef. osmótico (solo VANTHOFF)                 0.93

Output (Numbers):
  Recovery_pct, Flux_medio_LMH, Area_total_m2, N_pv_usado, Rechazo_aparente_pct,
  Beta_medio, Beta_max, Factor_conc, Pi_alimentacion_bar, Pi_membrana_salida_bar,
  Pi_rechazo_bar, Pi_permeado_bar, NDP_salida_bar, dP_canal_bar, P_operacion_bar,
  TDS_permeado_ppm, Conc_rechazo_gL, Caudal_permeado_m3h,
  Potencia_bomba_kW, Potencia_ERD_kW, SEC_neta_kWh_m3
=============================================================================
"""
import math
import os
import time
import clr
clr.AddReference('System')
clr.AddReference('System.Drawing')
from System import Array, Double
from System.Drawing import Bitmap

_T0 = time.time()
RUTA_ICONO_DEF = r"C:\Users\rehe_\Downloads\Bastidor.jpg"

# -----------------------------------------------------------------------------
# 0) ACCESO A LAS VARIABLES DEL PANEL Y UTILIDADES BÁSICAS
# -----------------------------------------------------------------------------
try:
    _uo = Me
except NameError:
    try:
        _uo = this
    except NameError:
        _uo = None


def _var(nombre):
    try:
        return globals()[nombre]
    except KeyError:
        pass
    if _uo is not None:
        for tabla in ("InputVariables", "InputStringVariables"):
            try:
                return getattr(_uo, tabla)[nombre]
            except Exception:
                pass
    return None


def _num(nombre, defecto):
    try:
        return float(_var(nombre))
    except Exception:
        return defecto


def _txt(nombre, defecto):
    v = _var(nombre)
    s = "" if v is None else str(v).strip()
    return s if s else defecto


def log(txt):
    try:
        Flowsheet.WriteMessage(txt)
    except Exception:
        try:
            print(txt)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# 0b) ÍCONO DEL BLOQUE (una sola vez: si ya hay imagen cargada no se repite)
# -----------------------------------------------------------------------------
def _icono():
    if _uo is None:
        return
    try:
        if getattr(_uo, "EmbeddedImage", None) is not None:
            return
        ruta = _txt("Ruta_icono", RUTA_ICONO_DEF)
        if ruta.upper() == "NONE":
            return
        if not os.path.isfile(ruta):
            log("Aviso RO_Icon: no existe el archivo " + ruta)
            return
        _uo.UseEmbeddedImage = True
        _uo.EmbeddedImage = Bitmap(ruta)
        _uo.GraphicObject.Width = 100      # tamaño solo al cargar; luego puedes
        _uo.GraphicObject.Height = 50      # redimensionar a mano en el PFD
    except Exception as e:
        log("Aviso RO_Icon: no se pudo cargar el ícono. " + str(e))


_icono()

# -----------------------------------------------------------------------------
# 1) PARÁMETROS
# -----------------------------------------------------------------------------
MODO = _txt("Modo", "SIMULACION").upper()
if MODO not in ("SIMULACION", "DISENO_AREA", "DISENO_PRESION"):
    log("AVISO RO: Modo '%s' no válido; se usa SIMULACION." % MODO)
    MODO = "SIMULACION"
METODO_PI = _txt("Metodo_Pi", "PITZER").upper()
if METODO_PI not in ("PITZER", "VANTHOFF", "TERMO"):
    log("AVISO RO: Metodo_Pi '%s' no válido; se usa PITZER." % METODO_PI)
    METODO_PI = "PITZER"
NOM_F = _txt("Nom_Alimentacion", "F")
NOM_P = _txt("Nom_Permeado", "P")
NOM_R = _txt("Nom_Rechazo", "R")

AREA_ELEM  = _num("Area_elem", 37.0)
N_ELEM     = max(int(round(_num("N_elem", 7))), 1)
N_PV       = max(int(round(_num("N_pv", 10))), 1)
A_WATER    = _num("A_agua_LMH_bar", 1.0) / 3.6e6          # m/(s*bar)
SR_DEF     = _num("SR_nominal", 99.7)
B_SAL      = _num("B_sal_m_s", 0.0)
JW_ENS     = _num("Flux_ensayo_LMH", 25.0) / 3.6e6        # m/s
REC_OBJ    = _num("Recovery_obj", 45.0) / 100.0
FLUX_DIS   = _num("Flux_diseno_LMH", 15.0) / 3.6e6        # m/s
K_MT       = _num("k_mt", 3.0e-5)
BETA_FIJO  = _num("Beta_fijo", 0.0)
DP_NOM     = _num("dP_nom_elem_bar", 0.25)
Q_NOM      = _num("Q_nom_elem_m3h", 12.0)
EXP_F      = _num("Exp_friccion", 1.7)
P_PERM_BAR = _num("P_permeado_bar", 1.01325)
P_SUC_BAR  = _num("P_succion_bar", 1.01325)
ETA_B      = max(_num("Eficiencia_bomba", 0.80), 0.05)
ETA_ERD    = _num("Eficiencia_ERD", 0.0)
P_MAX_BAR  = _num("P_max_bar", 120.0)
PHI_OSM    = _num("Phi_osm", 0.93)

TOL_JW = 1.0e-6          # tolerancia relativa del flux en cada elemento
R_GAS = 8.314462618
NU_DEF = 1.0
ALIAS_AGUA = ["WATER", "AGUA", "H2O", "7732-18-5"]
SOLUTOS = [
    {"alias": ["NACL", "SODIUM CHLORIDE", "CLORURO DE SODIO", "7647-14-5"],
     "nu": 2.0, "pitzer": True},
    # {"alias": ["KCL", "7447-40-7"], "nu": 2.0, "pitzer": False},
]

# -----------------------------------------------------------------------------
# 2) CORRIENTES Y COMPUESTOS
# -----------------------------------------------------------------------------
def rho_agua(T):
    t = T - 273.15
    return (999.83952 + 16.945176*t - 7.9870401e-3*t**2 - 46.170461e-6*t**3
            + 105.56302e-9*t**4 - 280.54253e-12*t**5) / (1.0 + 16.897850e-3*t)


ms_f = Flowsheet.GetFlowsheetSimulationObject(NOM_F)
ms_p = Flowsheet.GetFlowsheetSimulationObject(NOM_P)
ms_r = Flowsheet.GetFlowsheetSimulationObject(NOM_R)

T = ms_f.GetTemperature()
Pf = ms_f.GetPressure()                       # Pa
m_total_f = ms_f.GetMassFlow()
if not (m_total_f > 0):
    raise Exception("RO: el caudal másico de la alimentación es cero.")

comps = ms_f.Phases[0].Compounds
nombres = [k for k in comps.Keys]


def _tokens(nombre):
    t = set([nombre.upper()])
    cp = comps[nombre].ConstantProperties
    for attr in ("CAS_Number", "Formula"):
        try:
            v = getattr(cp, attr)
            if v:
                t.add(str(v).strip().upper())
        except Exception:
            pass
    return t


_R_SR = min(max(SR_DEF, 1.0), 99.99) / 100.0
_B_DESDE_SR = JW_ENS * (1.0 - _R_SR) / _R_SR          # R = Jw/(Jw+B)

MW = {}
idx_agua = None
MW_w = w_w = None
sol_names, idx_sol, MW_s, nu_s, pitz_s, w_s, B_s = [], [], [], [], [], [], []
for i, n in enumerate(nombres):
    MW[n] = comps[n].ConstantProperties.Molar_Weight          # kg/kmol
    tk = _tokens(n)
    if any(a in tk for a in ALIAS_AGUA):
        idx_agua, MW_w, w_w = n, MW[n], comps[n].MassFraction
        continue
    nu, pz = NU_DEF, False
    for s in SOLUTOS:
        if any(a in tk for a in s["alias"]):
            nu, pz = s["nu"], s["pitzer"]
            break
    sol_names.append(n)
    idx_sol.append(i)
    MW_s.append(MW[n])
    nu_s.append(nu)
    pitz_s.append(pz)
    w_s.append(comps[n].MassFraction)
    B_s.append(B_SAL if B_SAL > 0 else _B_DESDE_SR)

if idx_agua is None:
    raise Exception("No se encontró el agua en los compuestos. Revisa ALIAS_AGUA.")
ns = len(sol_names)
if ns == 0 or sum(w_s) <= 0:
    raise Exception("RO: la alimentación no contiene solutos.")
iw = nombres.index(idx_agua)

rho_w = rho_agua(T)
rho_mez = ms_f.Phases[0].Properties.density
try:
    rho_mez = float(rho_mez) if rho_mez and rho_mez > 0 else rho_w
except Exception:
    rho_mez = rho_w
inv_rho = 1.0 / rho_mez

# Constantes que dependen solo de T (antes se recalculaban en cada llamada a pi)
RT = R_GAS * T
RHO_W_RT = rho_w * RT
APHI = 0.3915 + 0.00067 * (T - 298.15)

# -----------------------------------------------------------------------------
# 3) PRESIÓN OSMÓTICA
#    tipo de phi por soluto: 0 = ideal, 1 = Pitzer NaCl, 2 = constante (Phi_osm)
# -----------------------------------------------------------------------------
_N_PI = [0]
_cache_pura = {}
_termo_ok = [METODO_PI == "TERMO"]
STATE_LIQ = None
pp = None
if METODO_PI == "TERMO":
    try:
        pp = ms_f.PropertyPackage
        try:
            clr.AddReference('DWSIM.Thermodynamics')
            from DWSIM.Thermodynamics.PropertyPackages import State as _St
            STATE_LIQ = _St.Liquid
        except Exception:
            from DWSIM.Interfaces.Enums import State as _St
            STATE_LIQ = _St.Liquid
    except Exception:
        _termo_ok[0] = False

_kind = [0] * ns


def _set_kinds(metodo):
    for i in range(ns):
        if metodo == "VANTHOFF":
            _kind[i] = 2
        else:                                   # PITZER (y respaldo de TERMO)
            _kind[i] = 1 if pitz_s[i] else 0


_set_kinds("VANTHOFF" if METODO_PI == "VANTHOFF" else "PITZER")


def phi_nacl(m):
    if m > 6.0:
        m = 6.0
    elif m < 0.0:
        m = 0.0
    a = APHI              # A_phi(T), aprox. lineal
    sm = math.sqrt(m)
    return (1.0 - a * sm / (1.0 + 1.2 * sm)
            + m * (0.0765 + 0.2664 * math.exp(-2.0 * sm)) + 0.00127 * m * m)


def pi_mol(C):
    """Presión osmótica [Pa] desde concentraciones C (lista, kg/m3) con phi molal."""
    ws = []
    tot = 0.0
    for c in C:
        w = c * inv_rho
        if w > 0.5:
            w = 0.5
        ws.append(w)
        tot += w
    if tot <= 0.0:
        return 0.0
    ww = max(1.0 - tot, 1.0e-6)
    osm = 0.0
    for i in range(ns):
        m = 1000.0 * ws[i] / (MW_s[i] * ww)              # mol/kg de agua
        k = _kind[i]
        if k == 1:
            phi = phi_nacl(m)
        elif k == 2:
            phi = PHI_OSM
        else:
            phi = 1.0
        osm += phi * nu_s[i] * m
    return osm * RHO_W_RT


def pi_termo(C, P_pa):
    """a_w del paquete termodinámico. P redondeada a 0.1 bar, igual para mezcla y agua pura."""
    P_pa = round(P_pa, -4)
    ws = [min(c * inv_rho, 0.5) for c in C]
    w_agua = 1.0 - sum(ws)
    n_w = w_agua / MW_w
    nmol = [ws[j] / MW_s[j] for j in range(ns)]
    nt = n_w + sum(nmol)
    x = [0.0] * len(nombres)
    x[iw] = n_w / nt
    for j in range(ns):
        x[idx_sol[j]] = nmol[j] / nt
    phi_mix = pp.DW_CalcFugCoeff(Array[Double](x), T, P_pa, STATE_LIQ)
    if P_pa not in _cache_pura:
        xp = [0.0] * len(nombres)
        xp[iw] = 1.0
        _cache_pura[P_pa] = pp.DW_CalcFugCoeff(Array[Double](xp), T, P_pa, STATE_LIQ)[iw]
    aw = x[iw] * phi_mix[iw] / _cache_pura[P_pa]
    Vw = MW_w / 1000.0 / rho_w
    return -RT * math.log(aw) / Vw


def pi_osm(C, P_pa):
    _N_PI[0] += 1
    if _termo_ok[0]:
        if not any(c > 1e-12 for c in C):
            return 0.0
        try:
            v = pi_termo(C, P_pa)
            if v == v and v > 0:
                return v
        except Exception:
            pass
        _termo_ok[0] = False
        _set_kinds("PITZER")
        log("AVISO RO: TERMO no dio a_w válida; se usa Pitzer.")
    return pi_mol(C)


# -----------------------------------------------------------------------------
# 4) MODELO DE UN TUBO DE PRESIÓN
# -----------------------------------------------------------------------------
def film(Jw, Cb, P_pa):
    """Película de polarización para un flux dado. Devuelve (beta, Cm, Cp, dPi_bar, pi_m_Pa)."""
    beta = BETA_FIJO if BETA_FIJO > 0 else math.exp(min(Jw / K_MT, 5.0))
    Cm = [beta * c for c in Cb]
    Cp = [B * c / max(Jw + B, 1e-30) for B, c in zip(B_s, Cm)]
    pim = pi_osm(Cm, P_pa)
    return beta, Cm, Cp, (pim - pi_osm(Cp, P_pa)) / 1e5, pim


def resolver_flux(dP_hid, Cb, P_pa, x0):
    """Resuelve Jw = A*(dP - dPi(Jw)) por secante acotada en [0, A*dP].
    g(0) = A*dP > 0 y g(A*dP) = -A*dPi <= 0, así que la raíz siempre está acotada."""
    if dP_hid <= 0.0:
        return (0.0,) + film(0.0, Cb, P_pa)
    hi = A_WATER * dP_hid
    a = min(max(x0, 1e-6 * hi), hi)
    sa = film(a, Cb, P_pa)
    ga = A_WATER * (dP_hid - sa[3]) - a
    b = min(max(a + ga, 0.0), hi)
    if b == a:
        return (a,) + sa
    sb = film(b, Cb, P_pa)
    gb = A_WATER * (dP_hid - sb[3]) - b
    for _ in range(30):
        if abs(gb) <= TOL_JW * max(b, 1e-12):
            break
        den = gb - ga
        if den == 0.0:
            break
        c = min(max(b - gb * (b - a) / den, 0.0), hi)
        if c == b:
            break
        a, ga = b, gb
        b = c
        sb = film(b, Cb, P_pa)
        gb = A_WATER * (dP_hid - sb[3]) - b
    return (b,) + sb


def correr_tubo(P_in_bar, m_w0, ms0):
    m_w = m_w0
    m_s = list(ms0)
    perm_w = 0.0
    perm_s = [0.0] * ns
    P_bar = P_in_bar
    flux_sum = beta_sum = beta_max = 0.0
    x0 = None
    for e in range(N_ELEM):
        m_tot = m_w + sum(m_s)
        Q = m_tot * inv_rho
        dP_fric = DP_NOM * (Q * 3600.0 / Q_NOM) ** EXP_F
        dP_hid = P_bar - 0.5 * dP_fric - P_PERM_BAR
        P_pa = P_bar * 1e5
        Cb = [x / Q for x in m_s]
        if x0 is None:
            x0 = A_WATER * max(dP_hid - pi_osm(Cb, P_pa) / 1e5, 0.0)
        Jw, beta, Cm, Cp, dPi, pim = resolver_flux(dP_hid, Cb, P_pa, x0)
        x0 = Jw                                    # arranque en caliente del siguiente elemento

        dm_w = min(Jw * AREA_ELEM * rho_w, 0.95 * m_w)
        m_w -= dm_w
        perm_w += dm_w
        for i in range(ns):
            dm = min(B_s[i] * (Cm[i] - Cp[i]) * AREA_ELEM, 0.95 * m_s[i])
            m_s[i] -= dm
            perm_s[i] += dm
        P_bar -= dP_fric
        flux_sum += Jw
        beta_sum += beta
        if beta > beta_max:
            beta_max = beta
    return {"m_w": m_w, "m_s": m_s, "perm_w": perm_w, "perm_s": perm_s,
            "P_out_bar": P_bar, "flux": flux_sum / N_ELEM,
            "beta_medio": beta_sum / N_ELEM, "beta_max": beta_max,
            "ndp": dP_hid - dPi, "pim": pim / 1e5}


def simular(P_bar, npv):
    k = 1.0 / npv
    r = correr_tubo(P_bar, m_total_f * w_w * k, [m_total_f * w * k for w in w_s])
    r["rec"] = (r["perm_w"] + sum(r["perm_s"])) * npv / m_total_f
    return r


# -----------------------------------------------------------------------------
# 5) MODO DE ESPECIFICACIÓN
# -----------------------------------------------------------------------------
npv = N_PV
P_op_bar = Pf / 1e5

if MODO == "DISENO_AREA":
    area_req = REC_OBJ * m_total_f / (FLUX_DIS * rho_w)
    npv = max(int(math.ceil(area_req / (AREA_ELEM * N_ELEM))), 1)
    log("RO | DISENO_AREA: area requerida = %.1f m2 -> N_pv = %d" % (area_req, npv))

elif MODO == "DISENO_PRESION":
    Cf = [w * rho_mez for w in w_s]
    lo = pi_osm(Cf, Pf) / 1e5 + P_PERM_BAR
    hi = P_MAX_BAR
    f_hi = simular(hi, npv)["rec"] - REC_OBJ
    if f_hi < 0:
        log("AVISO RO: con %.0f bar no se alcanza el recovery objetivo; se usa el máximo." % hi)
        P_op_bar = hi
    else:
        f_lo = simular(lo, npv)["rec"] - REC_OBJ
        if f_lo >= 0:
            P_op_bar = lo
        else:                                        # falsa posición de Illinois
            side = 0
            c = hi
            for it in range(40):
                c = (lo * f_hi - hi * f_lo) / (f_hi - f_lo)
                f_c = simular(c, npv)["rec"] - REC_OBJ
                if abs(f_c) < 1e-6 or abs(hi - lo) < 0.005:
                    break
                if f_c < 0:
                    lo, f_lo = c, f_c
                    if side == -1:
                        f_hi *= 0.5
                    side = -1
                else:
                    hi, f_hi = c, f_c
                    if side == 1:
                        f_lo *= 0.5
                    side = 1
            P_op_bar = c
    log("RO | DISENO_PRESION: presión de alimentación requerida = %.2f bar "
        "(ajusta la bomba; Alimentacion no se modifica)" % P_op_bar)

res = simular(P_op_bar, npv)
P_op = P_op_bar * 1e5

# -----------------------------------------------------------------------------
# 6) ESCRITURA DE CORRIENTES DE SALIDA Y FLASH
# -----------------------------------------------------------------------------
def escribir(ms, masas, P_pa):
    total = sum(masas.values())
    mol = dict((n, masas[n] / MW[n]) for n in nombres)
    nt = sum(mol.values())
    cs = ms.Phases[0].Compounds
    for n in nombres:
        c = cs[n]
        c.MassFraction = masas[n] / total
        c.MoleFraction = mol[n] / nt
    try:
        ms.SetMassFlow(total)
    except Exception:
        ms.Phases[0].Properties.massflow = total
    try:
        ms.SetTemperature(T)
    except Exception:
        ms.Phases[0].Properties.temperature = T
    try:
        ms.SetPressure(P_pa)
    except Exception:
        ms.Phases[0].Properties.pressure = P_pa
    try:
        ms.Calculate()
    except Exception:
        ms.Calculate(True, True)


d_perm = {idx_agua: res["perm_w"] * npv}
d_rech = {idx_agua: res["m_w"] * npv}
for j in range(ns):
    d_perm[sol_names[j]] = res["perm_s"][j] * npv
    d_rech[sol_names[j]] = res["m_s"][j] * npv
for d in (d_perm, d_rech):
    for n in nombres:
        d[n] = max(d[n], 1e-15)

P_out_bar = res["P_out_bar"]
escribir(ms_p, d_perm, P_PERM_BAR * 1e5)
escribir(ms_r, d_rech, P_out_bar * 1e5)

# -----------------------------------------------------------------------------
# 7) RESULTADOS (variables de salida)
# -----------------------------------------------------------------------------
def _dens(ms, defecto):
    try:
        d = ms.Phases[0].Properties.density
        if d is not None and d > 0:
            return float(d)
    except Exception:
        pass
    return defecto


m_p_tot = sum(d_perm.values())
m_r_tot = sum(d_rech.values())
tds_f = sum(w_s)
tds_p = sum(d_perm[n] for n in sol_names) / m_p_tot
tds_r = sum(d_rech[n] for n in sol_names) / m_r_tot
rho_p = _dens(ms_p, rho_w)
rho_r = _dens(ms_r, rho_mez)

C_f = [w * rho_mez for w in w_s]
C_p = [d_perm[n] / m_p_tot * rho_p for n in sol_names]
C_r = [d_rech[n] / m_r_tot * rho_r for n in sol_names]
pi_f = pi_osm(C_f, Pf) / 1e5
pi_p = pi_osm(C_p, P_PERM_BAR * 1e5) / 1e5
pi_r = pi_osm(C_r, P_out_bar * 1e5) / 1e5

Q_f = m_total_f / rho_mez                                   # m3/s
Q_r = m_r_tot / rho_r
Q_p_h = m_p_tot / rho_p * 3600.0                            # m3/h
W_bomba = Q_f * (P_op - P_SUC_BAR * 1e5) / ETA_B / 1000.0   # kW
W_erd = ETA_ERD * Q_r * (P_out_bar - P_PERM_BAR) * 1e5 / 1000.0
sec = (W_bomba - W_erd) / Q_p_h if Q_p_h > 0 else 0.0

SAL = {
    "Recovery_pct": 100.0 * m_p_tot / m_total_f,
    "Flux_medio_LMH": res["flux"] * 3.6e6,
    "Area_total_m2": AREA_ELEM * N_ELEM * npv,
    "N_pv_usado": npv,
    "Rechazo_aparente_pct": 100.0 * (1.0 - tds_p / tds_f),
    "Beta_medio": res["beta_medio"],
    "Beta_max": res["beta_max"],
    "Factor_conc": tds_r / tds_f,
    "Pi_alimentacion_bar": pi_f,
    "Pi_membrana_salida_bar": res["pim"],
    "Pi_rechazo_bar": pi_r,
    "Pi_permeado_bar": pi_p,
    "NDP_salida_bar": res["ndp"],
    "dP_canal_bar": P_op_bar - P_out_bar,
    "P_operacion_bar": P_op_bar,
    "TDS_permeado_ppm": tds_p * 1.0e6,
    "Conc_rechazo_gL": tds_r * rho_r,
    "Caudal_permeado_m3h": Q_p_h,
    "Potencia_bomba_kW": W_bomba,
    "Potencia_ERD_kW": W_erd,
    "SEC_neta_kWh_m3": sec,
}
for k, v in SAL.items():
    globals()[k] = v
    if _uo is not None:
        try:
            _uo.OutputVariables[k] = v
        except Exception:
            pass

log("RO | Modo=%s | Recovery=%.1f %% | Flux=%.1f LMH | Rechazo=%.2f %% | FC=%.2f | "
    "Beta max=%.2f | SEC=%.2f kWh/m3 | t=%.3f s | eval pi=%d"
    % (MODO, SAL["Recovery_pct"], SAL["Flux_medio_LMH"], SAL["Rechazo_aparente_pct"],
       SAL["Factor_conc"], SAL["Beta_max"], SAL["SEC_neta_kWh_m3"],
       time.time() - _T0, _N_PI[0]))

# Chequeos de consistencia termodinámica
if pi_r > P_out_bar - P_PERM_BAR:
    log("AVISO RO: pi del rechazo (%.1f bar) > presión neta de salida (%.1f bar): "
        "recovery inalcanzable a esta presión; revisa Metodo_Pi, el área o la presión."
        % (pi_r, P_out_bar - P_PERM_BAR))
if res["ndp"] <= 0:
    log("AVISO RO: NDP <= 0 en el último elemento (flux nulo al final del tubo).")
