# Dataset Description: FLAMINGO Lensed Component-Separation Maps

This dataset consists of flat-sky cut maps and associated angular power spectra derived from full-sky maps of the cosmic microwave background (CMB), thermal and kinetic Sunyaev-Zel'dovich effects (tSZ/kSZ), and the cosmic infrared background (CIB). The sky signal maps originate from the FLAMINGO L1_m9 HYDRO_FIDUCIAL simulation (lightcone0, Jeger rotation). This is a large-volume (comoving box size of 1 Gpc) hydrodynamical simulation, offering a self-consistent treatment of gas physics and complex processes such as radiative cooling, star formation, AGN feedback, diffuse gas flows, and their gravitational back reaction on the dark matter.

The data consist of maps at six frequencies: 90, 150, 217, 353, 545, and 857 GHz. The lower three frequencies correspond to three Simons Observatory (SO) Large Aperture Telescope (LAT) bands centered at 93, 145, and 225 GHz. The higher three frequencies correspond to three Planck High Frequency Instrument (HFI) bands centered at 353, 545, and 857 GHz. The maps are smoothed by a Gaussian beam with FWHM corresponding to the respective survey specifications. Noise maps are generated separately via respective SO and Planck noise model pipelines and are stored in dedicated files.

---

## Sky Coverage and Patch Geometry

- **Projection:** Gnomonic (flat-sky), bilinearly interpolated from HEALPix. All data originally has nside=4096, but is upgraded to nside=8192 immediately before projection to mitigate interpolation artifacts. 
- **Patch size:** 5° × 5°
- **Pixel grid:** 256 × 256 pixels
- **Pixel resolution:** ≈ 1.17 arcmin/pixel
- **Step size:** 5° in both longitude and latitude between patches
- **Galactic cut:** None (full sky, gal_cut = 0°)
- **Total patches (N_patches):** full-sky tessellation at 5° step spacing, giving N_patches=1523

Patches are indexed by the same ordering as the list of centers returned by `utils.get_patch_centers(gal_cut=0°, step_size=5°)`.

---

## Directory Structure

```
── cut_maps/
   ├── tsz.npy
   ├── ksz.npy
   ├── lensed_cmb.npy
   ├── cib_{90,150,217,353,545,857}.npy
   ├── stacked_{90,150,217,353,545,857}.npy
   ├── so_noise/
   │   ├── 90.npy
   │   ├── 150.npy
   │   └── 217.npy
   └── planck_noise/
       └── planck_noise_{353,545,857}_{0..99}.npy
``` 

---

## Files

### `cut_maps/*.npy`

Individual cut map arrays. Each file has shape **(N_patches, 256, 256)**, dtype float64.

| File | Description | Units | Beam FWHM | Conversion Factor to µK_CMB |
|---|---|---|---|---|
| `tsz.npy` | Thermal SZ (Compton-*y* parameter) | dimensionless Compton-*y* | 1 arcmin | `utils.tsz(freq)` |
| `ksz.npy` | Kinetic SZ temperature fluctuation | dimensionless Doppler *b* | 1 arcmin | `utils.ksz(freq)` (=-TCMB_µK)|
| `lensed_cmb.npy` | Lensed CMB temperature map | µK_CMB | 1 arcmin | 1 |
| `cib_90.npy` | CIB at 90 GHz (delta-bandpass) | Jy/sr | 1 arcmin | `utils.jysr2uk(90)` |
| `cib_150.npy` | CIB at 150 GHz (delta-bandpass) | Jy/sr | 1 arcmin | `utils.jysr2uk(150)` |
| `cib_217.npy` | CIB at 217 GHz (bandpass-integrated) | Jy/sr | 1 arcmin | `utils.jysr2uk(217)` |
| `cib_353.npy` | CIB at 353 GHz (bandpass-integrated) | Jy/sr | 1 arcmin | `utils.jysr2uk(353)` |
| `cib_545.npy` | CIB at 545 GHz (bandpass-integrated) | Jy/sr | 1 arcmin | `utils.jysr2uk(545)` |
| `cib_857.npy` | CIB at 857 GHz (bandpass-integrated) | Jy/sr | 1 arcmin | `utils.jysr2uk(857)` |
| `stacked_90.npy` | Total sky signal at 90 GHz | µK_CMB | 2.2 arcmin | 1 |
| `stacked_150.npy` | Total sky signal at 150 GHz | µK_CMB | 1.4 arcmin | 1 |
| `stacked_217.npy` | Total sky signal at 217 GHz | µK_CMB | 1.0 arcmin | 1 |
| `stacked_353.npy` | Total sky signal at 353 GHz | µK_CMB | 4.5 arcmin | 1 |
| `stacked_545.npy` | Total sky signal at 545 GHz | µK_CMB | 4.72 arcmin | 1 |
| `stacked_857.npy` | Total sky signal at 857 GHz | µK_CMB | 4.42 arcmin | 1 |

