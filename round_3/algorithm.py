"""
IMC Prosperity 4 — Round 3 submission.

Products: HYDROGEL_PACK (HP), VELVETFRUIT_EXTRACT (VF), and ten VEV_*
vouchers (call options on VF, strikes 4000-6500).

Architecture:
- Per-product fair-value estimators routed to one of three quoting paths:
    1. trade_delta1 — delta-1 market making for HP / VF / ITM vouchers
    2. trade_delta1_makeonly — quote-only variant used on HP
    3. trade_option_voucher — Black-Scholes fair with rolling IV calibration
       and a smoothed Z-score overlay for the OTM voucher chain
    4. trade_voucher_smile — quadratic-fit IV smile for selected strikes
- Size-weighted mid (SWMID) used as the mid-input for vouchers, HP and VF
- Wall-mid quote anchors on voucher MAKE
- Per-product MM edges and per-tick size caps

Final algorithm PnL: -403 (rank 2509).
"""

from math import log, sqrt, erf
import json
from typing import Dict, List, Optional
from datamodel import Order, OrderDepth, TradingState


POSITION_LIMITS = {
    "HYDROGEL_PACK": 200, "VELVETFRUIT_EXTRACT": 200,
    "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300, "VEV_5100": 300,
    "VEV_5200": 300, "VEV_5300": 300, "VEV_5400": 300, "VEV_5500": 300,
    "VEV_6000": 300, "VEV_6500": 300,
}

STRIKES = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000, "VEV_5100": 5100,
    "VEV_5200": 5200, "VEV_5300": 5300, "VEV_5400": 5400, "VEV_5500": 5500,
    "VEV_6000": 6000, "VEV_6500": 6500,
}

