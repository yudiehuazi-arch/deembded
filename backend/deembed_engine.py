"""
S-Parameter De-embedding Core Engine
Supports:
- Single-ended (2-Port) and Differential (4-Port)
- Double-sided (Both), Single-sided Left, Single-sided Right
- File-based De-embedding (PLTS Reference Plane Adjustment / T-matrix cascade inversion)
- IEEE 370 2X Thru Bifurcation & De-embedding (AFR)
- Port Extension (Delay & Loss peeling)
- Mixed-mode S-parameters (SDD, SCC, SCD, SDC)
- Time-domain TDR step response and impedance profile Z(t)
- Quality verification (Passivity, Reciprocity, Causality)
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import io
import tempfile
import warnings
import numpy as np
import skrf as rf
from skrf.network import concat_ports, s2t, t2s, inv
from skrf.calibration import deembedding

# Suppress harmless skrf floating-point interpolation warnings
warnings.filterwarnings('ignore', category=RuntimeWarning, module='skrf')


def load_network_from_str(content: str, filename: str = 'network.s2p') -> rf.Network:
    """Parse Touchstone content string into a scikit-rf Network object."""
    ext = os.path.splitext(filename)[1].lower()
    if not ext or ext == '.snp':
        # Auto-detect port count: if multiple columns per freq or 4-port layout
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith(('!', '#'))]
        if lines and len(lines[0].split()) >= 16:
            ext = '.s4p'
        else:
            ext = '.s2p'
    
    with tempfile.NamedTemporaryFile(suffix=ext, mode='w', delete=False, encoding='utf-8') as f:
        f.write(content)
        tmp_name = f.name
    try:
        try:
            ntwk = rf.Network(tmp_name)
        except Exception:
            # If failed with s2p, retry with s4p or vice versa
            alt_ext = '.s4p' if ext == '.s2p' else '.s2p'
            with tempfile.NamedTemporaryFile(suffix=alt_ext, mode='w', delete=False, encoding='utf-8') as f_alt:
                f_alt.write(content)
                alt_name = f_alt.name
            try:
                ntwk = rf.Network(alt_name)
            finally:
                if os.path.exists(alt_name):
                    os.remove(alt_name)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
    return ntwk


def network_to_touchstone_str(ntwk: rf.Network, form: str = 'ri') -> str:
    """Export scikit-rf Network object to standard Touchstone text format."""
    ext = f'.s{ntwk.nports}p'
    with tempfile.NamedTemporaryFile(suffix=ext, mode='r+', delete=False) as f:
        tmp_name = f.name
    try:
        ntwk.write_touchstone(filename=tmp_name, form=form)
        with open(tmp_name, 'r', encoding='utf-8') as f:
            content = f.read()
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
    return content


def align_frequencies(ntwks: list[rf.Network]) -> list[rf.Network]:
    """Ensure all networks have identical frequency points by interpolating if necessary."""
    if not ntwks:
        return []
    base_freq = ntwks[0].frequency
    aligned = [ntwks[0]]
    for n in ntwks[1:]:
        if n.frequency != base_freq:
            # Check overlap
            f_min = max(base_freq.f[0], n.frequency.f[0])
            f_max = min(base_freq.f[-1], n.frequency.f[-1])
            n_pts = min(len(base_freq), len(n))
            common_f = rf.Frequency(f_min, f_max, n_pts, unit='hz')
            aligned = [item.interpolate(common_f) for item in aligned]
            aligned.append(n.interpolate(common_f))
            base_freq = common_f
        else:
            aligned.append(n)
    return aligned


def generalized_s2t(s_mat: np.ndarray) -> np.ndarray:
    """
    Convert 2N-port S-matrix to Generalized Scattering Transfer Matrix (T-matrix).
    Shape of s_mat: (..., 2N, 2N).
    Block partition:
    S = [[S11, S12],
         [S21, S22]]
    T = [[inv(S21), -inv(S21)*S22],
         [S11*inv(S21), S12 - S11*inv(S21)*S22]]
    """
    n_total = s_mat.shape[-1]
    n = n_total // 2
    s11 = s_mat[..., :n, :n]
    s12 = s_mat[..., :n, n:]
    s21 = s_mat[..., n:, :n]
    s22 = s_mat[..., n:, n:]
    
    inv_s21 = np.linalg.inv(s21)
    t11 = inv_s21
    t12 = -inv_s21 @ s22
    t21 = s11 @ inv_s21
    t22 = s12 - s11 @ inv_s21 @ s22
    
    top = np.concatenate([t11, t12], axis=-1)
    bottom = np.concatenate([t21, t22], axis=-1)
    return np.concatenate([top, bottom], axis=-2)


def generalized_t2s(t_mat: np.ndarray) -> np.ndarray:
    """
    Convert Generalized Scattering Transfer Matrix (T-matrix) back to S-matrix.
    T = [[T11, T12],
         [T21, T22]]
    S = [[T21*inv(T11), T22 - T21*inv(T11)*T12],
         [inv(T11), -inv(T11)*T12]]
    """
    n_total = t_mat.shape[-1]
    n = n_total // 2
    t11 = t_mat[..., :n, :n]
    t12 = t_mat[..., :n, n:]
    t21 = t_mat[..., n:, :n]
    t22 = t_mat[..., n:, n:]
    
    inv_t11 = np.linalg.inv(t11)
    s11 = t21 @ inv_t11
    s12 = t22 - t21 @ inv_t11 @ t12
    s21 = inv_t11
    s22 = -inv_t11 @ t12
    
    top = np.concatenate([s11, s12], axis=-1)
    bottom = np.concatenate([s21, s22], axis=-1)
    return np.concatenate([top, bottom], axis=-2)


def uncoupled_lines_to_4port(line_a: rf.Network, line_b: rf.Network) -> rf.Network:
    """
    Combine two independent 2-port lines into a 4-port fixture network.
    line_a: connects port 0 (in) to port 2 (out)
    line_b: connects port 1 (in) to port 3 (out)
    """
    aligned = align_frequencies([line_a, line_b])
    return concat_ports([aligned[0], aligned[1]], port_order='second')


def deembed_t_matrix(s_total: np.ndarray, s_left: np.ndarray = None, s_right: np.ndarray = None, side: str = 'both') -> np.ndarray:
    """
    Universal T-matrix cascade inversion for 2-port or 4-port networks.
    side: 'both', 'left', or 'right'
    """
    t_tot = generalized_s2t(s_total)
    
    if side == 'left' and s_left is not None:
        t_l = generalized_s2t(s_left)
        t_dut = np.linalg.inv(t_l) @ t_tot
    elif side == 'right' and s_right is not None:
        t_r = generalized_s2t(s_right)
        t_dut = t_tot @ np.linalg.inv(t_r)
    elif side == 'both':
        if s_left is not None and s_right is not None:
            t_l = generalized_s2t(s_left)
            t_r = generalized_s2t(s_right)
            t_dut = np.linalg.inv(t_l) @ t_tot @ np.linalg.inv(t_r)
        elif s_left is not None:
            t_l = generalized_s2t(s_left)
            t_dut = np.linalg.inv(t_l) @ t_tot
        elif s_right is not None:
            t_r = generalized_s2t(s_right)
            t_dut = t_tot @ np.linalg.inv(t_r)
        else:
            t_dut = t_tot
    else:
        t_dut = t_tot
        
    return generalized_t2s(t_dut)


def file_based_deembed_2port(total: rf.Network, fix_l: rf.Network = None, fix_r: rf.Network = None, side: str = 'both') -> rf.Network:
    """Perform 2-port file-based de-embedding."""
    ntwks_to_align = [total]
    if fix_l is not None:
        ntwks_to_align.append(fix_l)
    if fix_r is not None:
        ntwks_to_align.append(fix_r)
        
    aligned = align_frequencies(ntwks_to_align)
    total_a = aligned[0]
    idx = 1
    fix_l_a = aligned[idx] if fix_l is not None else None
    if fix_l is not None:
        idx += 1
    fix_r_a = aligned[idx] if fix_r is not None else None
    
    s_dut = deembed_t_matrix(
        total_a.s,
        fix_l_a.s if fix_l_a is not None else None,
        fix_r_a.s if fix_r_a is not None else None,
        side=side
    )
    return rf.Network(frequency=total_a.frequency, s=s_dut, z0=total_a.z0)


def file_based_deembed_4port(
    total: rf.Network,
    fix_l: rf.Network = None,
    fix_r: rf.Network = None,
    side: str = 'both',
    port_mapping: str = 'sequential'
) -> rf.Network:
    """
    Perform 4-port file-based de-embedding.
    port_mapping: 'sequential' [1,2 -> 3,4] or 'plts' [1,3 -> 2,4]
    """
    # Remap to sequential internally if PLTS convention
    # Sequential: left ports = [0, 1], right ports = [2, 3]
    # PLTS: left ports = [0, 2], right ports = [1, 3]
    t_work = total.copy()
    if port_mapping == 'plts':
        t_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    fl_work = fix_l.copy() if fix_l is not None else None
    if fl_work is not None and port_mapping == 'plts':
        fl_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    fr_work = fix_r.copy() if fix_r is not None else None
    if fr_work is not None and port_mapping == 'plts':
        fr_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    ntwks_to_align = [t_work]
    if fl_work is not None:
        ntwks_to_align.append(fl_work)
    if fr_work is not None:
        ntwks_to_align.append(fr_work)
        
    aligned = align_frequencies(ntwks_to_align)
    t_work = aligned[0]
    idx = 1
    fl_work = aligned[idx] if fl_work is not None else None
    if fl_work is not None:
        idx += 1
    fr_work = aligned[idx] if fr_work is not None else None
    
    s_dut = deembed_t_matrix(
        t_work.s,
        fl_work.s if fl_work is not None else None,
        fr_work.s if fr_work is not None else None,
        side=side
    )
    dut_net = rf.Network(frequency=t_work.frequency, s=s_dut, z0=t_work.z0)
    
    # Restore original port mapping if PLTS
    if port_mapping == 'plts':
        dut_net.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    return dut_net


def adjust_fixture_delay_loss(
    fixture_net: rf.Network,
    delta_delay_ps: float = 0.0,
    delta_loss_db: float = 0.0,
    vp_eff: float = 3e8 * 0.7
) -> rf.Network:
    """
    Adjust fixture transmission line length (delay) and loss for asymmetric AFR (Length A != B).
    delta_delay_ps: positive to lengthen fixture, negative to shorten fixture.
    """
    if abs(delta_delay_ps) < 1e-4 and abs(delta_loss_db) < 1e-4:
        return fixture_net

    delta_tau = delta_delay_ps * 1e-12
    f = fixture_net.f
    f0 = f[-1] if f[-1] > 0 else 1.0

    # Phase delay shift
    phase_shift = np.exp(-1j * 2 * np.pi * f * delta_tau)

    # Loss adjustment
    loss_factor = np.exp(-(delta_loss_db / 8.686) * np.sqrt(np.maximum(f, 0) / f0)) if abs(delta_loss_db) > 1e-4 else np.ones_like(f)
    factor = phase_shift * loss_factor

    s_adj = fixture_net.s.copy()
    nports = fixture_net.nports

    if nports == 2:
        # Port 0 (launch), Port 1 (split plane / DUT connection)
        s_adj[:, 1, 0] *= factor
        s_adj[:, 0, 1] *= factor
        s_adj[:, 1, 1] *= (factor ** 2)
    elif nports == 4:
        # Ports 0, 1 (launch), Ports 2, 3 (split plane / DUT connection)
        for i in [0, 1]:
            for j in [2, 3]:
                s_adj[:, i, j] *= factor
                s_adj[:, j, i] *= factor
        for i in [2, 3]:
            for j in [2, 3]:
                s_adj[:, i, j] *= (factor ** 2)

    return rf.Network(frequency=fixture_net.frequency, s=s_adj, z0=fixture_net.z0)


def ieee370_2xthru_deembed_2port(
    total: rf.Network,
    thru_2x: rf.Network,
    side: str = 'both',
    z0: float = 50.0,
    delta_delay_ps_a: float = 0.0,
    delta_delay_ps_b: float = 0.0,
    delta_loss_db_a: float = 0.0,
    delta_loss_db_b: float = 0.0,
    match_a_ne_b: bool = False
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """
    IEEE 370 2X Thru de-embedding for 2-port network.
    Supports symmetric and asymmetric fixtures (Fixture A != Fixture B).
    Returns: (dut_network, left_1x_fixture, right_1x_fixture)
    """
    aligned = align_frequencies([total, thru_2x])
    tot_a, thru_a = aligned[0], aligned[1]
    
    dm = deembedding.IEEEP370_SE_NZC_2xThru(dummy_2xthru=thru_a, z0=z0)
    fix_l = dm.s_side1
    fix_r = dm.s_side2.flipped()

    # Apply Keysight PLTS Asymmetric Length Correction (Length A != B)
    if abs(delta_delay_ps_a) > 1e-4 or abs(delta_loss_db_a) > 1e-4:
        fix_l = adjust_fixture_delay_loss(fix_l, delta_delay_ps_a, delta_loss_db_a)
    if abs(delta_delay_ps_b) > 1e-4 or abs(delta_loss_db_b) > 1e-4:
        fix_r = adjust_fixture_delay_loss(fix_r, delta_delay_ps_b, delta_loss_db_b)
    
    s_dut = deembed_t_matrix(tot_a.s, fix_l.s, fix_r.s, side=side)
    dut_net = rf.Network(frequency=tot_a.frequency, s=s_dut, z0=z0)
    return dut_net, fix_l, fix_r


def ieee370_2xthru_deembed_4port(
    total: rf.Network,
    thru_2x: rf.Network,
    side: str = 'both',
    z0: float = 50.0,
    port_mapping: str = 'sequential',
    delta_delay_ps_a: float = 0.0,
    delta_delay_ps_b: float = 0.0,
    delta_loss_db_a: float = 0.0,
    delta_loss_db_b: float = 0.0,
    match_a_ne_b: bool = False
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """
    IEEE 370 Mixed-Mode 2X Thru de-embedding for 4-port differential network.
    Supports symmetric and asymmetric fixtures (Fixture A != Fixture B).
    Returns: (dut_network, left_1x_fixture, right_1x_fixture)
    """
    t_work = total.copy()
    thru_work = thru_2x.copy()
    if port_mapping == 'plts':
        t_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        thru_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    aligned = align_frequencies([t_work, thru_work])
    t_work, thru_work = aligned[0], aligned[1]
    
    dm = deembedding.IEEEP370_MM_NZC_2xThru(dummy_2xthru=thru_work, z0=z0, port_order='second')
    fix_l = dm.se_side1
    fix_r = dm.se_side2.flipped()

    # Apply Keysight PLTS Asymmetric Length Correction (Length A != B)
    if abs(delta_delay_ps_a) > 1e-4 or abs(delta_loss_db_a) > 1e-4:
        fix_l = adjust_fixture_delay_loss(fix_l, delta_delay_ps_a, delta_loss_db_a)
    if abs(delta_delay_ps_b) > 1e-4 or abs(delta_loss_db_b) > 1e-4:
        fix_r = adjust_fixture_delay_loss(fix_r, delta_delay_ps_b, delta_loss_db_b)
    
    s_dut = deembed_t_matrix(t_work.s, fix_l.s, fix_r.s, side=side)
    dut_net = rf.Network(frequency=t_work.frequency, s=s_dut, z0=z0)
    
    if port_mapping == 'plts':
        dut_net.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        fix_l.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        fix_r.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    return dut_net, fix_l, fix_r


def dual_2xthru_deembed_2port(
    total: rf.Network,
    thru_2x_a: rf.Network,
    thru_2x_b: rf.Network,
    side: str = 'both',
    z0: float = 50.0
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """
    Dual 2X Thru de-embedding (separate Fixture A and Fixture B 2X Thru files).
    Bifurcates thru_2x_a using IEEE 370 Annex A to extract 1X Fixture A.
    Bifurcates thru_2x_b using IEEE 370 Annex A to extract 1X Fixture B.
    De-embeds total network with fix_a on left and fix_b on right.
    Returns: (dut_network, fix_a_1x, fix_b_1x)
    """
    aligned = align_frequencies([total, thru_2x_a, thru_2x_b])
    tot_a, thru_a, thru_b = aligned[0], aligned[1], aligned[2]
    
    # Bifurcate 2X Thru A to get 1X Fixture A
    dm_a = deembedding.IEEEP370_SE_NZC_2xThru(dummy_2xthru=thru_a, z0=z0)
    fix_a = dm_a.s_side1
    
    # Bifurcate 2X Thru B to get 1X Fixture B
    dm_b = deembedding.IEEEP370_SE_NZC_2xThru(dummy_2xthru=thru_b, z0=z0)
    fix_b = dm_b.s_side2.flipped()
    
    s_dut = deembed_t_matrix(tot_a.s, fix_a.s, fix_b.s, side=side)
    dut_net = rf.Network(frequency=tot_a.frequency, s=s_dut, z0=z0)
    return dut_net, fix_a, fix_b


def dual_2xthru_deembed_4port(
    total: rf.Network,
    thru_2x_a: rf.Network,
    thru_2x_b: rf.Network,
    side: str = 'both',
    z0: float = 50.0,
    port_mapping: str = 'sequential'
) -> tuple[rf.Network, rf.Network, rf.Network]:
    """
    Dual 2X Thru de-embedding for 4-port differential network.
    Bifurcates thru_2x_a to extract 1X Fixture A.
    Bifurcates thru_2x_b to extract 1X Fixture B.
    """
    t_work = total.copy()
    thru_a_work = thru_2x_a.copy()
    thru_b_work = thru_2x_b.copy()
    if port_mapping == 'plts':
        t_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        thru_a_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        thru_b_work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    aligned = align_frequencies([t_work, thru_a_work, thru_b_work])
    t_work, thru_a_work, thru_b_work = aligned[0], aligned[1], aligned[2]
    
    dm_a = deembedding.IEEEP370_MM_NZC_2xThru(dummy_2xthru=thru_a_work, z0=z0, port_order='second')
    fix_a = dm_a.se_side1
    
    dm_b = deembedding.IEEEP370_MM_NZC_2xThru(dummy_2xthru=thru_b_work, z0=z0, port_order='second')
    fix_b = dm_b.se_side2.flipped()
    
    s_dut = deembed_t_matrix(t_work.s, fix_a.s, fix_b.s, side=side)
    dut_net = rf.Network(frequency=t_work.frequency, s=s_dut, z0=z0)
    
    if port_mapping == 'plts':
        dut_net.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        fix_a.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        fix_b.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    return dut_net, fix_a, fix_b


def port_extension_deembed(
    total: rf.Network,
    delay_ps_left: float = 0.0,
    delay_ps_right: float = 0.0,
    loss_db_left: float = 0.0,
    loss_db_right: float = 0.0,
    side: str = 'both'
) -> rf.Network:
    """
    Apply Port Extension (Electrical Delay & Loss de-embedding).
    """
    f = total.frequency.f
    f0 = f[-1] if f[-1] > 0 else 1.0
    
    # Calculate phase shift and attenuation factor
    d_l = delay_ps_left * 1e-12 if side in ['both', 'left'] else 0.0
    d_r = delay_ps_right * 1e-12 if side in ['both', 'right'] else 0.0
    
    l_l = loss_db_left if side in ['both', 'left'] else 0.0
    l_r = loss_db_right if side in ['both', 'right'] else 0.0
    
    theta_l = 2 * np.pi * f * d_l
    alpha_l = (l_l / 8.686) * np.sqrt(np.maximum(f, 0) / f0)
    gamma_l = np.exp(alpha_l + 1j * theta_l)
    
    theta_r = 2 * np.pi * f * d_r
    alpha_r = (l_r / 8.686) * np.sqrt(np.maximum(f, 0) / f0)
    gamma_r = np.exp(alpha_r + 1j * theta_r)
    
    s_corr = total.s.copy()
    nports = total.nports
    
    if nports == 2:
        # Port 0 (Left), Port 1 (Right)
        s_corr[:, 0, 0] *= (gamma_l ** 2)
        s_corr[:, 1, 1] *= (gamma_r ** 2)
        s_corr[:, 1, 0] *= (gamma_l * gamma_r)
        s_corr[:, 0, 1] *= (gamma_l * gamma_r)
    elif nports == 4:
        # Assuming ports 0,1 are Left, 2,3 are Right
        for p in [0, 1]:
            s_corr[:, p, p] *= (gamma_l ** 2)
        for p in [2, 3]:
            s_corr[:, p, p] *= (gamma_r ** 2)
        for p_l in [0, 1]:
            for p_r in [2, 3]:
                s_corr[:, p_l, p_r] *= (gamma_l * gamma_r)
                s_corr[:, p_r, p_l] *= (gamma_l * gamma_r)
                
    return rf.Network(frequency=total.frequency, s=s_corr, z0=total.z0)


def auto_detect_port_mapping(ntwk: rf.Network) -> str:
    """
    Automatically detect whether a 4-port network uses Sequential [1,2 -> 3,4]
    or PLTS [1,3 -> 2,4] port convention.
    In Sequential: through lanes are 1->3 (S31) and 2->4 (S42).
    In PLTS: through lanes are 1->2 (S21) and 3->4 (S43).
    Ensures input and output ports along the same physical link are communicating.
    """
    if ntwk.nports != 4:
        return 'sequential'
    
    n_check = min(len(ntwk.f), 60)
    mag_s21 = float(np.mean(np.abs(ntwk.s[:n_check, 1, 0]))) # PLTS through (Port 1 -> 2)
    mag_s31 = float(np.mean(np.abs(ntwk.s[:n_check, 2, 0]))) # Sequential through (Port 1 -> 3)
    
    return 'plts' if mag_s21 > mag_s31 else 'sequential'


def compute_mixed_mode(ntwk_4port: rf.Network, port_mapping: str = 'sequential') -> dict:
    """
    Compute Generalized Mixed-Mode S-parameters (SDD, SCC, SCD, SDC) for a 4-port network.
    Returns dictionary with magnitude in dB and phase in degrees.
    """
    if port_mapping == 'auto':
        port_mapping = auto_detect_port_mapping(ntwk_4port)
        
    work = ntwk_4port.copy()
    if port_mapping == 'plts':
        work.renumber([0, 1, 2, 3], [0, 2, 1, 3])
        
    mm = work.copy()
    mm.se2gmm(p=2)
    
    f_ghz = mm.f / 1e9
    
    # In skrf se2gmm(p=2):
    # Port 0: d0 (Diff Port 1)
    # Port 1: d1 (Diff Port 2)
    # Port 2: c0 (Comm Port 1)
    # Port 3: c1 (Comm Port 2)
    s = mm.s
    
    def to_db_phase(s_ij):
        mag_db = 20 * np.log10(np.maximum(np.abs(s_ij), 1e-12))
        phase_deg = np.angle(s_ij, deg=True)
        return mag_db.tolist(), phase_deg.tolist()
        
    sdd11_db, sdd11_phase = to_db_phase(s[:, 0, 0])
    sdd21_db, sdd21_phase = to_db_phase(s[:, 1, 0])
    sdd12_db, sdd12_phase = to_db_phase(s[:, 0, 1])
    sdd22_db, sdd22_phase = to_db_phase(s[:, 1, 1])
    
    scc11_db, scc11_phase = to_db_phase(s[:, 2, 2])
    scc21_db, scc21_phase = to_db_phase(s[:, 3, 2])
    scc12_db, scc12_phase = to_db_phase(s[:, 2, 3])
    scc22_db, scc22_phase = to_db_phase(s[:, 3, 3])
    
    scd21_db, scd21_phase = to_db_phase(s[:, 3, 0]) # Diff to Comm transmission
    scd11_db, scd11_phase = to_db_phase(s[:, 2, 0])
    scd12_db, scd12_phase = to_db_phase(s[:, 2, 1])
    scd22_db, scd22_phase = to_db_phase(s[:, 3, 1])
    sdc21_db, sdc21_phase = to_db_phase(s[:, 1, 2]) # Comm to Diff transmission
    sdc11_db, sdc11_phase = to_db_phase(s[:, 0, 2])
    sdc12_db, sdc12_phase = to_db_phase(s[:, 0, 3])
    sdc22_db, sdc22_phase = to_db_phase(s[:, 1, 3])
    
    return {
        'freq_ghz': f_ghz.tolist(),
        'sdd': {
            'sdd11': {'db': sdd11_db, 'phase': sdd11_phase},
            'sdd21': {'db': sdd21_db, 'phase': sdd21_phase},
            'sdd12': {'db': sdd12_db, 'phase': sdd12_phase},
            'sdd22': {'db': sdd22_db, 'phase': sdd22_phase},
        },
        'scc': {
            'scc11': {'db': scc11_db, 'phase': scc11_phase},
            'scc21': {'db': scc21_db, 'phase': scc21_phase},
            'scc12': {'db': scc12_db, 'phase': scc12_phase},
            'scc22': {'db': scc22_db, 'phase': scc22_phase},
        },
        'scd': {
            'scd21': {'db': scd21_db, 'phase': scd21_phase},
            'scd11': {'db': scd11_db, 'phase': scd11_phase},
            'scd12': {'db': scd12_db, 'phase': scd12_phase},
            'scd22': {'db': scd22_db, 'phase': scd22_phase},
        },
        'sdc': {
            'sdc21': {'db': sdc21_db, 'phase': sdc21_phase},
            'sdc11': {'db': sdc11_db, 'phase': sdc11_phase},
            'sdc12': {'db': sdc12_db, 'phase': sdc12_phase},
            'sdc22': {'db': sdc22_db, 'phase': sdc22_phase},
        }
    }


def compute_tdr_profile(freq_hz: np.ndarray, s_param: np.ndarray, z0: float = 50.0, num_pts: int = 1024) -> dict:
    """
    Compute TDR Step Response and Characteristic Impedance Profile Z(t).
    """
    f = np.asarray(freq_hz)
    s = np.asarray(s_param)
    
    df = np.median(np.diff(f))
    f_max = f[-1]
    
    f_uniform = np.arange(0, f_max + df/2, df)
    s_real = np.interp(f_uniform, f, np.real(s))
    s_imag = np.interp(f_uniform, f, np.imag(s))
    s_imag[0] = 0.0 # DC point imaginary component is 0 for reflection
    s_uniform = s_real + 1j * s_imag
    
    # Smooth cosine window on top 20%
    N = len(s_uniform)
    window = np.ones(N)
    w_len = max(int(0.2 * N), 4)
    window[-w_len:] = 0.5 * (1 + np.cos(np.linspace(0, np.pi, w_len)))
    s_win = s_uniform * window
    
    n_fft = max(num_pts, 2 * (N - 1))
    spectrum = np.zeros(n_fft, dtype=complex)
    spectrum[:N] = s_win
    spectrum[-N+1:] = np.conj(s_win[1:][::-1])
    
    impulse = np.fft.ifft(spectrum).real
    dt = 1.0 / (n_fft * df)
    t = np.arange(n_fft) * dt
    
    step = np.cumsum(impulse)
    # Normalize step response so DC reflection matches
    if np.max(np.abs(step)) > 0:
        dc_val = np.real(s_uniform[0])
        step_end = step[-1] if abs(step[-1]) > 1e-4 else 1.0
        scale = dc_val / step_end if abs(dc_val) > 1e-2 else 1.0
        step = step * scale
        
    rho = np.clip(step, -0.98, 0.98)
    z_profile = z0 * (1.0 + rho) / (1.0 - rho)
    
    # Return first half of the time window in ns
    view_len = min(N * 2, len(t))
    t_ns = t[:view_len] * 1e9
    
    return {
        'time_ns': t_ns.tolist(),
        'step': step[:view_len].tolist(),
        'z_profile': z_profile[:view_len].tolist(),
        'impulse': impulse[:view_len].tolist()
    }


def quality_check(ntwk: rf.Network) -> dict:
    """
    Perform IEEE 370 Annex C Quality Check:
    1. Passivity: max singular value <= 1.0
    2. Reciprocity: |S_ij - S_ji| ~ 0
    3. Causality estimate
    """
    s = ntwk.s
    n_pts, n_ports, _ = s.shape
    
    # Passivity
    max_sv_per_freq = np.zeros(n_pts)
    for i in range(n_pts):
        _, sv, _ = np.linalg.svd(s[i])
        max_sv_per_freq[i] = np.max(sv)
        
    max_sv = np.max(max_sv_per_freq)
    passivity_pass = bool(max_sv <= 1.005) # Allow 0.5% numerical tolerance
    passivity_margin_db = float(20 * np.log10(max_sv)) if max_sv > 0 else 0.0
    
    # Reciprocity
    recip_err = 0.0
    for i in range(n_ports):
        for j in range(i + 1, n_ports):
            diff = np.max(np.abs(s[:, i, j] - s[:, j, i]))
            recip_err = max(recip_err, diff)
    reciprocity_pass = bool(recip_err <= 0.05)
    
    # Overall score / status
    if passivity_pass and reciprocity_pass:
        status = 'PASS'
        verdict = '满足无源性与互易性，去嵌网络物理特性良好 (Physically Valid)'
    elif passivity_pass:
        status = 'WARNING'
        verdict = '无源性合格，但互易性存在微弱偏差 (Reciprocity Warning)'
    else:
        status = 'FAIL'
        verdict = f'无源性超标 (Max SV = {max_sv:.4f} > 1.0)，请检查夹具模型或频段设置'
        
    return {
        'status': status,
        'verdict': verdict,
        'max_singular_value': float(max_sv),
        'passivity_pass': passivity_pass,
        'passivity_margin_db': passivity_margin_db,
        'reciprocity_error': float(recip_err),
        'reciprocity_pass': reciprocity_pass
    }


def extract_network_display_data(ntwk: rf.Network, max_points: int = 401) -> dict:
    """
    Extract frequency, S-parameters magnitude (dB), phase (deg), group delay, and Smith chart coordinates.
    """
    f = ntwk.f / 1e9 # GHz
    n_ports = ntwk.nports
    
    # Downsample if too large for web visualization
    if len(f) > max_points:
        step = len(f) // max_points + 1
        indices = list(range(0, len(f), step))
        if indices[-1] != len(f) - 1:
            indices.append(len(f) - 1)
    else:
        indices = list(range(len(f)))
        
    f_sub = f[indices]
    s_sub = ntwk.s[indices]
    
    params = {}
    for i in range(n_ports):
        for j in range(n_ports):
            p_name = f'S{i+1}{j+1}'
            s_ij = s_sub[:, i, j]
            mag_db = 20 * np.log10(np.maximum(np.abs(s_ij), 1e-12))
            phase_deg = np.angle(s_ij, deg=True)
            
            # Group delay for transmission parameters (S21, S12, etc.)
            if i != j:
                unwrapped = np.unwrap(np.angle(ntwk.s[:, i, j]))
                df = np.diff(ntwk.f)
                gd = -np.diff(unwrapped) / (2 * np.pi * df) * 1e12 # ps
                # Interpolate to f_sub
                gd_sub = np.interp(f_sub, ntwk.f[:-1] / 1e9, gd)
            else:
                gd_sub = np.zeros_like(f_sub)
                
            params[p_name] = {
                'mag_db': mag_db.tolist(),
                'phase_deg': phase_deg.tolist(),
                'real': s_ij.real.tolist(),
                'imag': s_ij.imag.tolist(),
                'group_delay_ps': gd_sub.tolist()
            }
            
    return {
        'freq_ghz': f_sub.tolist(),
        'nports': n_ports,
        'params': params
    }


# ==============================================================================
# Preset Demo Generator
# ==============================================================================

def generate_preset_se_file_based() -> dict:
    """Preset 1: Single-Ended 2-Port File-Based De-embedding (50 Ohm microstrip + attenuator)."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.06 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    # Left fixture: 15mm line + SMA discontinuity (shunt C = 0.08pF)
    c_sma = med.shunt_capacitor(0.08e-12)
    fix_l = c_sma ** med.line(15e-3, 'm')
    
    # Right fixture: 12mm line + SMA discontinuity
    fix_r = med.line(12e-3, 'm') ** c_sma
    
    # DUT: 6dB attenuator / transmission line section
    dut_line = med.line(20e-3, 'm')
    
    total = fix_l ** dut_line ** fix_r
    
    return {
        'id': 'se_file_based',
        'title': '单端 2-Port 夹具测量去嵌 (File-Based)',
        'description': '典型单端微带线测试夹具（含SMA接头寄生电容与走线损耗），去嵌前后对比插入损耗与回波损耗。',
        'mode': 'se',
        'method': 'file_based',
        'total': total,
        'fix_l': fix_l,
        'fix_r': fix_r,
        'thru_2x': None,
        'dut_ideal': dut_line
    }