The stacked signal maps are the sum of all components converted to thermodynamic temperature units:

```
signal(freq) = CIB(freq) × jysr2uk(freq) + tSZ × f_tSZ(freq) + kSZ × f_kSZ + lensed_CMB
```

where `f_tSZ` and `f_kSZ` are the standard tSZ and kSZ spectral response functions in µK_CMB units. The combined map is then smoothed with the frequency-specific beam listed above.

Individual component maps (tSZ, kSZ, lensed CMB, CIB) are smoothed with a 1 arcmin FWHM Gaussian beam before cutting.

---

### `cut_maps/so_noise/`

Simulated Simons Observatory (SO) LAT noise patches for 3 000 independent realisations.

| File | Shape | Dtype | Units |
|---|---|---|---|
| `90.npy` | (3000, 256, 256) | float32 | µK_CMB |
| `150.npy` | (3000, 256, 256) | float32 | µK_CMB |
| `217.npy` | (3000, 256, 256) | float32 | µK_CMB |

Noise is generated as a Gaussian random field with the SO LAT v3.1 temperature noise power spectrum (mode 2, elevation 50°, f_sky = 0.4). The 90 and 150 GHz channels are drawn from a correlated 2×2 covariance matrix via Cholesky decomposition; 217 GHz is independent. Noise is generated at the native patch pixel resolution (≈ 1.17 arcmin). These bands are intended to be matched with the `stacked_90`, `stacked_150`, and `stacked_217` signal maps respectively.

When sampling SO noise, the index does not need to match that of the sky maps.

---

### `cut_maps/planck_noise/`

Planck FFP10 end-to-end noise Monte Carlo (MC) realisations for the high-frequency channels. Provides 100 independent MC iterations, each stored as a separate file.

**Filename pattern:** `planck_noise_{freq}_{i}.npy` where `freq` ∈ {353, 545, 857} and `i` ∈ {0, …, 99}.

- **Shape:** (N_patches, 256, 256)
- **Dtype:** float32
- **Units:** same as the corresponding Planck frequency map (K_CMB for 353 GHz, MJy/sr for 545 and 857 GHz — as delivered in the raw FFP10 files)

When sampling Planck noise, the index should match that of the sky maps. The conversion factors to µK_CMB for 353, 545 and 857 GHz are `1e6`, `utils.jysr2uk(545)*1e6` and `utils.jysr2uk(857)*1e6`, respectively.

---


## Loading Data
```python
import numpy
import utils # make sure utils.py is available
import os
CUT_MAPS_DIR = 'cut_maps'

rng = np.random.default_rng(seed=42)
n_patch = 1523
n_planck = 100
n_so = 3000

i_patch = rng.integers(n_patch) # sky patch number
i_planck = rng.integers(n_planck) # Planck MC realization
i_so = rng.integers(n_so) # SO patch number

# Load stacked signal + noise maps
frequencies = [90, 150, 217, 353, 545, 857]
patches = {}
for freq in frequencies:
    full_map = np.load(os.path.join(CUT_MAPS_DIR, f'stacked_{freq}.npy')) # all sky patches
    if freq <= 217: # sample SO noise for lower frequencies
        noise = np.load(os.path.join(CUT_MAPS_DIR, f'so_noise/{freq}.npy'))[i_so]
    else: # sample Planck noise for higher frequencies
        if freq == 353: # units are K_CMB
            scale = 1e6
        else: # units are MJy/sr
            scale = 1e6*utils.jysr2uk(freq)
        noise = np.load(os.path.join(CUT_MAPS_DIR, f'planck_noise/planck_noise_{freq}_{i_planck}.npy'))[i_patch]*scale
    patches[freq] = full_map[i_patch] + noise # uK_CMB units

# Load single component, e.g. tSZ
tsz_patch = np.load(os.path.join(CUT_MAPS_DIR, 'tsz.npy'))[i_patch] # y-map
```

---

## CMB Simulation Details

The CMB map is a Gaussian realization drawn from the unlensed temperature power spectrum C_ℓ^TT computed with CLASS using the following cosmological parameters:

| Parameter | Value |
|---|---|
| A_s | 2.1 × 10⁻⁹ |
| n_s | 0.965 |
| h | 0.6736 |
| ω_b | 0.02237 |
| ω_cdm | 0.12 |
| τ_reio | 0.0544 |
| Y_He | 0.2454 |

The unlensed CMB alm coefficients are lensed using the FLAMINGO CMB lensing convergence map (κ) via `lenspyx`, with a target remapping accuracy of ε = 10⁻⁶. The random seed for the CMB realization is fixed at 42 for reproducibility.

---


