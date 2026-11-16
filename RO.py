# -*- coding: utf-8 -*-
"""
RO - Bloque Python Script de DWSIM (IronPython)                         v5
Modelo: solución-difusión + polarización de concentración (película, con rechazo)
        + elementos en serie (con subdivisión opcional) + presión osmótica (Pitzer NaCl).

MODOS (variable de texto "Modo", escribir SIN ñ ni acentos)
  SIMULACION       equipo existente: usa N_pv, N_elem, Area_elem y la presión de la corriente
                   de alimentación; calcula recovery, flux, beta, TDS del permeado, energía.
  DISENO_AREA      dado Flux_diseno_LMH y Recovery_obj: dimensiona área, elementos y tubos
                   (valor exacto y comercial), calcula la presión requerida y verifica
                   beta <= Beta_limite (con sugerencias si no se cumple).
  DISENO_BLENDING  dado TDS_objetivo_mgL, SR, Flux_diseno_LMH y Recovery_OI: calcula la
                   fracción que pasa por la OI (f_OI) y por bypass, dimensiona SOLO la OI,
                   y reporta recovery global efectivo y beta.
  DISENO_PRESION   con el equipo dado (N_pv), calcula la presión que da Recovery_obj.

CONVENCIONES DE UNIDADES
  Internamente todo en SI (kg, s, m, Pa, K), igual que DWSIM. Las presiones del modelo
  hidráulico se manejan en bar SOLO dentro del modelo (A en m/(s*bar)) y se convierten
  en la frontera: DWSIM -> Pa (se divide entre 1e5), salida -> Pa para las corrientes.
  Variables del panel: las unidades indicadas abajo (LMH, bar, mg/L, m3/h...).

CAMBIOS RESPECTO A v4
  - Película con rechazo finito: Cm = Cb*beta/(1 + r*(beta-1)), r = B/(Jw+B). (v4: Cm = beta*Cb)
  - Volumen de la solución por aditividad (volumen específico parcial del soluto, calculado
    desde la densidad de la alimentación): la concentración ya no usa la densidad fija de
    la alimentación en toda la salmuera.
  - Corrección por temperatura de A y B (TCF, Ks 2640 / 3020 K) y factor de ensuciamiento.
  - Subdivisión de elementos (Subdiv_elem) para reducir el error del esquema explícito.
  - k_mt opcional dependiente del caudal por tubo (Exp_k).
  - Nuevo modo DISENO_BLENDING; DISENO_AREA ahora calcula también la presión requerida y
    valida beta con el modelo riguroso (no solo con una fórmula).
  - Validación de rangos de todas las entradas; protección contra divisiones por cero.
  - Avisos acumulados + variable de salida Estado_OK.

=============================================================================
VARIABLES DEL PANEL "Scripting Variables"  (botón "+", SIN espacios)
Si una variable no existe en el panel, el script usa el valor por defecto.
=============================================================================
Input (Text):                                                       defecto
  Modo               SIMULACION | DISENO_AREA | DISENO_BLENDING
                     | DISENO_PRESION                              SIMULACION
  Metodo_Pi          PITZER | VANTHOFF | TERMO                     PITZER
  Nom_Alimentacion   corriente de entrada                          F
  Nom_Permeado       corriente de permeado de la OI                P
  Nom_Rechazo        corriente de rechazo (salmuera)               R
  Nom_Bypass         (opcional, blending) corriente de bypass      NONE
  Nom_Producto       (opcional, blending) mezcla permeado+bypass   NONE
  Ruta_icono         ruta del .jpg/.png; NONE = sin ícono          (RUTA_ICONO_DEF)

Input (Numbers):
  Area_elem          m2 por elemento                                37
  N_elem             elementos en serie por tubo (1-12)             7
  N_pv               tubos de presión en paralelo (SIMULACION)      10
  A_agua_LMH_bar     permeabilidad al agua a 25 C [L/(m2 h bar)]    1.0
  SR_nominal         rechazo nominal de sal [%] (hoja técnica)      99.7
  B_sal_m_s          paso de sal [m/s]; 0 = calcular desde SR       0
  Flux_ensayo_LMH    flux del ensayo del fabricante [LMH]           25
  Recovery_obj       recovery objetivo [%] (DISENO_AREA/PRESION)    45
  Recovery_OI        recovery del tren de OI [%] (BLENDING)         75
  Flux_diseno_LMH    flux de diseño [LMH] (DISENO_AREA/BLENDING)    15
  TDS_objetivo_mgL   TDS máx. del producto [mg/L] (BLENDING)        500
  k_mt               coef. de transferencia de masa [m/s]           3e-5
  Exp_k              exponente k ~ (Q/Q_nom)^Exp_k; 0 = k fijo      0
  Beta_fijo          beta fijo (Cm/Cb); 0 = calcular                0
  Beta_limite        beta máximo admisible                          1.1
  dP_nom_elem_bar    caída de presión por elemento [bar]            0.25
  Q_nom_elem_m3h     caudal por tubo de esa caída [m3/h]            12
  Exp_friccion       exponente dP ~ Q^n                             1.7
  P_permeado_bar     presión del permeado [bar abs]                 1.01325
  P_succion_bar      presión de succión de la bomba [bar abs]       1.01325
  Eficiencia_bomba   fracción (0-1)                                 0.80
  Eficiencia_ERD     fracción; 0 = sin recuperador                  0
  P_max_bar          tope de presión en los modos de diseño [bar]   120
  Phi_osm            coef. osmótico (solo VANTHOFF)                 0.93
  Subdiv_elem        subdivisiones de cálculo por elemento (1-10)   1
  Factor_ensuciamiento  multiplica A (1 = membrana limpia)          1.0
  Corr_temp          1 = corregir A y B por T respecto a 25 C       1
  Q_alim_max_pv_m3h  aviso si el caudal de alim. por tubo lo supera 0 (apagado)
  Q_rech_min_pv_m3h  aviso si el rechazo por tubo es menor          0 (apagado)

Output (Numbers):
  Recovery_pct, Recovery_global_pct, Flux_medio_LMH, Area_total_m2, Area_exacta_m2,
  N_elem_total, N_elem_exacto, N_pv_usado, N_pv_exacto, f_OI, f_bypass,
  Rechazo_aparente_pct, Rechazo_global_pct, Beta_medio, Beta_max, Beta_ok,
  Flux_max_beta_LMH, Factor_conc, Pi_alimentacion_bar, Pi_membrana_salida_bar,
  Pi_rechazo_bar, Pi_permeado_bar, NDP_salida_bar, dP_canal_bar, P_operacion_bar,
  TDS_permeado_ppm, TDS_producto_mgL, Conc_rechazo_gL, Caudal_alim_OI_m3h,
  Caudal_permeado_m3h, Caudal_bypass_m3h, Caudal_producto_m3h,
  Potencia_bomba_kW, Potencia_ERD_kW, SEC_neta_kWh_m3, Estado_OK,
  Beta_elem_1 ... Beta_elem_12 (opcionales)
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
_AVISOS = []

# -----------------------------------------------------------------------------
# 0) ACCESO A VARIABLES, VALIDACIÓN Y LOG
# -----------------------------------------------------------------------------
try:
    _uo = Me
except NameError:
    try:
        _uo = this
    except NameError:
        _uo = None


def log(txt):
    try:
        Flowsheet.WriteMessage(txt)
    except Exception:
        try:
            print(txt)
        except Exception:
            pass


def aviso(txt):
    """Registra una advertencia (se muestra en consola y baja Estado_OK a 0)."""
    _AVISOS.append(txt)
    log("AVISO RO: " + txt)


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


def _num(nombre, defecto, lo=None, hi=None):
    """Lee una variable numérica; si falta usa el defecto; si es inválida o está fuera de
    [lo, hi] avisa y usa el defecto."""
    v = _var(nombre)
    if v is None:
        return defecto
    try:
        x = float(v)
    except Exception:
        aviso("%s = '%s' no es numérico; se usa %g." % (nombre, v, defecto))
        return defecto
    if x != x or abs(x) == float("inf") or \
            (lo is not None and x < lo) or (hi is not None and x > hi):
        aviso("%s = %g fuera del rango [%s, %s]; se usa %g." % (nombre, x, lo, hi, defecto))
        return defecto
    return x


def _txt(nombre, defecto):
    v = _var(nombre)
    s = "" if v is None else str(v).strip()
    return s if s else defecto


def _salida(nombre, valor):
    globals()[nombre] = valor
    if _uo is not None:
        try:
            _uo.OutputVariables[nombre] = valor
        except Exception:
            pass


# -----------------------------------------------------------------------------
# 0b) ÍCONO DEL BLOQUE (una sola vez)
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
        _uo.GraphicObject.Width = 100
        _uo.GraphicObject.Height = 50
    except Exception as e:
        log("Aviso RO_Icon: no se pudo cargar el ícono. " + str(e))


_icono()

# -----------------------------------------------------------------------------
# 1) PARÁMETROS (con rangos válidos)
# -----------------------------------------------------------------------------
MODO = _txt("Modo", "SIMULACION").upper()
if MODO not in ("SIMULACION", "DISENO_AREA", "DISENO_BLENDING", "DISENO_PRESION"):
    aviso("Modo '%s' no válido; se usa SIMULACION." % MODO)
    MODO = "SIMULACION"
METODO_PI = _txt("Metodo_Pi", "PITZER").upper()
if METODO_PI not in ("PITZER", "VANTHOFF", "TERMO"):
    aviso("Metodo_Pi '%s' no válido; se usa PITZER." % METODO_PI)
    METODO_PI = "PITZER"
NOM_F = _txt("Nom_Alimentacion", "F")
NOM_P = _txt("Nom_Permeado", "P")
NOM_R = _txt("Nom_Rechazo", "R")
NOM_BYP = _txt("Nom_Bypass", "NONE")
NOM_PROD = _txt("Nom_Producto", "NONE")

AREA_ELEM = _num("Area_elem", 37.0, 0.1, 500.0)
N_ELEM = int(round(_num("N_elem", 7, 1, 12)))
N_PV = int(round(_num("N_pv", 10, 1, 100000)))
FF = _num("Factor_ensuciamiento", 1.0, 0.3, 1.0)
CORR_T = _num("Corr_temp", 1, 0, 1) >= 0.5
A_BASE = _num("A_agua_LMH_bar", 1.0, 0.01, 20.0) / 3.6e6      # m/(s*bar) a 25 C
SR_NOM = _num("SR_nominal", 99.7, 50.0, 99.99)
B_SAL = _num("B_sal_m_s", 0.0, 0.0, 1.0e-5)
JW_ENS = _num("Flux_ensayo_LMH", 25.0, 1.0, 100.0) / 3.6e6    # m/s
REC_OBJ = _num("Recovery_obj", 45.0, 1.0, 90.0) / 100.0
REC_OI = _num("Recovery_OI", 75.0, 1.0, 90.0) / 100.0
FLUX_DIS = _num("Flux_diseno_LMH", 15.0, 1.0, 60.0) / 3.6e6   # m/s
C_OBJ = _num("TDS_objetivo_mgL", 500.0, 1.0, 5.0e4)
K_MT = _num("k_mt", 3.0e-5, 1.0e-6, 1.0e-3)
EXP_K = _num("Exp_k", 0.0, 0.0, 1.0)
BETA_FIJO = _num("Beta_fijo", 0.0, 0.0, 3.0)
BETA_LIM = _num("Beta_limite", 1.1, 1.0001, 3.0)
DP_NOM = _num("dP_nom_elem_bar", 0.25, 0.0, 2.0)
Q_NOM = _num("Q_nom_elem_m3h", 12.0, 0.1, 100.0)
EXP_F = _num("Exp_friccion", 1.7, 1.0, 3.0)
P_PERM_BAR = _num("P_permeado_bar", 1.01325, 0.5, 50.0)
P_SUC_BAR = _num("P_succion_bar", 1.01325, 0.1, 50.0)
ETA_B = _num("Eficiencia_bomba", 0.80, 0.1, 1.0)
ETA_ERD = _num("Eficiencia_ERD", 0.0, 0.0, 1.0)
P_MAX_BAR = _num("P_max_bar", 120.0, 1.0, 250.0)
PHI_OSM = _num("Phi_osm", 0.93, 0.5, 1.5)
SUB = int(round(_num("Subdiv_elem", 1, 1, 10)))
Q_ALIM_MAX = _num("Q_alim_max_pv_m3h", 0.0, 0.0, 1000.0)
Q_RECH_MIN = _num("Q_rech_min_pv_m3h", 0.0, 0.0, 1000.0)

TOL_JW = 1.0e-6            # tolerancia relativa del flux en cada paso
R_GAS = 8.314462618
NU_DEF = 1.0
ALIAS_AGUA = ["WATER", "AGUA", "H2O", "7732-18-5"]
SOLUTOS = [
    {"alias": ["NACL", "SODIUM CHLORIDE", "CLORURO DE SODIO", "7647-14-5"],
     "nu": 2.0, "pitzer": True},
    # {"alias": ["KCL", "7447-40-7"], "nu": 2.0, "pitzer": False},
]


# -----------------------------------------------------------------------------
# 2) CORRIENTES, COMPUESTOS Y PROPIEDADES DE LA ALIMENTACIÓN
# -----------------------------------------------------------------------------
def rho_agua(Tk):
    t = Tk - 273.15
    return (999.83952 + 16.945176 * t - 7.9870401e-3 * t ** 2 - 46.170461e-6 * t ** 3
            + 105.56302e-9 * t ** 4 - 280.54253e-12 * t ** 5) / (1.0 + 16.897850e-3 * t)


def _stream(nombre, obligatorio=True):
    if nombre.upper() in ("", "NONE", "NINGUNO"):
        return None
    try:
        s = Flowsheet.GetFlowsheetSimulationObject(nombre)
    except Exception:
        s = None
    if s is None:
        if obligatorio:
            raise Exception("RO: no se encontró la corriente '%s' en el flowsheet." % nombre)
        aviso("no se encontró la corriente opcional '%s'; se omite." % nombre)
    return s


ms_f = _stream(NOM_F)
ms_p = _stream(NOM_P)
ms_r = _stream(NOM_R)
ms_byp = _stream(NOM_BYP, False) if MODO == "DISENO_BLENDING" else None
ms_prod = _stream(NOM_PROD, False) if MODO == "DISENO_BLENDING" else None

T = ms_f.GetTemperature()                      # K
Pf = ms_f.GetPressure()                        # Pa
m_total_f = ms_f.GetMassFlow()                 # kg/s
if not (m_total_f > 0.0):
    raise Exception("RO: el caudal másico de la alimentación es cero o negativo.")
if not (250.0 < T < 400.0):
    raise Exception("RO: temperatura de alimentación fuera de rango (%.1f K)." % T)

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


MW = {}
WF = {}                                         # fracción másica de cada compuesto en la alimentación
nom_agua = None
MW_w = w_w = None
sol_names, idx_sol, MW_s, nu_s, pitz_s, w_s = [], [], [], [], [], []
for i, n in enumerate(nombres):
    MW[n] = comps[n].ConstantProperties.Molar_Weight           # kg/kmol
    WF[n] = max(float(comps[n].MassFraction), 0.0)
    tk = _tokens(n)
    if any(a in tk for a in ALIAS_AGUA):
        nom_agua, MW_w, w_w = n, MW[n], WF[n]
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
    w_s.append(WF[n])

if nom_agua is None:
    raise Exception("RO: no se encontró el agua en los compuestos. Revisa ALIAS_AGUA.")
ns = len(sol_names)
TDS_F = sum(w_s)
if ns == 0 or TDS_F <= 0.0:
    raise Exception("RO: la alimentación no contiene solutos.")
if TDS_F > 0.2:
    aviso("TDS de la alimentación = %.1f %% másico: fuera del rango de validez del modelo."
          % (100.0 * TDS_F))
iw = nombres.index(nom_agua)

RHO_W = rho_agua(T)
try:
    rho_mez = float(ms_f.Phases[0].Properties.density)
    if not (rho_mez > 0.0):
        rho_mez = RHO_W
except Exception:
    rho_mez = RHO_W

# Volumen específico parcial del soluto (m3/kg), derivado de la densidad de la alimentación
V_SOL = (1.0 / rho_mez - w_w / RHO_W) / TDS_F
if not (1.0 / 6000.0 < V_SOL < 1.0e-3):
    V_SOL = 2.8e-4                                # valor típico NaCl (apar. ~3500 kg/m3)
Q_F1 = w_w / RHO_W + V_SOL * TDS_F               # m3 de alimentación por kg
C_F = [w / Q_F1 for w in w_s]                     # kg/m3 de solución

# Constantes dependientes de T
RT = R_GAS * T
RHO_W_RT = RHO_W * RT
APHI = 0.3915 + 0.00067 * (T - 298.15)
TCF_A = math.exp(2640.0 * (1.0 / 298.15 - 1.0 / T)) if CORR_T else 1.0
TCF_B = math.exp(3020.0 * (1.0 / 298.15 - 1.0 / T)) if CORR_T else 1.0
A_WATER = A_BASE * TCF_A * FF                     # m/(s*bar)

_R_SR = SR_NOM / 100.0
_B_DESDE_SR = JW_ENS * (1.0 - _R_SR) / _R_SR      # de R = Jw/(Jw+B)
B_MEM = (B_SAL if B_SAL > 0.0 else _B_DESDE_SR) * TCF_B
B_s = [B_MEM] * ns


# -----------------------------------------------------------------------------
# 3) PRESIÓN OSMÓTICA   (tipo de phi: 0 ideal, 1 Pitzer NaCl, 2 constante)
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
        else:
            _kind[i] = 1 if pitz_s[i] else 0


_set_kinds("VANTHOFF" if METODO_PI == "VANTHOFF" else "PITZER")


def phi_nacl(m):
    """Coeficiente osmótico de Pitzer para NaCl (válido hasta ~6 mol/kg)."""
    if m > 6.0:
        m = 6.0
    elif m < 0.0:
        m = 0.0
    sm = math.sqrt(m)
    return (1.0 - APHI * sm / (1.0 + 1.2 * sm)
            + m * (0.0765 + 0.2664 * math.exp(-2.0 * sm)) + 0.00127 * m * m)


def vol(m_w, m_s):
    """Caudal volumétrico [m3/s] de una corriente de agua + solutos (volumen aditivo)."""
    return m_w / RHO_W + V_SOL * sum(m_s)


def pi_mol(C):
    """Presión osmótica [Pa] desde concentraciones C [kg soluto/m3 solución]."""
    cw = RHO_W * max(1.0 - V_SOL * sum(C), 0.05)        # kg de agua por m3 de solución
    osm = 0.0
    for i in range(ns):
        if C[i] <= 0.0:
            continue
        m = 1000.0 * C[i] / (MW_s[i] * cw)               # mol soluto / kg agua
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
    """pi = -RT ln(a_w)/Vw con a_w del paquete termodinámico. P redondeada a 0.1 bar."""
    P_pa = round(P_pa, -4)
    cw = RHO_W * max(1.0 - V_SOL * sum(C), 0.05)
    n_w = cw / MW_w
    nmol = [C[j] / MW_s[j] for j in range(ns)]
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
    Vw = MW_w / 1000.0 / RHO_W
    return -RT * math.log(aw) / Vw


def pi_osm(C, P_pa):
    _N_PI[0] += 1
    if _termo_ok[0]:
        if not any(c > 1e-12 for c in C):
            return 0.0
        try:
            v = pi_termo(C, P_pa)
            if v == v and v > 0.0:
                return v
        except Exception:
            pass
        _termo_ok[0] = False
        _set_kinds("PITZER")
        aviso("TERMO no dio a_w válida; se usa Pitzer.")
    return pi_mol(C)


# -----------------------------------------------------------------------------
# 4) MODELO DE UN TUBO DE PRESIÓN
# -----------------------------------------------------------------------------
_NOCONV = [0]


def film(Jw, Cb, P_pa, k):
    """Película de polarización con rechazo finito.
    (Cm-Cp)/(Cb-Cp) = exp(Jw/k) y Cp = r*Cm, r = B/(Jw+B)  =>  Cm = Cb*b0/(1 + r*(b0-1)).
    Devuelve (beta_ef = Cm/Cb, Cm, Cp, dPi_bar, pi_membrana_Pa)."""
    b0 = BETA_FIJO if BETA_FIJO > 0.0 else math.exp(min(Jw / k, 5.0))
    Cm, Cp = [], []
    for i in range(ns):
        r = B_s[i] / (Jw + B_s[i])
        cm = b0 * Cb[i] if BETA_FIJO > 0.0 else Cb[i] * b0 / (1.0 + r * (b0 - 1.0))
        Cm.append(cm)
        Cp.append(r * cm)
    sb = sum(Cb)
    beta_ef = sum(Cm) / sb if sb > 0.0 else 1.0
    pim = pi_osm(Cm, P_pa)
    return beta_ef, Cm, Cp, (pim - pi_osm(Cp, P_pa)) / 1e5, pim


def resolver_flux(dP_hid, Cb, P_pa, x0, k):
    """Resuelve Jw = A*(dP - dPi(Jw)) por secante acotada en [0, A*dP].
    g(0) = A*dP > 0 y g(A*dP) <= 0, así que la raíz siempre está acotada."""
    if dP_hid <= 0.0:
        return (0.0,) + film(0.0, Cb, P_pa, k)
    hi = A_WATER * dP_hid
    a = min(max(x0, 1e-6 * hi), hi)
    sa = film(a, Cb, P_pa, k)
    ga = A_WATER * (dP_hid - sa[3]) - a
    b = min(max(a + ga, 0.0), hi)
    if b == a:
        return (a,) + sa
    sb = film(b, Cb, P_pa, k)
    gb = A_WATER * (dP_hid - sb[3]) - b
    ok = abs(gb) <= TOL_JW * max(b, 1e-12)
    for _ in range(30):
        if ok:
            break
        den = gb - ga
        if den == 0.0:
            break
        c = min(max(b - gb * (b - a) / den, 0.0), hi)
        if c == b:
            break
        a, ga = b, gb
        b = c
        sb = film(b, Cb, P_pa, k)
        gb = A_WATER * (dP_hid - sb[3]) - b
        ok = abs(gb) <= TOL_JW * max(b, 1e-12)
    if not ok and abs(gb) > 1e-4 * max(b, 1e-12):
        _NOCONV[0] += 1
    return (b,) + sb


def correr_tubo(P_in_bar, m_w0, ms0, ne):
    """Un tubo de presión con ne elementos (cada uno dividido en SUB pasos)."""
    nst = ne * SUB
    a_step = AREA_ELEM / SUB
    m_w = m_w0
    m_s = list(ms0)
    perm_w = 0.0
    perm_s = [0.0] * ns
    P_bar = P_in_bar
    beta_el = [0.0] * ne
    flux_el = [0.0] * ne
    beta_sum = flux_sum = 0.0
    n_ok = 0
    x0 = None
    ndp = pim = 0.0
    for st in range(nst):
        Q = vol(m_w, m_s)
        if Q <= 0.0:
            break
        e = st // SUB
        Q_h = Q * 3600.0
        dP_fric = DP_NOM * (Q_h / Q_NOM) ** EXP_F / SUB
        dP_hid = P_bar - 0.5 * dP_fric - P_PERM_BAR
        P_pa = P_bar * 1e5
        Cb = [x / Q for x in m_s]
        k = K_MT * (Q_h / Q_NOM) ** EXP_K if EXP_K > 0.0 else K_MT
        k = max(k, 1.0e-7)
        if x0 is None:
            x0 = A_WATER * max(dP_hid - pi_osm(Cb, P_pa) / 1e5, 0.0)
        Jw, beta, Cm, Cp, dPi, pim = resolver_flux(dP_hid, Cb, P_pa, x0, k)
        x0 = Jw
        ndp = dP_hid - dPi

        dm_w = min(Jw * a_step * RHO_W, 0.95 * m_w)
        m_w -= dm_w
        perm_w += dm_w
        for i in range(ns):
            dm = min(B_s[i] * (Cm[i] - Cp[i]) * a_step, 0.95 * m_s[i])
            m_s[i] -= dm
            perm_s[i] += dm
        P_bar = max(P_bar - dP_fric, P_PERM_BAR)
        flux_sum += Jw
        beta_sum += beta
        n_ok += 1
        beta_el[e] = max(beta_el[e], beta)
        flux_el[e] += Jw / SUB
    n_ok = max(n_ok, 1)
    return {"m_w": m_w, "m_s": m_s, "perm_w": perm_w, "perm_s": perm_s,
            "P_out_bar": P_bar, "flux": flux_sum / n_ok,
            "beta_medio": beta_sum / n_ok, "beta_max": max(beta_el),
            "beta_el": beta_el, "flux_el": flux_el, "ndp": ndp, "pim": pim / 1e5}


def simular(P_bar, npv, m_feed, ne):
    """Planta completa: npv tubos idénticos en paralelo (npv puede ser real en el diseño)."""
    k = 1.0 / npv
    r = correr_tubo(P_bar, m_feed * w_w * k, [m_feed * w * k for w in w_s], ne)
    mp = r["perm_w"] + sum(r["perm_s"])
    r["rec"] = mp * npv / m_feed
    r["wp"] = sum(r["perm_s"]) / mp if mp > 0.0 else 0.0
    return r


def resolver_presion(rec_obj, npv, m_feed, ne):
    """Presión de alimentación [bar] que da el recovery objetivo (falsa posición de Illinois).
    Devuelve (P_bar, estado) con estado 'ok' | 'max' (inalcanzable) | 'min'."""
    lo = pi_osm(C_F, Pf) / 1e5 + P_PERM_BAR
    hi = P_MAX_BAR
    if hi <= lo:
        return hi, "max"
    f_hi = simular(hi, npv, m_feed, ne)["rec"] - rec_obj
    if f_hi < 0.0:
        return hi, "max"
    f_lo = simular(lo, npv, m_feed, ne)["rec"] - rec_obj
    if f_lo >= 0.0:
        return lo, "min"
    side = 0
    c = hi
    for _ in range(40):
        if f_hi == f_lo:
            break
        c = (lo * f_hi - hi * f_lo) / (f_hi - f_lo)
        f_c = simular(c, npv, m_feed, ne)["rec"] - rec_obj
        if abs(f_c) < 1e-6 or abs(hi - lo) < 0.005:
            break
        if f_c < 0.0:
            lo, f_lo = c, f_c
            if side == -1:
                f_hi *= 0.5
            side = -1
        else:
            hi, f_hi = c, f_c
            if side == 1:
                f_lo *= 0.5
            side = 1
    return c, "ok"


# -----------------------------------------------------------------------------
# 5) MODOS DE CÁLCULO
# -----------------------------------------------------------------------------
def _plan(res, npv, P_bar, m_oi, **kw):
    d = {"res": res, "npv": npv, "P_op_bar": P_bar, "m_oi": m_oi, "ne": N_ELEM,
         "npv_ex": float(npv), "area_ex": AREA_ELEM * N_ELEM * npv,
         "f": 1.0, "rec_obj": None, "estado_P": "ok"}
    d.update(kw)
    return d


def _ceil(x):
    return max(int(math.ceil(x - 1e-9)), 1)


def modo_simulacion():
    return _plan(simular(Pf / 1e5, N_PV, m_total_f, N_ELEM), N_PV, Pf / 1e5, m_total_f)


def modo_diseno_presion():
    P, est = resolver_presion(REC_OBJ, N_PV, m_total_f, N_ELEM)
    if est == "max":
        aviso("con %.0f bar no se alcanza Recovery_obj = %.1f %%; se usa la presión máxima."
              % (P, 100.0 * REC_OBJ))
    log("RO | DISENO_PRESION: presión de alimentación requerida = %.2f bar "
        "(ajusta la bomba; la corriente de alimentación no se modifica)" % P)
    return _plan(simular(P, N_PV, m_total_f, N_ELEM), N_PV, P, m_total_f,
                 rec_obj=REC_OBJ, estado_P=est)


def modo_diseno_area():
    qp = REC_OBJ * m_total_f / RHO_W                  # m3/s de permeado
    area_ex = qp / FLUX_DIS
    ne_ex = area_ex / AREA_ELEM
    npv_ex = ne_ex / N_ELEM
    npv = _ceil(npv_ex)
    ne_com = npv * N_ELEM
    log("RO | DISENO_AREA: area exacta = %.1f m2 | elementos exactos = %.2f | tubos exactos = %.2f"
        % (area_ex, ne_ex, npv_ex))
    log("RO | DISENO_AREA: comercial -> %d tubos x %d elementos = %d elementos, %.1f m2 "
        "(flux real %.2f LMH)" % (npv, N_ELEM, ne_com, ne_com * AREA_ELEM,
                                  qp / (ne_com * AREA_ELEM) * 3.6e6))
    if BETA_FIJO <= 0.0:
        log("RO | DISENO_AREA: beta de película (sin rechazo) a Flux_diseno = %.3f (límite %.2f)"
            % (math.exp(FLUX_DIS / K_MT), BETA_LIM))
    P, est = resolver_presion(REC_OBJ, npv, m_total_f, N_ELEM)
    if est == "max":
        aviso("con %.0f bar no se alcanza Recovery_obj = %.1f %%; se usa la presión máxima."
              % (P, 100.0 * REC_OBJ))
    log("RO | DISENO_AREA: presión de alimentación requerida = %.2f bar" % P)
    return _plan(simular(P, npv, m_total_f, N_ELEM), npv, P, m_total_f,
                 npv_ex=npv_ex, area_ex=area_ex, rec_obj=REC_OBJ, estado_P=est)


# --- blending ----------------------------------------------------------------
W_OBJ = C_OBJ * 1.0e-3 / RHO_W            # mg/L -> kg/m3 -> fracción másica (producto ~ agua)


def _balance_f(wp, R):
    """Fracción de la alimentación que va a la OI para que la mezcla cumpla W_OBJ.
    Balance de sal: W_OBJ*(Mp+Mb) = Mp*wp + Mb*wf,  Mp = R*f*M,  Mb = (1-f)*M."""
    den = TDS_F - R * wp - W_OBJ * (1.0 - R)
    if den <= 1.0e-15:
        return None
    return (TDS_F - W_OBJ) / den


def modo_blending():
    R = REC_OI
    if W_OBJ >= TDS_F:
        aviso("la alimentación (%.0f mg/L) ya cumple el objetivo (%.0f mg/L): no se requiere OI "
              "(f_OI = 0)." % (TDS_F * RHO_W * 1e3, C_OBJ))
        return _plan(None, 0, 0.0, 0.0, f=0.0, npv_ex=0.0, area_ex=0.0, rec_obj=R)

    wp0 = TDS_F * (1.0 - _R_SR)                              # a priori con SR nominal
    f = _balance_f(wp0, R)
    if f is None or f > 1.0:
        aviso("con SR = %.2f %% el permeado de OI no alcanza el objetivo ni con 100 %% por OI." % SR_NOM)
        f = 1.0
    log("RO | BLENDING (a priori, SR nominal): f_OI = %.4f, f_bypass = %.4f" % (f, 1.0 - f))

    # Fase 1: dimensionamiento con área continua y wp del modelo riguroso
    npv_c = area_ex = 0.0
    for _ in range(12):
        m_oi = f * m_total_f
        area_ex = R * m_oi / RHO_W / FLUX_DIS
        npv_c = area_ex / (AREA_ELEM * N_ELEM)
        P, est = resolver_presion(R, npv_c, m_oi, N_ELEM)
        res = simular(P, npv_c, m_oi, N_ELEM)
        fn = _balance_f(res["wp"], R)
        if fn is None or fn >= 1.0:
            aviso("el permeado calculado (%.0f mg/L) no permite cumplir el objetivo; f_OI = 1."
                  % (res["wp"] * RHO_W * 1e3))
            f = 1.0
            break
        if abs(fn - f) < 1.0e-4:
            f = fn
            break
        f = fn

    # Fase 2: tubos enteros (comercial); el bypass se reajusta con el permeado real
    npv = _ceil(npv_c)
    conv = False
    for _ in range(8):
        m_oi = f * m_total_f
        P, est = resolver_presion(R, npv, m_oi, N_ELEM)
        res = simular(P, npv, m_oi, N_ELEM)
        fn = _balance_f(res["wp"], R)
        fn = 1.0 if (fn is None or fn > 1.0) else fn
        if abs(fn - f) < 1.0e-4:
            conv = True
            break
        f = fn
    if not conv:
        m_oi = f * m_total_f
        P, est = resolver_presion(R, npv, m_oi, N_ELEM)
        res = simular(P, npv, m_oi, N_ELEM)
        aviso("el balance de blending no convergió del todo; revisa el TDS del producto.")
    if est == "max":
        aviso("con %.0f bar no se alcanza Recovery_OI = %.1f %%; se usa la presión máxima."
              % (P, 100.0 * R))
    log("RO | BLENDING: f_OI = %.4f | f_bypass = %.4f | tubos exactos = %.2f -> %d | P = %.2f bar"
        % (f, 1.0 - f, npv_c, npv, P))
    return _plan(res, npv, P, m_oi, f=f, npv_ex=npv_c, area_ex=area_ex, rec_obj=R, estado_P=est)


# -----------------------------------------------------------------------------
# 6) SUGERENCIAS CUANDO beta > límite
# -----------------------------------------------------------------------------
def sugerencias_beta(plan):
    res = plan["res"]
    s = []
    j_lead = res["flux_el"][0]
    j_med = res["flux"]
    if BETA_FIJO <= 0.0 and j_lead > 0.0:
        j_lim = K_MT * math.log(BETA_LIM)
        s.append("reducir el flux de diseño a <= %.1f LMH (media) o subir k_mt "
                 "(espaciador/velocidad)" % (j_med * j_lim / j_lead * 3.6e6))
    s.append("recovery por tubo actual = %.1f %%: reducir la recuperación por etapa "
             "(2 etapas en serie sobre el rechazo)" % (100.0 * res["rec"]))
    ne_ex = plan["area_ex"] / AREA_ELEM
    if plan["rec_obj"] and plan["m_oi"] > 0.0:
        intentos = 0
        for ne in range(N_ELEM - 1, 0, -1):
            if intentos >= 4:
                break
            intentos += 1
            nv = _ceil(ne_ex / ne)
            P, est = resolver_presion(plan["rec_obj"], nv, plan["m_oi"], ne)
            r = simular(P, nv, plan["m_oi"], ne)
            if est != "max" and r["beta_max"] <= BETA_LIM:
                s.append("usar N_elem = %d con N_pv = %d (beta max = %.3f, P = %.1f bar)"
                         % (ne, nv, r["beta_max"], P))
                break
    return s


# -----------------------------------------------------------------------------
# 7) ESCRITURA DE CORRIENTES
# -----------------------------------------------------------------------------
def escribir(ms, masas, P_pa):
    if ms is None:
        return
    total = sum(masas.values())
    if total <= 0.0:
        return
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


def _suma(a, b):
    return dict((n, a[n] + b[n]) for n in nombres)


# -----------------------------------------------------------------------------
# 8) EJECUCIÓN: cálculo, corrientes, resultados y chequeos
# -----------------------------------------------------------------------------
if MODO == "DISENO_AREA":
    plan = modo_diseno_area()
elif MODO == "DISENO_BLENDING":
    plan = modo_blending()
elif MODO == "DISENO_PRESION":
    plan = modo_diseno_presion()
else:
    plan = modo_simulacion()

res = plan["res"]
npv = plan["npv"]
m_oi = plan["m_oi"]
P_op_bar = plan["P_op_bar"]
P_op = P_op_bar * 1e5
m_byp = m_total_f - m_oi
FLOOR = 1.0e-15

SAL = {}
if res is None:                                     # blending sin OI (alimentación ya cumple)
    d_perm = dict((n, FLOOR) for n in nombres)
    d_rech = dict((n, FLOOR) for n in nombres)
    d_byp = dict((n, m_total_f * WF[n]) for n in nombres)
    escribir(ms_p, d_perm, P_PERM_BAR * 1e5)
    escribir(ms_r, d_rech, P_PERM_BAR * 1e5)
    escribir(ms_byp, d_byp, P_PERM_BAR * 1e5)
    escribir(ms_prod, d_byp, P_PERM_BAR * 1e5)
    SAL.update({"f_OI": 0.0, "f_bypass": 1.0, "Estado_OK": 0.0 if _AVISOS else 1.0,
                "TDS_producto_mgL": TDS_F * RHO_W * 1e3,
                "Caudal_bypass_m3h": m_total_f / rho_mez * 3600.0,
                "Caudal_producto_m3h": m_total_f / rho_mez * 3600.0,
                "Recovery_global_pct": 100.0})
else:
    d_perm = {nom_agua: res["perm_w"] * npv}
    d_rech = {nom_agua: res["m_w"] * npv}
    for j in range(ns):
        d_perm[sol_names[j]] = res["perm_s"][j] * npv
        d_rech[sol_names[j]] = res["m_s"][j] * npv
    m_p_tot = sum(d_perm.values())
    m_r_tot = sum(d_rech.values())
    P_out_bar = res["P_out_bar"]

    if m_p_tot <= 1.0e-12:
        aviso("flux nulo: la presión de operación (%.2f bar) no vence la presión osmótica." % P_op_bar)
    for d in (d_perm, d_rech):
        for n in nombres:
            d[n] = max(d[n], FLOOR)
    escribir(ms_p, d_perm, P_PERM_BAR * 1e5)
    escribir(ms_r, d_rech, P_out_bar * 1e5)

    d_byp = dict((n, m_byp * WF[n]) for n in nombres)
    if MODO == "DISENO_BLENDING":
        if m_byp > 0.0:
            escribir(ms_byp, d_byp, P_PERM_BAR * 1e5)
        escribir(ms_prod, _suma(d_perm, d_byp), P_PERM_BAR * 1e5)

    # --- resultados ---
    tds_p = res["wp"]
    tds_r = sum(d_rech[n] for n in sol_names) / m_r_tot
    mp_s = [d_perm[n] for n in sol_names]
    Q_p = vol(d_perm[nom_agua], mp_s)                           # m3/s
    Q_r = vol(d_rech[nom_agua], [d_rech[n] for n in sol_names])
    C_p = [x / Q_p for x in mp_s] if Q_p > 0.0 else [0.0] * ns
    C_r = [d_rech[n] / Q_r for n in sol_names]
    pi_f = pi_osm(C_F, Pf) / 1e5
    pi_p = pi_osm(C_p, P_PERM_BAR * 1e5) / 1e5
    pi_r = pi_osm(C_r, P_out_bar * 1e5) / 1e5
    Q_p_h = Q_p * 3600.0
    Q_byp_h = m_byp / rho_mez * 3600.0
    Q_prod_h = Q_p_h + Q_byp_h
    Q_oi = m_oi / rho_mez                                        # m3/s a la OI
    W_bomba = max(Q_oi * (P_op - P_SUC_BAR * 1e5), 0.0) / ETA_B / 1000.0   # kW
    W_erd = ETA_ERD * Q_r * max(P_out_bar - P_PERM_BAR, 0.0) * 1e5 / 1000.0
    sec = (W_bomba - W_erd) / Q_prod_h if Q_prod_h > 0.0 else 0.0
    w_prod = (m_p_tot * tds_p + m_byp * TDS_F) / (m_p_tot + m_byp) if (m_p_tot + m_byp) > 0 else 0.0
    area_com = AREA_ELEM * N_ELEM * npv

    SAL.update({
        "Recovery_pct": 100.0 * m_p_tot / m_oi,
        "Recovery_global_pct": 100.0 * (m_p_tot + m_byp) / m_total_f,
        "Flux_medio_LMH": res["flux"] * 3.6e6,
        "Area_total_m2": area_com,
        "Area_exacta_m2": plan["area_ex"],
        "N_elem_total": N_ELEM * npv,
        "N_elem_exacto": plan["area_ex"] / AREA_ELEM,
        "N_pv_usado": npv,
        "N_pv_exacto": plan["npv_ex"],
        "f_OI": plan["f"] if MODO == "DISENO_BLENDING" else 1.0,
        "f_bypass": 1.0 - plan["f"] if MODO == "DISENO_BLENDING" else 0.0,
        "Rechazo_aparente_pct": 100.0 * (1.0 - tds_p / TDS_F),
        "Rechazo_global_pct": 100.0 * (1.0 - w_prod / TDS_F),
        "Beta_medio": res["beta_medio"],
        "Beta_max": res["beta_max"],
        "Beta_ok": 1.0 if res["beta_max"] <= BETA_LIM + 1e-9 else 0.0,
        "Flux_max_beta_LMH": (K_MT * math.log(BETA_LIM) * 3.6e6) if BETA_FIJO <= 0.0 else 0.0,
        "Factor_conc": tds_r / TDS_F,
        "Pi_alimentacion_bar": pi_f,
        "Pi_membrana_salida_bar": res["pim"],
        "Pi_rechazo_bar": pi_r,
        "Pi_permeado_bar": pi_p,
        "NDP_salida_bar": res["ndp"],
        "dP_canal_bar": P_op_bar - P_out_bar,
        "P_operacion_bar": P_op_bar,
        "TDS_permeado_ppm": tds_p * 1.0e6,
        "TDS_producto_mgL": w_prod * RHO_W * 1.0e3,
        "Conc_rechazo_gL": sum(C_r),
        "Caudal_alim_OI_m3h": Q_oi * 3600.0,
        "Caudal_permeado_m3h": Q_p_h,
        "Caudal_bypass_m3h": Q_byp_h,
        "Caudal_producto_m3h": Q_prod_h,
        "Potencia_bomba_kW": W_bomba,
        "Potencia_ERD_kW": W_erd,
        "SEC_neta_kWh_m3": sec,
    })
    for e in range(min(N_ELEM, 12)):
        SAL["Beta_elem_%d" % (e + 1)] = res["beta_el"][e]

    # --- chequeos ---
    if res["beta_max"] > BETA_LIM + 1e-9:
        msg = "beta max = %.3f > límite %.2f (perfil por elemento: %s)." % (
            res["beta_max"], BETA_LIM, ", ".join("%.3f" % b for b in res["beta_el"]))
        aviso(msg)
        if MODO in ("DISENO_AREA", "DISENO_BLENDING"):
            for sug in sugerencias_beta(plan):
                log("RO | SUGERENCIA: " + sug)
    if pi_r > P_out_bar - P_PERM_BAR:
        aviso("pi del rechazo (%.1f bar) > presión neta de salida (%.1f bar): recovery inalcanzable "
              "a esta presión; revisa Metodo_Pi, el área o la presión." % (pi_r, P_out_bar - P_PERM_BAR))
    if res["ndp"] <= 0.0:
        aviso("NDP <= 0 en el último elemento (flux nulo al final del tubo).")
    if Pf <= P_PERM_BAR * 1e5 and MODO == "SIMULACION":
        aviso("la presión de la alimentación (%.2f bar) no supera la del permeado." % (Pf / 1e5))
    q_tubo = Q_oi * 3600.0 / npv
    if Q_ALIM_MAX > 0.0 and q_tubo > Q_ALIM_MAX:
        aviso("caudal de alimentación por tubo %.1f m3/h > máximo %.1f m3/h." % (q_tubo, Q_ALIM_MAX))
    if Q_RECH_MIN > 0.0 and Q_r * 3600.0 / npv < Q_RECH_MIN:
        aviso("caudal de rechazo por tubo %.2f m3/h < mínimo %.2f m3/h (riesgo de ensuciamiento)."
              % (Q_r * 3600.0 / npv, Q_RECH_MIN))
    if _NOCONV[0] > 0:
        aviso("el flux no convergió en %d paso(s) de cálculo; revisa los datos de entrada." % _NOCONV[0])
    if MODO == "DISENO_BLENDING":
        if w_prod > W_OBJ * 1.001:
            aviso("el producto (%.0f mg/L) NO cumple el objetivo (%.0f mg/L)."
                  % (w_prod * RHO_W * 1e3, C_OBJ))

    SAL["Estado_OK"] = 0.0 if _AVISOS else 1.0

for k_, v_ in SAL.items():
    _salida(k_, v_)

if res is not None:
    log("RO | Modo=%s | Rec=%.1f %% (global %.1f %%) | Flux=%.1f LMH | Rechazo=%.2f %% | FC=%.2f | "
        "Beta max=%.3f | P=%.2f bar | SEC=%.2f kWh/m3 | t=%.3f s | eval pi=%d | avisos=%d"
        % (MODO, SAL["Recovery_pct"], SAL["Recovery_global_pct"], SAL["Flux_medio_LMH"],
           SAL["Rechazo_aparente_pct"], SAL["Factor_conc"], SAL["Beta_max"], SAL["P_operacion_bar"],
           SAL["SEC_neta_kWh_m3"], time.time() - _T0, _N_PI[0], len(_AVISOS)))