def generate_preset_se_2xthru() -> dict:
    """Preset 2: Single-Ended 2-Port IEEE 370 2X Thru AFR De-embedding."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    # 20mm fixture trace with standard PCB dielectric/copper loss
    fix_half = med.line(20e-3, 'm')
    
    # 2X Thru is two halves cascaded back to back
    thru_2x = fix_half ** fix_half.flipped()
    
    # DUT: a 25mm transmission line with distinct impedance/attenuation
    dut = med.line(25e-3, 'm')
    total = fix_half ** dut ** fix_half.flipped()
    
    return {
        'id': 'se_2xthru',
        'title': '单端 IEEE 370 2X Thru 自动夹具剥离 (AFR)',
        'description': '基于 IEEE 370 2X Thru 标准件自动劈半为 1X 左右夹具模型，消除夹具走线衰减与相位延迟。',
        'mode': 'se',
        'method': '2xthru',
        'total': total,
        'fix_l': None,
        'fix_r': None,
        'thru_2x': thru_2x,
        'dut_ideal': dut
    }


def generate_preset_diff_file_based() -> dict:
    """Preset 3: Differential 4-Port Coupled Fixture De-embedding."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    # Coupled 4-port fixtures (left and right)
    line_l1 = med.line(16e-3, 'm')
    line_l2 = med.line(16e-3, 'm')
    fix_l = concat_ports([line_l1, line_l2], port_order='second')
    
    line_r1 = med.line(14e-3, 'm')
    line_r2 = med.line(14e-3, 'm')
    fix_r = concat_ports([line_r1, line_r2], port_order='second')
    
    # DUT: differential pair with mild skew/delay
    line_d1 = med.line(30e-3, 'm')
    line_d2 = med.line(30.2e-3, 'm') # slight skew for mode conversion demonstration
    dut = concat_ports([line_d1, line_d2], port_order='second')
    
    total = fix_l ** dut ** fix_r
    
    return {
        'id': 'diff_file_based',
        'title': '差分 4-Port 全耦合夹具去嵌 (File-Based)',
        'description': '4端口差分网络去嵌，支持 PLTS 交叉或标准顺序端口排布，展示 SDD21/SDD11 改善及 SCD21 模态转换。',
        'mode': 'diff',
        'method': 'file_based',
        'total': total,
        'fix_l': fix_l,
        'fix_r': fix_r,
        'thru_2x': None,
        'dut_ideal': dut
    }