DELTA1_VOUCHERS = ["VEV_4000", "VEV_4500"]
OPTION_VOUCHERS = ["VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]

EDGES = {
    "HYDROGEL_PACK": 2.3,
    "VELVETFRUIT_EXTRACT": 1.4,
    "VEV_4000": 1.5,
    "VEV_4500": 1.5,
    "VEV_5000": 1.3,
    "VEV_5100": 1.2,
    "VEV_5200": 1.0,
    "VEV_5300": 0.8,
    "VEV_5400": 0.7,
    "VEV_5500": 0.6,
}

HP_ANCHOR = 9990
HP_BAND = 20

SIZE_CAP_FRAC = {
    "HYDROGEL_PACK": 0.5,
    "VELVETFRUIT_EXTRACT": 0.5,
    "VEV_4000": 0.3, "VEV_4500": 0.3,
    "VEV_5000": 0.15, "VEV_5100": 0.15, "VEV_5200": 0.15,
    "VEV_5300": 0.15, "VEV_5400": 0.15, "VEV_5500": 0.15,
}

ZSCORE_PERIOD = 100
SMOOTHING_PERIOD = 20
ZSCORE_THRESHOLD_LONG = 1.8
ZSCORE_THRESHOLD_SHORT = 2.0

SIGMA_WINDOW = 25
MIN_SIGMA_SAMPLES = 5

TTE_DAYS_AT_START = 5.0
TIMESTAMPS_PER_DAY = 1_000_000

SMILE_STRIKES = {5000, 5100}

MIN_IV = 0.05
MAX_IV = 1.0

SMILE_TAKE_EDGE = 3.0

STRIKE_IV_CORRECTION_BID = {5000: -0.007, 5100: +0.005}
STRIKE_IV_CORRECTION_ASK = {5000: +0.003, 5100: -0.005}

SMILE_WINDOW = 200
SMILE_REFIT_EVERY = 10
MIN_SMILE_SAMPLES = 30
FALLBACK_SIGMA = 0.25


# ----------------------------------------------------------------------------
# Black-Scholes (embedded; no external deps on the platform)
# ----------------------------------------------------------------------------
def _N(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, S - K)
    d1 = (log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return S * _N(d1) - K * _N(d2)


def implied_vol(market_px: float, S: float, K: float, T: float) -> Optional[float]:
    """Bisection IV solver. Returns None if price is below intrinsic."""
    intrinsic = max(0.0, S - K)
    if market_px <= intrinsic + 0.01 or market_px >= S:
        return None
    lo, hi = 0.0001, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if bs_call(S, K, T, mid) > market_px:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-6:
            break
    return (lo + hi) / 2.0


# ----------------------------------------------------------------------------
# Order-book utilities
# ----------------------------------------------------------------------------
def best_levels(od: OrderDepth):
    if not od.buy_orders or not od.sell_orders:
        return None, None
    return max(od.buy_orders.keys()), min(od.sell_orders.keys())


def voucher_swmid(od):
    """Size-weighted mid — weights toward the lower-liquidity side."""
    if not od.buy_orders or not od.sell_orders:
        return None
    bb = max(od.buy_orders.keys())
    ba = min(od.sell_orders.keys())
    bv = od.buy_orders[bb]
    av = abs(od.sell_orders[ba])
    if bv + av <= 0:
        return (bb + ba) / 2.0
    return (bv * ba + av * bb) / (bv + av)


def rolling_median(values: list) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def rolling_mean(values: list) -> float:
    return sum(values) / len(values) if values else 0.0


def rolling_std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    m = rolling_mean(values)
    return (sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5


# ----------------------------------------------------------------------------
# Quadratic fit (3x3 solve, no numpy)
# ----------------------------------------------------------------------------
def fit_quadratic(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    Sx = sum(xs)
    Sx2 = sum(x * x for x in xs)
    Sx3 = sum(x * x * x for x in xs)
    Sx4 = sum(x * x * x * x for x in xs)
    Sy = sum(ys)
    Sxy = sum(x * y for x, y in zip(xs, ys))
    Sx2y = sum(x * x * y for x, y in zip(xs, ys))

    def det3(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))

    M = [[Sx4, Sx3, Sx2], [Sx3, Sx2, Sx], [Sx2, Sx, n]]
    r = [Sx2y, Sxy, Sy]
    d = det3(M)
    if abs(d) < 1e-12:
        return None

    def rc(col):
        return [[r[i] if j == col else M[i][j] for j in range(3)] for i in range(3)]

    return det3(rc(0)) / d, det3(rc(1)) / d, det3(rc(2)) / d


# ----------------------------------------------------------------------------
# Trader
# ----------------------------------------------------------------------------
class Trader:
    _tte_override: Optional[float] = None

    def bid(self):
        return 5000

    # ------------------------------------------------------------------------
    # Delta-1 MM with an aggressive amplifier driven by an external z-score signal
    # ------------------------------------------------------------------------
    def trade_delta1_aggressive(self, symbol: str, od: OrderDepth, position: int,
                                 fair: float, edge: float, vf_zscore):
        orders = []
        pos_limit = POSITION_LIMITS[symbol]
        bb, ba = best_levels(od)
        if bb is None:
            return orders

        buy_vol = 0
        sell_vol = 0

        if vf_zscore is not None and vf_zscore < -1.5:
            for ap in sorted(od.sell_orders.keys()):
                if ap > fair + 5:
                    break
                avail = abs(od.sell_orders[ap])
                cap = pos_limit - position - buy_vol
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, ap, q))
                    buy_vol += q

        if vf_zscore is not None and vf_zscore > 2.0:
            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp < fair - 5:
                    break
                avail = od.buy_orders[bp]
                cap = pos_limit + position - sell_vol
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, bp, -q))
                    sell_vol += q

        for ap in sorted(od.sell_orders.keys()):
            if ap >= fair - edge:
                break
            avail = abs(od.sell_orders[ap])
            cap = pos_limit - position - buy_vol
            q = min(avail, cap)
            if q > 0:
                orders.append(Order(symbol, ap, q))
                buy_vol += q

        if position + buy_vol < 0:
            for ap in sorted(od.sell_orders.keys()):
                if ap > fair + 0.5:
                    break
                if ap < fair - edge:
                    continue
                avail = abs(od.sell_orders[ap])
                cap = min(abs(position + buy_vol), pos_limit - position - buy_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, ap, q))
                    buy_vol += q

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp <= fair + edge:
                break
            avail = od.buy_orders[bp]
            cap = pos_limit + position - sell_vol
            q = min(avail, cap)
            if q > 0:
                orders.append(Order(symbol, bp, -q))
                sell_vol += q

        my_bid_candidates = [bb + 1, int(round(fair - edge))]
        my_ask_candidates = [ba - 1, int(round(fair + edge))]
        my_bid = min(my_bid_candidates)
        my_ask = max(my_ask_candidates)

        if my_bid >= my_ask:
            my_bid = int(round(fair)) - 1
            my_ask = int(round(fair)) + 1

        buy_cap = pos_limit - position - buy_vol
        sell_cap = pos_limit + position - sell_vol
        pos_after = position + buy_vol - sell_vol
        pos_ratio = pos_after / pos_limit
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(symbol, 0.3))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        if buy_cap > 0:
            orders.append(Order(symbol, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(symbol, int(my_ask), -sell_cap))

        return orders

    # ------------------------------------------------------------------------
    # Delta-1 MM with TAKE on mispricing + break-even unwind + position-skewed MAKE
    # ------------------------------------------------------------------------
    def trade_delta1(self, symbol: str, od: OrderDepth, position: int,
                     fair: float, edge: float):
        orders = []
        pos_limit = POSITION_LIMITS[symbol]
        bb, ba = best_levels(od)
        if bb is None:
            return orders

        buy_vol = 0
        sell_vol = 0

        for ap in sorted(od.sell_orders.keys()):
            if ap >= fair - edge:
                break
            avail = abs(od.sell_orders[ap])
            cap = pos_limit - position - buy_vol
            q = min(avail, cap)
            if q > 0:
                orders.append(Order(symbol, ap, q))
                buy_vol += q

        if position + buy_vol < 0:
            for ap in sorted(od.sell_orders.keys()):
                if ap > fair + 0.5:
                    break
                if ap < fair - edge:
                    continue
                avail = abs(od.sell_orders[ap])
                cap = min(abs(position + buy_vol), pos_limit - position - buy_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, ap, q))
                    buy_vol += q

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp <= fair + edge:
                break
            avail = od.buy_orders[bp]
            cap = pos_limit + position - sell_vol
            q = min(avail, cap)
            if q > 0:
                orders.append(Order(symbol, bp, -q))
                sell_vol += q

        if position - sell_vol > 0:
            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp < fair - 0.5:
                    break
                if bp > fair + edge:
                    continue
                avail = od.buy_orders[bp]
                cap = min(position - sell_vol, pos_limit + position - sell_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, bp, -q))
                    sell_vol += q

        my_bid_candidates = [bb + 1, int(round(fair - edge))]
        my_ask_candidates = [ba - 1, int(round(fair + edge))]
        my_bid = min(my_bid_candidates)
        my_ask = max(my_ask_candidates)

        if my_bid >= my_ask:
            my_bid = int(round(fair)) - 1
            my_ask = int(round(fair)) + 1

        buy_cap = pos_limit - position - buy_vol
        sell_cap = pos_limit + position - sell_vol

        pos_after = position + buy_vol - sell_vol
        pos_ratio = pos_after / pos_limit
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(symbol, 0.3))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        if buy_cap > 0:
            orders.append(Order(symbol, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(symbol, int(my_ask), -sell_cap))

        return orders

    # ------------------------------------------------------------------------
    # MAKE-only variant — skips TAKE entirely; retains a conservative break-even unwind
    # ------------------------------------------------------------------------
    def trade_delta1_makeonly(self, symbol: str, od: OrderDepth, position: int,
                              fair: float, edge: float):
        orders = []
        pos_limit = POSITION_LIMITS[symbol]
        bb, ba = best_levels(od)
        if bb is None:
            return orders

        sell_vol = 0
        buy_vol = 0

        if position < 0:
            for ap in sorted(od.sell_orders.keys()):
                if ap > fair + 0.5: break
                if ap < fair - edge: continue
                avail = abs(od.sell_orders[ap])
                cap = min(abs(position), pos_limit - position - buy_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, ap, q))
                    buy_vol += q

        if position > 0:
            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp < fair - 0.5: break
                if bp > fair + edge: continue
                avail = od.buy_orders[bp]
                cap = min(position, pos_limit + position - sell_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, bp, -q))
                    sell_vol += q

        my_bid = min(bb + 1, int(round(fair - edge)))
        my_ask = max(ba - 1, int(round(fair + edge)))
        if my_bid >= my_ask:
            my_bid = int(round(fair)) - 1
            my_ask = int(round(fair)) + 1

        buy_cap = pos_limit - position - buy_vol
        sell_cap = pos_limit + position - sell_vol
        pos_after = position + buy_vol - sell_vol
        pos_ratio = pos_after / pos_limit
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(symbol, 0.3))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        if buy_cap > 0:
            orders.append(Order(symbol, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(symbol, int(my_ask), -sell_cap))

        return orders


    # ------------------------------------------------------------------------
    # Voucher MM: BS fair with rolling-mean IV + smoothed Z-score overlay
    # ------------------------------------------------------------------------
    def trade_option_voucher(self, symbol: str, od: OrderDepth, position: int,
                             vf_mid: float, tte_years: float, state: dict):
        orders = []
        pos_limit = POSITION_LIMITS[symbol]
        strike = STRIKES[symbol]

        bb, ba = best_levels(od)
        if bb is None or vf_mid is None:
            return orders

        voucher_mid = voucher_swmid(od) or ((bb + ba) / 2.0)

        cur_iv = implied_vol(voucher_mid, vf_mid, strike, tte_years)
        iv_key = f"iv_{symbol}"
        iv_hist = state.get(iv_key, [])
        if cur_iv is not None:
            iv_hist.append(cur_iv)
            if len(iv_hist) > SIGMA_WINDOW:
                iv_hist = iv_hist[-SIGMA_WINDOW:]
            state[iv_key] = iv_hist

        if len(iv_hist) < MIN_SIGMA_SAMPLES:
            return orders

        sigma = rolling_mean(iv_hist)

        fair = bs_call(vf_mid, strike, tte_years, sigma)
        if fair < 0.5 or fair > vf_mid:
            return orders

        price_key = f"price_{symbol}"
        price_hist = state.get(price_key, [])
        price_hist.append(voucher_mid)
        required = ZSCORE_PERIOD + SMOOTHING_PERIOD
        if len(price_hist) > required:
            price_hist = price_hist[-required:]
        state[price_key] = price_hist

        zscore = None
        if len(price_hist) >= ZSCORE_PERIOD:
            recent_window = price_hist[-ZSCORE_PERIOD - SMOOTHING_PERIOD + 1:] if len(price_hist) >= ZSCORE_PERIOD + SMOOTHING_PERIOD - 1 else None
            if recent_window and len(recent_window) >= ZSCORE_PERIOD + SMOOTHING_PERIOD - 1:
                z_values = []
                for i in range(SMOOTHING_PERIOD):
                    window = recent_window[i:i + ZSCORE_PERIOD]
                    m = rolling_mean(window)
                    sd = rolling_std(window)
                    if sd > 1e-6:
                        z_values.append((window[-1] - m) / sd)
                if z_values:
                    zscore = rolling_mean(z_values)

        edge = EDGES.get(symbol, 1.0)
        buy_vol = 0
        sell_vol = 0

        for ap in sorted(od.sell_orders.keys()):
            if ap >= fair - edge:
                break
            avail = abs(od.sell_orders[ap])
            cap = pos_limit - position - buy_vol
            q = min(avail, cap)
            if q > 0:
                orders.append(Order(symbol, ap, q))
                buy_vol += q

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp <= fair + edge:
                break
            avail = od.buy_orders[bp]
            cap = pos_limit + position - sell_vol
            q = min(avail, cap)
            if q > 0:
                orders.append(Order(symbol, bp, -q))
                sell_vol += q

        if zscore is not None:
            if zscore < -ZSCORE_THRESHOLD_LONG and position + buy_vol < pos_limit:
                for ap in sorted(od.sell_orders.keys()):
                    if ap > fair + edge:
                        break
                    avail = abs(od.sell_orders[ap])
                    cap = pos_limit - position - buy_vol
                    q = min(avail, cap, int(pos_limit * 0.2))
                    if q > 0:
                        orders.append(Order(symbol, ap, q))
                        buy_vol += q
                        break
            elif zscore > ZSCORE_THRESHOLD_SHORT and position - sell_vol > -pos_limit:
                for bp in sorted(od.buy_orders.keys(), reverse=True):
                    if bp < fair - edge:
                        break
                    avail = od.buy_orders[bp]
                    cap = pos_limit + position - sell_vol
                    q = min(avail, cap, int(pos_limit * 0.1))
                    if q > 0:
                        orders.append(Order(symbol, bp, -q))
                        sell_vol += q
                        break

        # Wall-mid anchor for the MAKE quote
        bid_wall = min(od.buy_orders.keys()) if od.buy_orders else bb
        ask_wall = max(od.sell_orders.keys()) if od.sell_orders else ba
        my_bid_candidates = [bid_wall + 1, int(round(fair - edge))]
        my_ask_candidates = [ask_wall - 1, int(round(fair + edge))]
        my_bid = min(my_bid_candidates)
        my_ask = max(my_ask_candidates)

        if my_bid >= my_ask:
            my_bid = int(round(fair)) - 1
            my_ask = int(round(fair)) + 1
        if my_bid < 1:
            my_bid = 1

        buy_cap = pos_limit - position - buy_vol
        sell_cap = pos_limit + position - sell_vol

        pos_after = position + buy_vol - sell_vol
        pos_ratio = pos_after / pos_limit
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(symbol, 0.15))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        if buy_cap > 0:
            orders.append(Order(symbol, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(symbol, int(my_ask), -sell_cap))

        return orders

    # ------------------------------------------------------------------------
    # Smile fit — pools IV samples across strikes, refits quadratic bid/ask curves
    # ------------------------------------------------------------------------
    def update_smile(self, state: dict, vf_mid: float, tte_years: float,
                     voucher_books):
        smile_data = state.get('smile_data', [])

        for sym in ["VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]:
            if sym not in voucher_books:
                continue
            od = voucher_books[sym]
            bb, ba = best_levels(od)
            if bb is None:
                continue
            strike = STRIKES[sym]
            iv_bid = implied_vol(bb, vf_mid, strike, tte_years)
            iv_ask = implied_vol(ba, vf_mid, strike, tte_years)
            if iv_bid is None or iv_ask is None:
                continue
            if iv_bid < MIN_IV or iv_bid > MAX_IV:
                continue
            if iv_ask < MIN_IV or iv_ask > MAX_IV:
                continue
            m_t = log(strike / vf_mid) / sqrt(tte_years)
            smile_data.append((m_t, iv_bid, iv_ask))

        if len(smile_data) > SMILE_WINDOW:
            smile_data = smile_data[-SMILE_WINDOW:]
        state['smile_data'] = smile_data

        last_fit_size = state.get('smile_last_fit_size', 0)
        if len(smile_data) >= MIN_SMILE_SAMPLES and \
           len(smile_data) - last_fit_size >= SMILE_REFIT_EVERY:
            m_ts = [d[0] for d in smile_data]
            iv_bids = [d[1] for d in smile_data]
            iv_asks = [d[2] for d in smile_data]

            bid_fit = fit_quadratic(m_ts, iv_bids)
            ask_fit = fit_quadratic(m_ts, iv_asks)

            if bid_fit is not None and ask_fit is not None:
                state['smile_coefs'] = {
                    'a_bid': bid_fit[0], 'b_bid': bid_fit[1], 'c_bid': bid_fit[2],
                    'a_ask': ask_fit[0], 'b_ask': ask_fit[1], 'c_ask': ask_fit[2],
                }
                state['smile_last_fit_size'] = len(smile_data)

    # ------------------------------------------------------------------------
    # Smile-priced voucher MM (uses the quadratic fit above)
    # ------------------------------------------------------------------------
    def trade_voucher_smile(self, symbol: str, od: OrderDepth, position: int,
                            vf_mid: float, tte_years: float, state: dict):
        orders = []
        pos_limit = POSITION_LIMITS[symbol]
        strike = STRIKES[symbol]

        bb, ba = best_levels(od)
        if bb is None or vf_mid is None:
            return orders

        coefs = state.get('smile_coefs')
        if coefs is None:
            iv_bid_pred = FALLBACK_SIGMA
            iv_ask_pred = FALLBACK_SIGMA
        else:
            m_t = log(strike / vf_mid) / sqrt(tte_years)
            iv_bid_pred = coefs['a_bid'] * m_t * m_t + coefs['b_bid'] * m_t + coefs['c_bid']
            iv_ask_pred = coefs['a_ask'] * m_t * m_t + coefs['b_ask'] * m_t + coefs['c_ask']
            iv_bid_pred += STRIKE_IV_CORRECTION_BID.get(strike, 0.0)
            iv_ask_pred += STRIKE_IV_CORRECTION_ASK.get(strike, 0.0)
            iv_bid_pred = max(MIN_IV, min(MAX_IV, iv_bid_pred))
            iv_ask_pred = max(MIN_IV, min(MAX_IV, iv_ask_pred))

        pred_bid_price = bs_call(vf_mid, strike, tte_years, iv_bid_pred)
        pred_ask_price = bs_call(vf_mid, strike, tte_years, iv_ask_pred)

        if pred_bid_price < 0.5 or pred_ask_price < 0.5 or pred_ask_price <= pred_bid_price:
            voucher_mid = voucher_swmid(od) or ((bb + ba) / 2.0)
            pred_bid_price = voucher_mid - 1
            pred_ask_price = voucher_mid + 1

        pred_mid = (pred_bid_price + pred_ask_price) / 2.0

        # Warmup guard — wait for smile to mature before TAKE-ing
        smile_samples = len(state.get('smile_data', []))
        smile_matured = smile_samples >= 100

        price_key = f"price_{symbol}"
        price_hist = state.get(price_key, [])
        voucher_mid = voucher_swmid(od) or ((bb + ba) / 2.0)
        price_hist.append(voucher_mid)
        max_len = ZSCORE_PERIOD + SMOOTHING_PERIOD + 10
        if len(price_hist) > max_len:
            price_hist = price_hist[-max_len:]
        state[price_key] = price_hist

        zscore = None
        if len(price_hist) >= ZSCORE_PERIOD + SMOOTHING_PERIOD - 1:
            start_base = len(price_hist) - ZSCORE_PERIOD - SMOOTHING_PERIOD + 1
            z_values = []
            for i in range(SMOOTHING_PERIOD):
                start = start_base + i
                window = price_hist[start:start + ZSCORE_PERIOD]
                m = rolling_mean(window)
                sd = rolling_std(window)
                if sd > 1e-6:
                    z_values.append((window[-1] - m) / sd)
            if z_values:
                zscore = rolling_mean(z_values)

        buy_vol = 0
        sell_vol = 0

        if smile_matured:
            for ap in sorted(od.sell_orders.keys()):
                if ap >= pred_bid_price - SMILE_TAKE_EDGE:
                    break
                avail = abs(od.sell_orders[ap])
                cap = pos_limit - position - buy_vol
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, ap, q))
                    buy_vol += q

            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp <= pred_ask_price + SMILE_TAKE_EDGE:
                    break
                avail = od.buy_orders[bp]
                cap = pos_limit + position - sell_vol
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(symbol, bp, -q))
                    sell_vol += q

        if zscore is not None:
            pos_cur = position + buy_vol - sell_vol
            pos_ratio = pos_cur / pos_limit
            if zscore < -ZSCORE_THRESHOLD_LONG:
                intensity = min(abs(zscore) - ZSCORE_THRESHOLD_LONG, 2.0) / 2.0
                if pos_ratio > 0.3: intensity *= 0.3
                elif pos_ratio > 0.1: intensity *= 0.6
                z_size = int(pos_limit * 0.40 * intensity)
                if z_size > 0 and od.sell_orders:
                    best_ask = min(od.sell_orders.keys())
                    if best_ask <= pred_ask_price:
                        avail = abs(od.sell_orders[best_ask])
                        cap = pos_limit - position - buy_vol
                        q = min(avail, cap, z_size)
                        if q > 0:
                            orders.append(Order(symbol, best_ask, q))
                            buy_vol += q
            elif zscore > ZSCORE_THRESHOLD_SHORT:
                intensity = min(abs(zscore) - ZSCORE_THRESHOLD_SHORT, 2.0) / 2.0
                if pos_ratio < -0.3: intensity *= 0.3
                elif pos_ratio < -0.1: intensity *= 0.6
                z_size = int(pos_limit * 0.20 * intensity)
                if z_size > 0 and od.buy_orders:
                    best_bid = max(od.buy_orders.keys())
                    if best_bid >= pred_bid_price:
                        avail = od.buy_orders[best_bid]
                        cap = pos_limit + position - sell_vol
                        q = min(avail, cap, z_size)
                        if q > 0:
                            orders.append(Order(symbol, best_bid, -q))
                            sell_vol += q

        bid_wall = min(od.buy_orders.keys()) if od.buy_orders else bb
        ask_wall = max(od.sell_orders.keys()) if od.sell_orders else ba
        my_bid = max(bid_wall + 1, int(pred_bid_price))
        my_ask = min(ask_wall - 1, int(pred_ask_price) + 1)

        if my_bid > pred_mid - 0.3:
            my_bid = int(pred_mid - 0.5)
        if my_ask < pred_mid + 0.3:
            my_ask = int(pred_mid + 0.5) + 1

        if my_bid >= my_ask:
            my_bid = int(pred_mid) - 1
            my_ask = int(pred_mid) + 1
        if my_bid < 1:
            my_bid = 1

        buy_cap = pos_limit - position - buy_vol
        sell_cap = pos_limit + position - sell_vol
        pos_after = position + buy_vol - sell_vol
        pos_ratio = pos_after / pos_limit
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(symbol, 0.15))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        if buy_cap > 0:
            orders.append(Order(symbol, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(symbol, int(my_ask), -sell_cap))

        return orders

    # ------------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------------
    def run(self, state: TradingState):
        try:
            trader_state = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_state = {}

        result: Dict[str, List[Order]] = {}

        vf_mid = None
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            _od_vf = state.order_depths["VELVETFRUIT_EXTRACT"]
            bb, ba = best_levels(_od_vf)
            if bb is not None:
                vf_mid = voucher_swmid(_od_vf) or ((bb + ba) / 2.0)

        # Track a rolling Z-score on VF mid (consumed by the delta-1 amplifier)
        vf_hist = trader_state.get('vf_price_hist', [])
        if vf_mid is not None:
            vf_hist.append(vf_mid)
            max_len = ZSCORE_PERIOD + SMOOTHING_PERIOD + 10
            if len(vf_hist) > max_len:
                vf_hist = vf_hist[-max_len:]
            trader_state['vf_price_hist'] = vf_hist

        vf_zscore = None
        if len(vf_hist) >= ZSCORE_PERIOD + SMOOTHING_PERIOD - 1:
            start_base = len(vf_hist) - ZSCORE_PERIOD - SMOOTHING_PERIOD + 1
            z_values = []
            for i in range(SMOOTHING_PERIOD):
                start = start_base + i
                window = vf_hist[start:start + ZSCORE_PERIOD]
                m = rolling_mean(window)
                sd = rolling_std(window)
                if sd > 1e-6:
                    z_values.append((window[-1] - m) / sd)
            if z_values:
                vf_zscore = rolling_mean(z_values)

        start_tte = self._tte_override if self._tte_override is not None else TTE_DAYS_AT_START
        tte_days = max(0.1, start_tte - state.timestamp / TIMESTAMPS_PER_DAY)
        tte_years = tte_days / 365.0

        if vf_mid is not None:
            voucher_books = {sym: state.order_depths[sym] for sym in OPTION_VOUCHERS
                             if sym in state.order_depths}
            self.update_smile(trader_state, vf_mid, tte_years, voucher_books)

        # HP: hybrid fair — lean against the anchor only when L1_mid is far from it
        if "HYDROGEL_PACK" in state.order_depths:
            od = state.order_depths["HYDROGEL_PACK"]
            bb, ba = best_levels(od)
            if bb is not None:
                l1_mid = voucher_swmid(od) or ((bb + ba) / 2.0)
                if abs(l1_mid - HP_ANCHOR) > HP_BAND:
                    fair = HP_ANCHOR
                else:
                    fair = l1_mid
                result["HYDROGEL_PACK"] = self.trade_delta1_makeonly(
                    "HYDROGEL_PACK", od, state.position.get("HYDROGEL_PACK", 0),
                    fair, EDGES["HYDROGEL_PACK"])

        # VF fair shift toward the rolling-VWAP centre of gravity
        vf_trade_hist = trader_state.get('vf_trade_hist', [])
        for trd in state.market_trades.get("VELVETFRUIT_EXTRACT", []) or []:
            try:
                vf_trade_hist.append((trd.price, abs(trd.quantity)))
            except Exception:
                pass
        if len(vf_trade_hist) > 50:
            vf_trade_hist = vf_trade_hist[-50:]
        trader_state['vf_trade_hist'] = vf_trade_hist
        vf_fair_shift = 0.0
        if len(vf_trade_hist) >= 5 and vf_mid is not None:
            tot_q = sum(q for _, q in vf_trade_hist)
            if tot_q > 0:
                vwap = sum(p*q for p, q in vf_trade_hist) / tot_q
                dev = vf_mid - vwap
                if abs(dev) > 0.5:
                    vf_fair_shift = -0.3 * dev

        if "VELVETFRUIT_EXTRACT" in state.order_depths and vf_mid is not None:
            od = state.order_depths["VELVETFRUIT_EXTRACT"]
            result["VELVETFRUIT_EXTRACT"] = self.trade_delta1(
                "VELVETFRUIT_EXTRACT", od, state.position.get("VELVETFRUIT_EXTRACT", 0),
                vf_mid + vf_fair_shift, EDGES["VELVETFRUIT_EXTRACT"])

        # ITM voucher time-value mean-reversion shift
        tv_shifts = {}
        for _sym in ("VEV_4000", "VEV_4500"):
            if _sym not in state.order_depths or vf_mid is None:
                continue
            _od = state.order_depths[_sym]
            _bb, _ba = best_levels(_od)
            if _bb is None:
                continue
            _vou_mid = voucher_swmid(_od) or ((_bb + _ba) / 2.0)
            _intrinsic = max(0.0, vf_mid - STRIKES[_sym])
            _tv = _vou_mid - _intrinsic
            _tv_key = f"tv_hist_{_sym}"
            _tv_hist = trader_state.get(_tv_key, [])
            _tv_hist.append(_tv)
            if len(_tv_hist) > 200:
                _tv_hist = _tv_hist[-200:]
            trader_state[_tv_key] = _tv_hist
            if len(_tv_hist) >= 50:
                _tv_mean = sum(_tv_hist) / len(_tv_hist)
                tv_shifts[_sym] = -0.3 * (_tv - _tv_mean)

        for sym in DELTA1_VOUCHERS:
            if sym not in state.order_depths or vf_mid is None:
                continue
            strike = STRIKES[sym]
            fair = vf_mid - strike
            if fair <= 0:
                continue
            fair = fair + tv_shifts.get(sym, 0.0)
            result[sym] = self.trade_delta1_aggressive(
                sym, state.order_depths[sym], state.position.get(sym, 0),
                fair, EDGES[sym], vf_zscore)

        for sym in OPTION_VOUCHERS:
            if sym not in state.order_depths or vf_mid is None:
                continue
            strike = STRIKES[sym]
            if strike in SMILE_STRIKES:
                result[sym] = self.trade_voucher_smile(
                    sym, state.order_depths[sym], state.position.get(sym, 0),
                    vf_mid, tte_years, trader_state)
            else:
                result[sym] = self.trade_option_voucher(
                    sym, state.order_depths[sym], state.position.get(sym, 0),
                    vf_mid, tte_years, trader_state)

        return result, 0, json.dumps(trader_state)
