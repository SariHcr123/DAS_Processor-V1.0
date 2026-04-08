import os
import numpy as np
from scipy import signal
from scipy.fftpack import fft, ifft, fft2, ifft2, fftshift, ifftshift
from skimage import io
from nptdms import TdmsFile
from concurrent.futures import ThreadPoolExecutor, as_completed

class TDMSReader:
    def __init__(self, file_path):
        self.file_path = file_path
        self.tdms_file = None
        
    def __enter__(self):
        # Reading only metadata first if possible is faster, 
        # but TdmsFile.read() reads all structural metadata (channels). 
        # It does not read data unless access_data is used or we index it.
        # nptdms 1.x is lazy by default for data.
        self.tdms_file = TdmsFile.read(self.file_path)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tdms_file = None
        
    def get_properties(self):
        props = {}
        if not self.tdms_file: return props
        
        # Try to find a group with properties
        for group in self.tdms_file.groups():
            for key, val in group.properties.items():
                props[key] = val
            # Also check channel properties if needed
            break # Just take first group for now? Usually root props are enough?
            # Actually TdmsFile.properties exists?
        
        # Root properties
        for key, val in self.tdms_file.properties.items():
            props[key] = val
            
        return props

    def _read_channel(self, args):
        """Helper for parallel reading"""
        channel, t_start, t_end = args
        # Slicing nptdms channel reads from disk
        return channel[t_start:t_end]

    def get_data(self, ch_start=0, ch_end=None, t_start=0, t_end=None, progress_callback=None):
        if not self.tdms_file: return None
        
        # Assuming data is in the first group, channels are spatial channels
        groups = self.tdms_file.groups()
        if not groups: return None
        
        group = groups[0]
        channels = group.channels()
        
        # Slice channels
        if ch_end is None: ch_end = len(channels)
        selected_channels = channels[ch_start:ch_end]
        
        # Prepare arguments for parallel reading
        # We need to determine t_end if it's None, but checking length of one channel is enough
        if t_end is None:
            # Check length of first channel
            if selected_channels:
                t_end = len(selected_channels[0])
            else:
                t_end = 0
        
        # Use ThreadPoolExecutor for parallel IO
        # Adjust max_workers based on system, usually 4-8 is good for IO
        data_list = [None] * len(selected_channels)
        
        # Create args list with index to preserve order
        args_list = [(i, ch, t_start, t_end) for i, ch in enumerate(selected_channels)]
        
        def read_wrapper(args):
            idx, ch, ts, te = args
            return idx, self._read_channel((ch, ts, te))

        total_channels = len(selected_channels)
        completed_channels = 0

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(read_wrapper, args) for args in args_list]
            
            for future in as_completed(futures):
                idx, data = future.result()
                data_list[idx] = data
                
                if progress_callback:
                    completed_channels += 1
                    progress = int((completed_channels / total_channels) * 100)
                    progress_callback(progress)
            
        return np.array(data_list) # Shape: (Space, Time)