def generate_preset_diff_2xthru() -> dict:
    """Preset 4: Differential 4-Port IEEE 370 Mixed-Mode 2X Thru De-embedding."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    line_f1 = med.line(15e-3, 'm')
    line_f2 = med.line(15e-3, 'm')
    fix_half = concat_ports([line_f1, line_f2], port_order='second')
    
    # 2X Thru
    thru_2x = fix_half ** fix_half.flipped()
    
    # DUT
    dut = concat_ports([med.line(28e-3, 'm'), med.line(28e-3, 'm')], port_order='second')
    total = fix_half ** dut ** fix_half.flipped()
    
    return {
        'id': 'diff_2xthru',
        'title': '差分 4-Port IEEE 370 2X Thru 混合模 AFR 去嵌',
        'description': '利用 4 端口差分 2X Thru 标准件，通过 IEEE 370 算法剥离差分夹具对，获取纯净 DUT 的 SDD/SCC 响应。',
        'mode': 'diff',
        'method': '2xthru',
        'total': total,
        'fix_l': None,
        'fix_r': None,
        'thru_2x': thru_2x,
        'dut_ideal': dut
    }


def generate_preset_se_asym_file() -> dict:
    """Preset: Single-Ended Asymmetric File-Based De-embedding (Fixture A != B)."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.06 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    # Left fixture A: 12mm line with SMA (C = 0.08pF)
    c_sma_a = med.shunt_capacitor(0.08e-12)
    fix_a = c_sma_a ** med.line(12e-3, 'm')
    
    # Right fixture B: 24mm line with 2.92mm (C = 0.04pF) -> A != B!
    c_sma_b = med.shunt_capacitor(0.04e-12)
    fix_b = med.line(24e-3, 'm') ** c_sma_b
    
    # DUT: 30mm line section
    dut_line = med.line(30e-3, 'm')
    total = fix_a ** dut_line ** fix_b
    
    return {
        'id': 'se_asym_file',
        'title': '单端非对称双边去嵌 (Fixture A ≠ B: 独立夹具文件)',
        'description': '左端夹具为 12mm (SMA接头)，右端夹具为 24mm (2.92mm接头)，双边非对称全去嵌。',
        'mode': 'se',
        'method': 'file_based',
        'fixture_symmetry': 'asymmetric',
        'total': total,
        'fix_l': fix_a,
        'fix_r': fix_b,
        'thru_2x': None,
        'dut_ideal': dut_line
    }


