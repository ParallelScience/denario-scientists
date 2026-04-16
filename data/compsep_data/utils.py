from astropy import units as u
import numpy as np
from scipy.signal.windows import tukey
from scipy import stats
import healpy as hp
from astropy.cosmology import Planck15


### Unit Conversions and Response Functions ###
def jysr2uk(nu):
    """
    Jy/sr to uK conversion for CIB at frequency nu (GHz) with Planck 2015 T_CMB
    """
    equiv = u.thermodynamic_temperature(nu*u.GHz, Planck15.Tcmb0)
    return 1/( (1. * u.uK).to(u.Jy /u.sr, equivalencies=equiv) ).value

TCMB = 2.726 #Kelvin
TCMB_uK = 2.726e6 #micro-Kelvin

hplanck=6.626068e-34 #MKS
kboltz=1.3806503e-23 #MKS

def tsz(nu_ghz,*args,**kwargs):
        nu = 1.e9*nu_ghz
        X = hplanck*nu/(kboltz*TCMB)
        resp = (X / np.tanh(X/2.0) - 4.0) * TCMB_uK #put explicitly into uK_CMB units, so that output ILC map is in Compton-y
        return resp

def ksz(nu_ghz, *args, **kwargs):
    """
    kSZ response function in units of uK_CMB.
    Since kSZ is a Doppler shift of the CMB blackbody, its 
    frequency dependence is constant in thermodynamic temperature units.
    """
    # In the non-relativistic limit, dT/T = -tau * (vz/c).
    # To have the ILC recover tau*(vz/c), we return TCMB in uK.
    return -TCMB_uK


### Map and Power Spectrum Utilities ###
def get_patch_centers(gal_cut: u.deg, step_size: u.deg):
    """ Function to get the centers of the various patches to be cut out.

    Parameters
    ----------
    gal_cut: float
        We will miss out the region +/- `gal_cut` in Galactic latitude, measured
        in degrees.
    step_size: float
        Stepping distance in Galactic longitude, measured in degrees, between 
        patches.

    Returns
    -------
    list(tuple(float))
        List of two-element tuples containing the longitude and latitude.
    """
    gal_cut = gal_cut.to(u.deg)
    step_size = step_size.to(u.deg)
    assert gal_cut.unit == u.deg
    assert step_size.unit == u.deg
    southern_lat_range = np.arange(-90, (-gal_cut-step_size).value, step_size.value) * u.deg
    northern_lat_range = np.arange((gal_cut + step_size).value, 90, step_size.value) * u.deg
    lat_range = np.concatenate((southern_lat_range, northern_lat_range))

    centers = []
    for t in lat_range:
        step = step_size.value / np.cos(t.to(u.rad).value)
        for i in np.arange(0, 360, step):
            centers.append((i * u.deg, t))
    return centers


def powers(a, b=None, ps=10, ell_n=199, window_alpha=None):
    """
    Return flat-sky angular auto- or cross-power spectrum.

    Parameters
    ----------
    a, b: 2D arrays
        The two maps for which the power spectrum is to be computed, with the same shape. b defaults to None, in which case the auto-power spectrum of a will be computed.
    delta_theta: float
        Patch size in degrees.
    ell_n: int, optional
        The number of ell bins to use for the 1D power spectrum. Default is 199.
    window_alpha: float, optional
        The alpha parameter for the Tukey window used for apodisation. If None, no apodisation is applied. Default is None.

    Returns
    -------
    tuple(np.ndarray, np.ndarray)
        A tuple containing the 1D power spectrum and the corresponding ell values.
    """
    ps_rad = np.radians(ps) # patch size in radians
    npix = a.shape[-1]
    delta_theta = ps_rad / npix  # radians per pixel
    if window_alpha is not None:
        # Basic apodisation window
        if not isinstance(window_alpha, float):
            raise TypeError(f"window_alpha must be a float, got {type(window_alpha).__name__}")
        window_1d = tukey(npix, window_alpha)
        window_2d = np.outer(window_1d, window_1d)
    else:
        window_2d = np.ones((npix, npix))

    map1 = a - np.mean(a)
    map2 = b - np.mean(b) if b is not None else np.copy(map1)
    map1 *= window_2d
    map2 *= window_2d

    fft_map1 = np.fft.fft2(map1, norm=None)
    fft_map2 = np.fft.fft2(map2, norm=None)

    ps2d = np.real(fft_map1*np.conj(fft_map2))  * (delta_theta**2)/(npix**2)

    # Bin to 1D
    kx = np.fft.fftfreq(npix, d=delta_theta)
    ky = np.fft.fftfreq(npix, d=delta_theta)
    kxx, kyy = np.meshgrid(kx, ky)
    k = np.sqrt(kxx**2 + kyy**2).flatten()
    ps1d = ps2d.flatten()
    
    # Convert to angular
    ell = 2 * np.pi * k
    ell_bins = np.linspace(0, np.max(ell), ell_n+1)
    cl_flat, _, _ = stats.binned_statistic(ell, ps1d, bins=ell_bins, statistic='mean')
    ell_centers = 0.5 * (ell_bins[1:] + ell_bins[:-1])
    return cl_flat/np.mean(window_2d**2), ell_centers

def proj_bilinear(map, center, npix, res_arcmin):
    lon, lat = center
    proj = hp.projector.GnomonicProj(rot=(lon.value, lat.value, 0), coord='G', xsize=npix, ysize=npix, reso=res_arcmin)
    # 1. Get the 2D grid coordinates
    x, y = proj.ij2xy()
    # 2. Flatten them to 1D arrays using .ravel()
    # This prevents the ValueError by making shapes compatible
    theta, phi = proj.xy2ang(x.ravel(), y.ravel())
    # 3. Perform Bilinear Interpolation
    # This returns a 1D array of values
    bilinear_slice_1d = hp.get_interp_val(map, theta, phi)
    # 4. Reshape back to the 2D image format
    bilinear_slice = bilinear_slice_1d.reshape((npix, npix))
    return bilinear_slice