class DataProcessor:
    def __init__(self):
        self.raw_data = None
        self.processed_data = None
        
        # Base parameters
        self.base_dx = 4.0
        self.base_dt = 0.1
        
        # Effective parameters
        self.dx = 4.0
        self.dt = 0.1
        
        # Metadata
        self.start_distance = 0.0
        self.base_start_distance = 0.0
        self.gauge_length = 10.0
        self.zero_offset = 0.0
        self.fibre_length_multiplier = 1.0
        
        # Analysis Results
        self.ccf_data = None # (Space, Lag)
        self.ccf_lags = None

    def compute_cross_correlation(self, data, ref_ch_idx, max_lag_sec=1.0, window_sec=0.0):
        """
        Compute Cross-Correlation of all channels against a reference channel.
        Uses FFT-based correlation with optional stacking.
        """
        if data is None: return None, None
        
        n_ch, n_time = data.shape
        dt = self.dt if self.dt > 0 else 1.0
        
        max_lag_samples = int(max_lag_sec / dt)
        if max_lag_samples < 1: max_lag_samples = 1
        
        if window_sec > 0:
            window_samples = int(window_sec / dt)
        else:
            window_samples = n_time
            
        # Ensure window is valid
        window_samples = min(window_samples, n_time)
        if window_samples < 10: return None, None
        
        # Split into chunks
        n_windows = n_time // window_samples
        if n_windows < 1: n_windows = 1
        
        ccf_stack = None
        count = 0
        
        # FFT size for linear correlation (pad to >= 2*N - 1)
        # Find next power of 2 for speed
        n_fft = 1
        while n_fft < 2 * window_samples - 1:
            n_fft *= 2
            
        for w in range(n_windows):
            start = w * window_samples
            end = start + window_samples
            
            # Extract chunk
            chunk = data[:, start:end].copy()
            
            # Remove mean (DC offset) to avoid high correlation at 0 due to DC
            chunk = chunk - np.mean(chunk, axis=1, keepdims=True)
            
            # Tapering (optional but good for FFT)
            # window_func = signal.windows.hann(window_samples)
            # chunk = chunk * window_func
            
            ref_trace = chunk[ref_ch_idx, :]
            
            # FFT
            F_data = np.fft.fft(chunk, n=n_fft, axis=1)
            F_ref = np.fft.fft(ref_trace, n=n_fft)
            
            # Cross-Correlation in Freq Domain
            CCF_fft = F_data * np.conj(F_ref)
            
            # Inverse FFT
            ccf_chunk = np.fft.ifft(CCF_fft, axis=1).real
            
            # Shift zero lag to center
            ccf_chunk = np.fft.fftshift(ccf_chunk, axes=1)
            
            # Center index of the FFT result
            center = n_fft // 2
            
            # Crop to max_lag
            l_idx = center - max_lag_samples
            r_idx = center + max_lag_samples + 1
            
            # Boundary checks
            l_pad = 0
            r_pad = 0
            
            if l_idx < 0: 
                l_pad = -l_idx
                l_idx = 0
            if r_idx > n_fft: 
                r_pad = r_idx - n_fft
                r_idx = n_fft
                
            ccf_crop = ccf_chunk[:, l_idx:r_idx]
            
            # Handle padding if max_lag > half window (unlikely but possible)
            if l_pad > 0 or r_pad > 0:
                ccf_crop = np.pad(ccf_crop, ((0,0), (l_pad, r_pad)), mode='constant')
                
            # Normalize (optional, usually by energy)
            # norm = std(data) * std(ref) * len
            # skipping strict normalization for now, just raw correlation
            
            if ccf_stack is None:
                ccf_stack = np.zeros_like(ccf_crop)
            
            if ccf_stack.shape == ccf_crop.shape:
                ccf_stack += ccf_crop
                count += 1
                
        if count > 0:
            ccf_stack /= count
            
        self.ccf_data = ccf_stack
        
        # Generate lags axis
        n_lags = ccf_stack.shape[1]
        self.ccf_lags = (np.arange(n_lags) - n_lags // 2) * dt
        
        return self.ccf_data, self.ccf_lags

    def compute_dispersion(self, data, v_min=100.0, v_max=2000.0, v_step=10.0, f_min=1.0, f_max=100.0):
        """
        Compute Dispersion Image (f-v domain) from space-time data.
        Returns: f_axis, v_axis, dispersion_image, curve_v
        """
        if data is None:
            return None, None, None, None

        rows, cols = data.shape # rows=space, cols=time
        dt = self.dt if self.dt > 0 else 1.0
        dx = self.dx if self.dx > 0 else 1.0
        
        # 1. 2D FFT
        # Optimize: if data is too large, use a subset or window?
        # For dispersion, we usually want good f resolution (long time) and k resolution (long space).
        # But we can limit dimensions to power of 2 for speed.
        
        # Remove DC
        data_detrend = data - np.mean(data)
        
        # 2D FFT
        # fft2 returns (ny, nx) -> (k, f)
        # We need to shift zero freq to center
        f_k = fftshift(fft2(data_detrend))
        mag = np.abs(f_k)
        
        # Frequency and Wavenumber axes
        # fftfreq returns cycles/unit. 
        # f axis (time)
        freqs = fftshift(np.fft.fftfreq(cols, d=dt))
        # k axis (space)
        ks = fftshift(np.fft.fftfreq(rows, d=dx))
        
        # 2. Select Frequency Range (Positive only)
        # We only care about f > 0 (and usually k > 0 for forward, but we might want both directions)
        # Typically dispersion curves are symmetric or we care about one direction.
        # Let's assume positive frequency.
        f_mask = (freqs >= f_min) & (freqs <= f_max)
        if not np.any(f_mask):
            return None, None, None, None
            
        freqs_roi = freqs[f_mask]
        mag_roi = mag[:, f_mask] # Shape: (n_k, n_f_roi)
        
        # 3. Remap to Velocity Domain
        # v = f / k  =>  k = f / v
        v_axis = np.arange(v_min, v_max + v_step, v_step)
        n_v = len(v_axis)
        n_f = len(freqs_roi)
        
        disp_img = np.zeros((n_v, n_f))
        
        # Optimization: Meshgrid calculation
        # F_grid, V_grid = np.meshgrid(freqs_roi, v_axis)
        # K_target = F_grid / V_grid
        
        # But we need to interpolate from ks grid.
        # Since ks is uniform, we can convert k value to index.
        # idx = (k - k0) / dk
        
        k0 = ks[0]
        dk = ks[1] - ks[0]
        if dk == 0: dk = 1e-9
        
        for i_v, v in enumerate(v_axis):
            if v == 0: continue
            k_target = freqs_roi / v
            
            # Map k_target to indices in ks array
            # ks is from -kmax to +kmax (shifted)
            # idx = (k_target - k0) / dk
            
            k_indices = (k_target - k0) / dk
            
            # Nearest neighbor or Linear? 
            # Nearest is fast.
            k_idx_int = np.rint(k_indices).astype(int)
            
            # Valid indices
            valid_mask = (k_idx_int >= 0) & (k_idx_int < len(ks))
            
            # For valid f points, grab the value
            # disp_img[i_v, valid_mask] = mag_roi[k_idx_int[valid_mask], valid_mask] # This indexing is tricky in 2D
            
            # Row-by-row might be clearer but slower. 
            # mag_roi has shape (n_k, n_f_roi). 
            # We want mag_roi[k_idx, f_idx]
            
            # Advanced indexing:
            # We need column indices [0, 1, ..., n_f-1]
            col_indices = np.arange(n_f)
            
            # Apply mask
            valid_k = k_idx_int[valid_mask]
            valid_c = col_indices[valid_mask]
            
            if len(valid_k) > 0:
                disp_img[i_v, valid_mask] = mag_roi[valid_k, valid_c]
                
        # 4. Extract Curve (Max energy per frequency)
        # Find index of max value along velocity axis
        max_v_indices = np.argmax(disp_img, axis=0)
        curve_v = v_axis[max_v_indices]
        
        # Filter curve: if energy is too low, maybe set to NaN?
        # For now, just return the raw max.
        
        return freqs_roi, v_axis, disp_img, curve_v

    def compute_beamforming(self, data, angle_min=-90, angle_max=90, angle_step=1.0, f_min=1.0, f_max=100.0, v_sound=1500.0, window_sec=1.0, step_sec=0.5):
        """
        Compute Beamforming (Delay-and-Sum) for source localization (Angle-Time).
        Assuming linear array along the fiber.
        Returns: time_axis, angles, energy_map (time, angle)
        """
        if data is None:
            return None, None, None
            
        rows, cols = data.shape # rows=channels, cols=time
        dt = self.dt if self.dt > 0 else 1.0
        dx = self.dx if self.dx > 0 else 1.0
        
        # Array geometry (Linear)
        positions = np.arange(rows) * dx
        positions = positions - np.mean(positions)
        
        # Angles
        angles = np.arange(angle_min, angle_max + angle_step, angle_step)
        theta_rad = np.radians(angles)
        
        # Windowing
        n_window = int(window_sec / dt)
        n_step = int(step_sec / dt)
        if n_window < 2: n_window = 2
        if n_step < 1: n_step = 1
        
        n_windows = (cols - n_window) // n_step + 1
        if n_windows < 1: n_windows = 1
        
        # Result map: (n_time, n_angles)
        energy_map = np.zeros((n_windows, len(angles)))
        time_axis = np.zeros(n_windows)
        
        # Precompute Frequency bins for one window
        freqs = np.fft.fftfreq(n_window, d=dt)
        f_mask = (freqs >= f_min) & (freqs <= f_max)
        if not np.any(f_mask):
             # Fallback if range invalid, use all positive
             f_mask = (freqs >= 0)
             
        freqs_roi = freqs[f_mask]
        n_freqs = len(freqs_roi)
        
        # Precompute Steering Vectors per Frequency
        # For each freq, we have a matrix (n_ch, n_angles)
        # We can store them in a list or 3D array if memory allows.
        # steering_matrices[freq_idx] = (n_ch, n_angles)
        
        c = v_sound
        steering_matrices = []
        for f_val in freqs_roi:
            k = 2 * np.pi * f_val / c
            # Phase shifts: exp(j * k * x * sin(theta))
            # (n_ch, 1) * (1, n_angles)
            phase_shifts = np.exp(1j * k * positions[:, np.newaxis] * np.sin(theta_rad))
            steering_matrices.append(phase_shifts)
            
        # Sliding Window Processing
        for t_idx in range(n_windows):
            start = t_idx * n_step
            end = start + n_window
            
            # Extract window
            chunk = data[:, start:end]
            
            # FFT
            spectrum = np.fft.fft(chunk, axis=1) # (n_ch, n_window)
            spectrum_roi = spectrum[:, f_mask]   # (n_ch, n_freqs)
            
            # Beamform accumulation
            # For each freq, y = x^T * S
            # x: (n_ch,), S: (n_ch, n_angles)
            
            # Vectorized over freq?
            # spectrum_roi: (n_ch, n_freqs)
            # steering: list of (n_ch, n_angles)
            
            # Loop over frequencies is safer for memory
            row_energy = np.zeros(len(angles))
            
            for f_i in range(n_freqs):
                x_f = spectrum_roi[:, f_i] # (n_ch,)
                S = steering_matrices[f_i] # (n_ch, n_angles)
                
                y = np.dot(x_f, S) # (n_angles,)
                row_energy += np.abs(y)**2
                
            energy_map[t_idx, :] = row_energy
            time_axis[t_idx] = (start + n_window / 2) * dt
            
        # Normalize
        # Normalize per time step or globally?
        # Usually global normalization to see relative strength
        max_val = np.max(energy_map)
        if max_val > 0:
            energy_map /= max_val
            
        return time_axis, angles, energy_map

    def compute_scholte_dispersion_curve(self, vs_sed, h_sed, vs_sub, vp_sub=None, rho_sed=1.7, rho_sub=2.2, 
                                       vp_water=1500.0, rho_water=1.0, f_min=1.0, f_max=50.0, df=1.0):
        """
        Compute theoretical Scholte/Rayleigh dispersion curve for a 1-layer sediment over halfspace model.
        Model: Water / Sediment (vs_sed, h_sed) / Substrate (vs_sub)
        Returns: freqs, velocities
        """
        import scipy.optimize as optimize
        
        freqs = np.arange(f_min, f_max + df, df)
        velocities = []
        
        # Empirical/Approximations
        if vp_sub is None:
            vp_sub = 1.732 * vs_sub
            
        # Forward Model using Effective Medium Approximation for Surface/Interface Waves
        # V_scholte(f) ~ V_scholte_local(z_eff)
        # z_eff ~ 0.5 * lambda
        
        for f in freqs:
            if f <= 0:
                velocities.append(np.nan)
                continue
                
            # Fixed point iteration for phase velocity
            # Initial guess
            c_guess = min(vs_sed * 0.9, vp_water * 0.9)
            
            for _ in range(10):
                if c_guess <= 0: c_guess = 10.0
                wavelength = c_guess / f
                z_eff = 0.5 * wavelength
                
                # Effective Vs at depth z_eff
                if z_eff < h_sed:
                    vs_eff = vs_sed
                else:
                    # Weighting between sediment and substrate
                    # Simple volume weighting up to depth z_eff?
                    # vs_eff = (h_sed * vs_sed + (z_eff - h_sed) * vs_sub) / z_eff
                    # Or just substrate dominance?
                    # MASW often uses vs_eff = Vs at z_eff directly for simple mapping,
                    # but smooth transition is better.
                    vs_eff = (h_sed * vs_sed + (z_eff - h_sed) * vs_sub) / z_eff
                
                # Scholte Velocity Approximation
                # V_sch is root of Scholte equation. 
                # For soft sediment (Vs < Vw), V_sch ~ 0.88-0.95 Vs
                # For hard bottom (Vs > Vw), V_sch ~ Vw
                
                if vs_eff < vp_water:
                    # Soft: dominated by shear stiffness
                    c_new = 0.9 * vs_eff
                else:
                    # Hard: dominated by fluid bulk modulus
                    # Transition to Stoneley/Scholte limit < Vw
                    c_new = 0.99 * vp_water
                    
                # Damping
                c_guess = 0.5 * c_guess + 0.5 * c_new
                
            velocities.append(c_guess)
            
        return freqs, np.array(velocities)

    def invert_scholte_profile(self, f_obs, v_obs, bounds=None):
        """
        Invert for Vs profile (1 layer + halfspace).
        Bounds: [(vs_sed_min, max), (h_sed_min, max), (vs_sub_min, max)]
        """
        from scipy.optimize import minimize
        
        if bounds is None:
            # Default bounds for shallow water sediments
            bounds = [(20.0, 800.0), (1.0, 50.0), (200.0, 2500.0)]
            
        def objective(params):
            vs1, h, vs2 = params
            # Constraints
            if vs1 >= vs2: return 1e6 # Assume increasing stiffness with depth
            
            # Forward
            # Use same freq range as obs
            f_min, f_max = f_obs[0], f_obs[-1]
            if len(f_obs) > 1:
                df = f_obs[1] - f_obs[0]
            else:
                df = 1.0
                
            f_calc, v_calc = self.compute_scholte_dispersion_curve(vs1, h, vs2, f_min=f_min, f_max=f_max, df=df)
            
            # Interpolate to observed freqs in case of mismatch
            v_interp = np.interp(f_obs, f_calc, v_calc)
            
            # RMS Error
            rmse = np.sqrt(np.mean((v_interp - v_obs)**2))
            return rmse
            
        # Initial guess: Midpoints
        x0 = [np.mean(b) for b in bounds]
        
        # L-BFGS-B handles bounds
        res = minimize(objective, x0, bounds=bounds, method='L-BFGS-B')
        
        return res.x, res.fun

    def _get_filter_coeffs(self, ftype, order, Wn, btype='low'):
        """Helper to get filter coefficients based on type."""
        ftype = ftype.lower()
        if 'butter' in ftype:
            return signal.butter(order, Wn, btype=btype)
        elif 'chebyshev i' in ftype or 'cheby1' in ftype:
            # rp=1dB passband ripple
            return signal.cheby1(order, 1, Wn, btype=btype)
        elif 'chebyshev ii' in ftype or 'cheby2' in ftype:
            # rs=40dB stopband attenuation
            return signal.cheby2(order, 40, Wn, btype=btype)
        elif 'elliptic' in ftype or 'ellip' in ftype:
            # rp=1dB, rs=40dB
            return signal.ellip(order, 1, 40, Wn, btype=btype)
        elif 'bessel' in ftype:
            return signal.bessel(order, Wn, btype=btype)
        else:
            return signal.butter(order, Wn, btype=btype)

    def _apply_kalman_filter(self, data, Q, R):
        """
        Apply simple 1D Kalman Filter along time axis (axis 1).
        State: x (amplitude)
        Model: x_k = x_{k-1} + w, w ~ N(0, Q)
        Meas: z_k = x_k + v, v ~ N(0, R)
        """
        n_ch, n_time = data.shape
        x_est = np.zeros_like(data)
        
        # Vectorized implementation across channels
        # Initialize state and covariance
        # Initial guess: first sample
        x = data[:, 0].copy()
        P = np.ones(n_ch) * R # Initial uncertainty approx R
        
        x_est[:, 0] = x
        
        for t in range(1, n_time):
            # Prediction
            # x_pred = x # Random walk model
            P = P + Q
            
            # Update
            z = data[:, t]
            K = P / (P + R)
            x = x + K * (z - x)
            P = (1 - K) * P
            
            x_est[:, t] = x
            
        return x_est

    def load_image(self, image_path):
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"File not found: {image_path}")
            
        img = io.imread(image_path)
        img_normalized = img.astype(float) / 255.0
        
        if len(img.shape) == 3 and img.shape[2] >= 3:
            if np.allclose(img[:,:,0], img[:,:,1], atol=0.01) and np.allclose(img[:,:,1], img[:,:,2], atol=0.01):
                self.raw_data = img_normalized[:, :, 0]
            else:
                r = img_normalized[:, :, 0]
                b = img_normalized[:, :, 2]
                self.raw_data = (r - b)
        else:
            self.raw_data = img_normalized
            if len(self.raw_data.shape) == 3:
                self.raw_data = self.raw_data[:, :, 0]
                
        min_val = self.raw_data.min()
        max_val = self.raw_data.max()
        if max_val - min_val > 0:
            self.raw_data = 2 * (self.raw_data - min_val) / (max_val - min_val) - 1
            
        self.processed_data = self.raw_data.copy()
        
        self.base_dx = 1.0
        self.base_dt = 1.0
        self.dx = 1.0
        self.dt = 1.0
        self.base_start_distance = 0.0
        self.start_distance = 0.0
        return True

    def load_tdms(self, file_path, progress_callback=None):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with TDMSReader(file_path) as reader:
            props = reader.get_properties()
            
            self.zero_offset = float(props.get('Zero Offset (m)', 0.0))
            self.base_start_distance = float(props.get('Start Distance (m)', 0.0))
            self.start_distance = self.base_start_distance
            self.gauge_length = float(props.get('GaugeLength', 10.0))
            self.fibre_length_multiplier = float(props.get('Fibre Length Multiplier', 1.0))
            
            if 'SpatialResolution[m]' in props:
                self.base_dx = float(props['SpatialResolution[m]']) * self.fibre_length_multiplier
            else:
                self.base_dx = 4.0 * self.fibre_length_multiplier
            
            if 'SamplingFrequency[Hz]' in props:
                fs = float(props['SamplingFrequency[Hz]'])
                if fs > 0: self.base_dt = 1.0 / fs
            else:
                self.base_dt = 0.1
            
            self.dx = self.base_dx
            self.dt = self.base_dt
                
            # Load ALL data initially? Or should we support partial load?
            # For this tool, let's load all and let ROI node handle slicing in memory 
            # (unless file is huge, but let's stick to simple logic for now)
            data = reader.get_data(progress_callback=progress_callback)
            self.raw_data = data.T.astype(float)
            self.processed_data = self.raw_data.copy()
            return True, props

    def execute_pipeline(self, pipeline):
        """
        Execute a list of processing steps (nodes).
        Each step is a dict: {'type': 'NodeType', ...params...}
        """
        if self.raw_data is None:
            return

        # Always start from raw data? 
        # Yes, pipeline is fully descriptive.
        data = self.raw_data.copy()
        
        # Reset effective params
        self.dx = self.base_dx
        self.dt = self.base_dt
        self.start_distance = self.base_start_distance

        fs = 1.0 / self.dt if self.dt > 0 else 1.0
        nyquist = 0.5 * fs

        for step in pipeline:
            stype = step.get('type')
            
            # --- Preprocessing ---
            if stype == "ROI":
                ch_s = int(step.get('ch_start', 0))
                ch_e = int(step.get('ch_end', data.shape[0]))
                t_s = int(step.get('time_start', 0))
                t_e = int(step.get('time_end', data.shape[1]))
                
                ch_s = max(0, ch_s)
                ch_e = min(data.shape[0], ch_e)
                t_s = max(0, t_s)
                t_e = min(data.shape[1], t_e)
                
                if ch_e > ch_s and t_e > t_s:
                    data = data[ch_s:ch_e, t_s:t_e]
                    self.start_distance += ch_s * self.dx
            
            elif stype == "Downsample":
                ds_space = int(step.get('space', 1))
                ds_time = int(step.get('time', 1))
                ds_space = max(1, ds_space)
                ds_time = max(1, ds_time)
                
                if ds_space > 1 or ds_time > 1:
                    data = data[::ds_space, ::ds_time]
                    self.dx *= ds_space
                    self.dt *= ds_time
                    # Re-calc nyquist after downsampling
                    fs = 1.0 / self.dt
                    nyquist = 0.5 * fs

            elif stype == "Detrend":
                axis = step.get('axis', 1) # 1 for time
                data = signal.detrend(data, axis=axis)

            elif stype == "Normalize":
                mode = step.get('mode', 'Global Z-Score')
                if mode == 'Global Z-Score':
                    mean = np.mean(data)
                    std = np.std(data)
                    if std > 0: data = (data - mean) / std
                elif mode == 'Channel Z-Score':
                    means = np.mean(data, axis=1, keepdims=True)
                    stds = np.std(data, axis=1, keepdims=True)
                    stds[stds == 0] = 1.0
                    data = (data - means) / stds
                elif mode == 'Time Z-Score':
                    means = np.mean(data, axis=0, keepdims=True)
                    stds = np.std(data, axis=0, keepdims=True)
                    stds[stds == 0] = 1.0
                    data = (data - means) / stds

            # --- Filtering ---
            elif stype == "Bandpass":
                low_hz = step.get('low', 10.0)
                high_hz = step.get('high', 100.0)
                ftype = step.get('filter_type', 'Butterworth')
                order = int(step.get('order', 4))
                
                low = np.clip(low_hz, 0.001, nyquist - 0.002)
                high = np.clip(high_hz, low + 0.001, nyquist - 0.001)
                
                try:
                    b, a = self._get_filter_coeffs(ftype, order, [low/nyquist, high/nyquist], btype='band')
                    data = signal.filtfilt(b, a, data, axis=1)
                except Exception as e:
                    print(f"Filter error: {e}")

            elif stype == "Lowpass":
                cutoff_hz = step.get('cutoff', 50.0)
                ftype = step.get('filter_type', 'Butterworth')
                order = int(step.get('order', 4))
                
                cutoff = np.clip(cutoff_hz, 0.001, nyquist - 0.001)
                
                try:
                    b, a = self._get_filter_coeffs(ftype, order, cutoff/nyquist, btype='low')
                    data = signal.filtfilt(b, a, data, axis=1)
                except Exception as e:
                    print(f"Filter error: {e}")

            elif stype == "Highpass":
                cutoff_hz = step.get('cutoff', 50.0)
                ftype = step.get('filter_type', 'Butterworth')
                order = int(step.get('order', 4))
                
                cutoff = np.clip(cutoff_hz, 0.001, nyquist - 0.001)
                
                try:
                    b, a = self._get_filter_coeffs(ftype, order, cutoff/nyquist, btype='high')
                    data = signal.filtfilt(b, a, data, axis=1)
                except Exception as e:
                    print(f"Filter error: {e}")

            elif stype == "Kalman Filter":
                Q = step.get('Q', 1e-5)
                R = step.get('R', 1e-2)
                data = self._apply_kalman_filter(data, Q, R)

            elif stype == "FK Filter":
                v_min = step.get('min_velocity', -3000)
                v_max = step.get('max_velocity', 3000)
                
                # Compute FK
                f_k_spectrum = fftshift(fft2(data))
                
                rows, cols = data.shape
                # k axis (along rows, spatial) -> 1/m
                k_freq = fftshift(np.fft.fftfreq(rows, d=self.dx))
                # f axis (along cols, temporal) -> 1/s
                f_freq = fftshift(np.fft.fftfreq(cols, d=self.dt))
                
                # Create meshgrid (indexing='ij' for matrix indexing)
                K, F = np.meshgrid(k_freq, f_freq, indexing='ij')
                
                # Calculate Velocity V = F / K
                with np.errstate(divide='ignore', invalid='ignore'):
                    V = F / K
                
                # Mask
                # Initialize mask with False
                mask = np.zeros_like(V, dtype=bool)
                
                # Valid velocities
                mask = (V >= v_min) & (V <= v_max)
                
                # Handle DC component (F=0, K=0) -> V is NaN
                # Usually we want to preserve DC
                center_row, center_col = rows // 2, cols // 2
                mask[center_row, center_col] = True
                
                # Handle K=0 axis (F axis, Infinite Velocity)
                # If range includes large values, maybe we should include it?
                # Typically velocity filters are wedge filters removing low velocities (noise) or high velocities.
                # If K is close to 0, V is large.
                # If the user specifies a range like -3000 to 3000, they want to KEEP low velocities and REJECT high velocities?
                # Or usually reject Surface Waves (low velocity) and keep Body Waves (high velocity)?
                # Or reject aliasing?
                # Let's stick to strict inequality. If V is Inf, it's not <= 3000. So it gets filtered out.
                # If user sets v_max to huge number, it might be included? No, Inf > huge.
                
                # Apply mask
                data = np.real(ifft2(ifftshift(f_k_spectrum * mask)))

            elif stype == "FK Mag Threshold":
                # Same as FK Filter? Or different logic? 
                # User asked for "FK Mag Threshold" node previously.
                # Assuming same logic as FK Filter above.
                thresh = step.get('threshold', 0.0)
                if thresh > 0:
                    f_k_spectrum = fftshift(fft2(data))
                    magnitude = np.abs(f_k_spectrum)
                    max_mag = np.max(magnitude)
                    if max_mag > 0:
                        mask = magnitude >= (thresh * max_mag)
                        data = np.real(ifft2(ifftshift(f_k_spectrum * mask)))
            
            elif stype == "Time Threshold":
                thresh = step.get('threshold', 0.0)
                if thresh > 0:
                    mag = np.abs(data)
                    max_mag = np.max(mag)
                    if max_mag > 0:
                        mask = mag >= (thresh * max_mag)
                        data *= mask
            
            elif stype == "Freq Threshold":
                thresh = step.get('threshold', 0.0)
                if thresh > 0:
                    spectrum = fft(data, axis=1)
                    mag = np.abs(spectrum)
                    max_mag = np.max(mag)
                    if max_mag > 0:
                        mask = mag >= (thresh * max_mag)
                        spectrum *= mask
                        data = np.real(ifft(spectrum, axis=1))

            elif stype == "Envelope":
                # Compute envelope using Hilbert transform along time axis (axis=1)
                data = np.abs(signal.hilbert(data, axis=1))

        self.processed_data = data
        return self.processed_data