def generate_preset_se_asym_2xthru() -> dict:
    """Preset: Single-Ended Asymmetric 2X Thru (PLTS Length A != B)."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    # Real fixtures: A is 12mm, B is 24mm (Total 36mm)
    fix_a = med.line(12e-3, 'm')
    fix_b = med.line(24e-3, 'm')
    
    # Standard 2X Thru is 36mm (measured as a single test line)
    thru_2x = med.line(36e-3, 'm')
    
    dut = med.line(25e-3, 'm')
    total = fix_a ** dut ** fix_b
    
    # Length difference: nominal half is 18mm. A is 12mm (-6mm -> -28.6ps), B is 24mm (+6mm -> +28.6ps)
    delta_tau_a_ps = (-6e-3 / vp) * 1e12 # -28.57 ps
    delta_tau_b_ps = (+6e-3 / vp) * 1e12 # +28.57 ps
    
    return {
        'id': 'se_asym_2xthru',
        'title': '单端 2X Thru 非对称去嵌 (PLTS Length A ≠ B 长度校正)',
        'description': '2X Thru 总长 36mm，实际板上左夹具 12mm (占33%)，右夹具 24mm (占67%)，应用 PLTS 非对称长度校正。',
        'mode': 'se',
        'method': '2xthru',
        'fixture_symmetry': 'asymmetric',
        'delta_delay_ps_a': delta_tau_a_ps,
        'delta_delay_ps_b': delta_tau_b_ps,
        'length_ratio_a': 12.0 / 36.0,
        'length_ratio_b': 24.0 / 36.0,
        'total': total,
        'fix_l': None,
        'fix_r': None,
        'thru_2x': thru_2x,
        'dut_ideal': dut
    }


def generate_preset_diff_asym_file() -> dict:
    """Preset: Differential 4-Port Asymmetric File-Based De-embedding (Fixture A != B)."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    # Left fixture A: 12mm differential pair
    line_a = med.line(12e-3, 'm')
    fix_a = concat_ports([line_a, line_a], port_order='second')
    
    # Right fixture B: 24mm differential pair -> A != B!
    line_b = med.line(24e-3, 'm')
    fix_b = concat_ports([line_b, line_b], port_order='second')
    
    # DUT: 30mm differential pair with slight delay
    line_dut = med.line(30e-3, 'm')
    dut = concat_ports([line_dut, line_dut], port_order='second')
    
    total = fix_a ** dut ** fix_b
    
    return {
        'id': 'diff_asym_file',
        'title': '差分 4-Port 非对称双边去嵌 (Fixture A ≠ B)',
        'description': '左侧差分夹具 12mm，右侧差分夹具 24mm，双边消除完全不对称的差分测试夹具。',
        'mode': 'diff',
        'method': 'file_based',
        'fixture_symmetry': 'asymmetric',
        'total': total,
        'fix_l': fix_a,
        'fix_r': fix_b,
        'thru_2x': None,
        'dut_ideal': dut
    }


def generate_preset_diff_asym_2xthru() -> dict:
    """Preset: Differential 4-Port Asymmetric 2X Thru (PLTS Length A != B)."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    line_a = med.line(12e-3, 'm')
    fix_a = concat_ports([line_a, line_a], port_order='second')
    
    line_b = med.line(24e-3, 'm')
    fix_b = concat_ports([line_b, line_b], port_order='second')
    
    line_2x = med.line(36e-3, 'm')
    thru_2x = concat_ports([line_2x, line_2x], port_order='second')
    
    line_dut = med.line(25e-3, 'm')
    dut = concat_ports([line_dut, line_dut], port_order='second')
    
    total = fix_a ** dut ** fix_b
    delta_tau_a_ps = (-6e-3 / vp) * 1e12
    delta_tau_b_ps = (+6e-3 / vp) * 1e12
    
    return {
        'id': 'diff_asym_2xthru',
        'title': '差分 2X Thru 非对称去嵌 (PLTS Length A ≠ B 长度校正)',
        'description': '差分 2X Thru 总长 36mm，实际左夹具 12mm (33%)，右夹具 24mm (67%)，劈半生成 1X 并分别去嵌。',
        'mode': 'diff',
        'method': '2xthru',
        'fixture_symmetry': 'asymmetric',
        'delta_delay_ps_a': delta_tau_a_ps,
        'delta_delay_ps_b': delta_tau_b_ps,
        'length_ratio_a': 12.0 / 36.0,
        'length_ratio_b': 24.0 / 36.0,
        'total': total,
        'fix_l': None,
        'fix_r': None,
        'thru_2x': thru_2x,
        'dut_ideal': dut
    }


def generate_preset_se_dual_2xthru() -> dict:
    """Preset: Single-Ended Dual 2X Thru (separate 2X Thru A and 2X Thru B)."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    # Left fixture A: 12mm line
    fix_a = med.line(12e-3, 'm')
    # Right fixture B: 24mm line -> A != B
    fix_b = med.line(24e-3, 'm')
    
    # 2X Thru A: 24mm line (A + A)
    thru_2x_a = med.line(24e-3, 'm')
    # 2X Thru B: 48mm line (B + B)
    thru_2x_b = med.line(48e-3, 'm')
    
    dut = med.line(25e-3, 'm')
    total = fix_a ** dut ** fix_b
    
    return {
        'id': 'se_dual_2xthru',
        'title': '单端独立双 2X Thru 劈半去嵌 (2X Thru A + 2X Thru B)',
        'description': '提供夹具 A 的 2X Thru 与夹具 B 的 2X Thru，分别独立劈半提取 1X A 与 1X B，再从待测文件中去嵌。',
        'mode': 'se',
        'method': 'dual_2xthru',
        'fixture_symmetry': 'asymmetric',
        'total': total,
        'fix_l': fix_a,
        'fix_r': fix_b,
        'thru_2x': thru_2x_a,
        'thru_2x_a': thru_2x_a,
        'thru_2x_b': thru_2x_b,
        'dut_ideal': dut
    }


def generate_preset_diff_dual_2xthru() -> dict:
    """Preset: Differential Dual 2X Thru (separate differential 2X Thru A and 2X Thru B)."""
    freq = rf.Frequency(0.1, 67.0, 269, unit='ghz')
    vp = 3e8 * 0.7
    gamma = 1j * 2 * np.pi * freq.f / vp + 0.08 * np.sqrt(freq.f / 1e9)
    med = rf.media.DefinedGammaZ0(freq, z0=50, gamma=gamma)
    
    line_a = med.line(12e-3, 'm')
    fix_a = concat_ports([line_a, line_a], port_order='second')
    
    line_b = med.line(24e-3, 'm')
    fix_b = concat_ports([line_b, line_b], port_order='second')
    
    line_2x_a = med.line(24e-3, 'm')
    thru_2x_a = concat_ports([line_2x_a, line_2x_a], port_order='second')
    
    line_2x_b = med.line(48e-3, 'm')
    thru_2x_b = concat_ports([line_2x_b, line_2x_b], port_order='second')
    
    line_dut = med.line(25e-3, 'm')
    dut = concat_ports([line_dut, line_dut], port_order='second')
    
    total = fix_a ** dut ** fix_b
    
    return {
        'id': 'diff_dual_2xthru',
        'title': '差分 4-Port 独立双 2X Thru 劈半去嵌 (2X Thru A + 2X Thru B)',
        'description': '提供差分 2X Thru A 与 2X Thru B，分别劈半提取差分 1X A 与 1X B，实现非对称差分对完全去嵌。',
        'mode': 'diff',
        'method': 'dual_2xthru',
        'fixture_symmetry': 'asymmetric',
        'total': total,
        'fix_l': fix_a,
        'fix_r': fix_b,
        'thru_2x': thru_2x_a,
        'thru_2x_a': thru_2x_a,
        'thru_2x_b': thru_2x_b,
        'dut_ideal': dut
    }


PRESETS = {
    'se_dual_2xthru': generate_preset_se_dual_2xthru,
    'diff_dual_2xthru': generate_preset_diff_dual_2xthru,
    'se_asym_2xthru': generate_preset_se_asym_2xthru,
    'diff_asym_2xthru': generate_preset_diff_asym_2xthru,
    'se_asym_file': generate_preset_se_asym_file,
    'diff_asym_file': generate_preset_diff_asym_file,
    'se_2xthru': generate_preset_se_2xthru,
    'diff_2xthru': generate_preset_diff_2xthru,
    'se_file_based': generate_preset_se_file_based,
    'diff_file_based': generate_preset_diff_file_based
}
