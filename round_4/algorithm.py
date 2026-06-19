"""
IMC Prosperity 4 — Round 4 submission.

Products: HYDROGEL_PACK (HP), VELVETFRUIT_EXTRACT (VF), and twelve VEV_*
vouchers (call options on VF, strikes 4000-6500).

Architecture:
- A single ``Trader.run`` entrypoint composes per-product quoting layers
  (``HydrogelTrader``, ``VelvetfruitExtractTrader``, ``VoucherTrader``)
  against a centralised ``RiskManager`` that enforces position-limit, net
  voucher-delta, end-of-day taper, drawdown-halt and inventory-skew rules.
- The voucher chain is routed: intrinsic-fair for deep ITM, Black-Scholes
  with rolling-median IV for moderate moneyness, smile-fit (pooled
  quadratic) for near-ATM, and a passive-only fallback for deep OTM.
- A pluggable ``CounterpartyEngine`` (default OFF) accepts a JSON bot
  profile table for counterparty-aware sizing.

Final algorithm PnL: +42,475 (rank 930).
"""

from math import log, sqrt, erf
import json
from typing import Dict, List, Optional, Tuple
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
OPTION_VOUCHERS = ["VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300",
                   "VEV_5400", "VEV_5500"]
DEAD_STRIKES = {6000, 6500}
ALL_VOUCHERS = list(STRIKES.keys())

EDGES = {
    "HYDROGEL_PACK": 2.3,
    "VELVETFRUIT_EXTRACT": 1.4,
    "VEV_4000": 1.5, "VEV_4500": 1.5,
    "VEV_5000": 1.3, "VEV_5100": 1.2, "VEV_5200": 1.0,
    "VEV_5300": 0.8, "VEV_5400": 0.7, "VEV_5500": 0.6,
}

HP_ANCHOR = 9990
HP_BAND = 20

SIZE_CAP_FRAC = {
    "HYDROGEL_PACK": 0.5, "VELVETFRUIT_EXTRACT": 0.5,
    "VEV_4000": 0.3, "VEV_4500": 0.3,
    "VEV_5000": 0.15, "VEV_5100": 0.15, "VEV_5200": 0.15,
    "VEV_5300": 0.15, "VEV_5400": 0.15, "VEV_5500": 0.15,
}

ZSCORE_PERIOD = 100
SMOOTHING_PERIOD = 20
ZSCORE_THRESHOLD_LONG = 1.8
ZSCORE_THRESHOLD_SHORT = 2.0

SIGMA_WINDOW = 50
MIN_SIGMA_SAMPLES = 5

TTE_DAYS_AT_START = 4.0
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

# Risk-manager tuning constants
DELTA_CAP_VF = 50.0
HEDGE_RATIO = 0.5
TAPER_START = 950_000
TAPER_LEN   = 50_000
INVENTORY_THR = 0.7
INVENTORY_SHIFT = 0.5
DD_HALT = 5000.0

ENABLE_BOT_INTELLIGENCE = False
BOT_TABLE_JSON = ""


# ----------------------------------------------------------------------------
# Black-Scholes (embedded; no scipy on the platform)
# ----------------------------------------------------------------------------
def _N(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, S - K)
    d1 = (log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return S * _N(d1) - K * _N(d2)


def bs_delta(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return 1.0 if S > K else (0.5 if S == K else 0.0)
    d1 = (log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrt(T))
    return _N(d1)


def implied_vol(market_px: float, S: float, K: float, T: float) -> Optional[float]:
    """Bisection IV; None if market price violates the no-arbitrage bounds."""
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
def best_levels(od: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
    if not od.buy_orders or not od.sell_orders:
        return None, None
    return max(od.buy_orders.keys()), min(od.sell_orders.keys())


def voucher_swmid(od: OrderDepth) -> Optional[float]:
    """Size-weighted mid; weights toward the lower-liquidity side."""
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


def fit_quadratic(xs, ys):
    """3x3 normal-equations solve; returns (a, b, c) for y = a x^2 + b x + c."""
    n = len(xs)
    if n < 3:
        return None
    Sx = sum(xs); Sx2 = sum(x*x for x in xs); Sx3 = sum(x*x*x for x in xs); Sx4 = sum(x*x*x*x for x in xs)
    Sy = sum(ys); Sxy = sum(x*y for x, y in zip(xs, ys)); Sx2y = sum(x*x*y for x, y in zip(xs, ys))

    def det3(m):
        return (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
                - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
                + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))

    M = [[Sx4, Sx3, Sx2], [Sx3, Sx2, Sx], [Sx2, Sx, n]]
    r = [Sx2y, Sxy, Sy]
    d = det3(M)
    if abs(d) < 1e-12:
        return None

    def rc(col):
        return [[r[i] if j == col else M[i][j] for j in range(3)] for i in range(3)]

    return det3(rc(0)) / d, det3(rc(1)) / d, det3(rc(2)) / d


# ----------------------------------------------------------------------------
# CounterpartyEngine — parameterised, default OFF
# ----------------------------------------------------------------------------
class CounterpartyEngine:
    """Pluggable counterparty-classifier. No-op when disabled or when
    ``BOT_TABLE_JSON`` is empty."""

    def __init__(self, table_json: str, enabled: bool):
        self.enabled = enabled and bool(table_json)
        self.bot_class: Dict[Tuple[str, str], str] = {}
        self.bot_conf: Dict[Tuple[str, str], float] = {}
        if not self.enabled:
            return
        try:
            rows = json.loads(table_json)
        except Exception:
            self.enabled = False
            return
        for row in rows:
            try:
                bot = row.get("bot")
                product = row.get("product")
                cls = row.get("classification", "UNKNOWN")
                conf = float(row.get("confidence", 0.0))
                if bot and product and cls in ("INFORMED", "DUMB", "MM", "NOISE"):
                    self.bot_class[(bot, product)] = cls
                    self.bot_conf[(bot, product)] = conf
            except Exception:
                continue

    def flow_score(self, symbol: str, market_trades: list) -> Optional[float]:
        if not self.enabled:
            return None
        score = 0.0
        for tr in market_trades:
            qty = abs(getattr(tr, "quantity", 0))
            if qty == 0:
                continue
            buyer = getattr(tr, "buyer", None)
            seller = getattr(tr, "seller", None)
            for side, name in (("BUY", buyer), ("SELL", seller)):
                if not name:
                    continue
                cls = self.bot_class.get((name, symbol))
                if cls is None:
                    cls = self.bot_class.get((name, "ALL"))
                if cls is None:
                    continue
                conf = self.bot_conf.get((name, symbol), 0.5)
                if cls == "INFORMED":
                    score += (qty * conf) if side == "BUY" else -(qty * conf)
                elif cls == "DUMB":
                    score += -(qty * conf) if side == "BUY" else (qty * conf)
        return score


# ----------------------------------------------------------------------------
# RiskManager — pre-emit gate for net delta, EOD taper, drawdown, inventory shift
# ----------------------------------------------------------------------------
class RiskManager:
    def __init__(self, state: TradingState, persisted: dict):
        self.state = state
        self.persisted = persisted
        self.ts = state.timestamp

        self.net_delta_vf: float = 0.0
        self.voucher_deltas: Dict[str, float] = {}

        self.peak_pnl = float(persisted.get("peak_pnl", 0.0))
        self.cur_pnl = self._compute_mtm_pnl(persisted)
        if self.cur_pnl > self.peak_pnl:
            self.peak_pnl = self.cur_pnl
        self.dd = self.peak_pnl - self.cur_pnl
        self.dd_halt_active = self.dd > DD_HALT

        local_ts = self.ts % TIMESTAMPS_PER_DAY
        if local_ts < TAPER_START:
            self.taper_mult = 1.0
        else:
            self.taper_mult = max(0.0, 1.0 - (local_ts - TAPER_START) / TAPER_LEN)

    def _stable_mid(self, sym: str) -> Optional[float]:
        od = self.state.order_depths.get(sym)
        if od is None:
            return None
        bb, ba = best_levels(od)
        if bb is None:
            return None
        return (bb + ba) / 2.0

    def _compute_mtm_pnl(self, persisted: dict) -> float:
        cash_by_prod = dict(persisted.get("realized_cash", {}))
        for sym, trades in (self.state.own_trades or {}).items():
            for tr in trades:
                qty = abs(int(getattr(tr, "quantity", 0)))
                price = float(getattr(tr, "price", 0))
                if qty == 0:
                    continue
                buyer = getattr(tr, "buyer", None)
                seller = getattr(tr, "seller", None)
                if buyer == "SUBMISSION":
                    cash_by_prod[sym] = cash_by_prod.get(sym, 0.0) - qty * price
                elif seller == "SUBMISSION":
                    cash_by_prod[sym] = cash_by_prod.get(sym, 0.0) + qty * price
        persisted["realized_cash"] = cash_by_prod
        total = sum(cash_by_prod.values())
        for sym, pos in (self.state.position or {}).items():
            if pos == 0:
                continue
            mid = self._stable_mid(sym)
            if mid is None:
                continue
            total += pos * mid
        return total

    def compute_voucher_deltas(self, vf_mid: float, tte_years: float, iv_state: dict) -> None:
        """Per-strike delta from rolling IV (median); ITM-empirical fallback."""
        net = 0.0
        for sym, K in STRIKES.items():
            pos = self.state.position.get(sym, 0)
            if pos == 0 and sym not in self.state.order_depths:
                self.voucher_deltas[sym] = 0.0
                continue
            iv_key = f"iv_{sym}"
            iv_hist = iv_state.get(iv_key, [])
            if len(iv_hist) >= MIN_SIGMA_SAMPLES:
                sigma = rolling_median(iv_hist)
                d = bs_delta(vf_mid, K, tte_years, sigma)
            else:
                if K < vf_mid - 50:
                    d = 1.0
                elif K > vf_mid + 50:
                    d = 0.0
                else:
                    d = max(0.0, min(1.0, (vf_mid - K + 100) / 200.0))
            self.voucher_deltas[sym] = d
            net += pos * d
        self.net_delta_vf = net

    def vf_target_position(self) -> int:
        target = -HEDGE_RATIO * self.net_delta_vf
        lim = POSITION_LIMITS["VELVETFRUIT_EXTRACT"]
        return int(max(-lim, min(lim, target)))

    def can_increase_voucher_delta(self, sym: str, side: str, qty: int) -> int:
        if qty <= 0:
            return 0
        d = self.voucher_deltas.get(sym, 0.0)
        if d <= 0.001:
            return qty
        if side == "BUY":
            if self.net_delta_vf >= 0:
                room = max(0.0, DELTA_CAP_VF - self.net_delta_vf)
                max_q = int(room / d)
                return max(0, min(qty, max_q))
            return qty
        else:
            if self.net_delta_vf <= 0:
                room = max(0.0, DELTA_CAP_VF + self.net_delta_vf)
                max_q = int(room / d)
                return max(0, min(qty, max_q))
            return qty

    def apply_taper(self, qty: int, sym: str, position: int, side: str) -> int:
        if self.taper_mult >= 0.999:
            return qty
        if side == "BUY":
            increases_abs = position >= 0
        else:
            increases_abs = position <= 0
        if not increases_abs:
            return qty
        return int(qty * self.taper_mult)

    def block_due_to_drawdown(self, sym: str, position: int, side: str) -> bool:
        if not self.dd_halt_active:
            return False
        if side == "BUY":
            return position >= 0
        else:
            return position <= 0

    def inventory_fair_shift(self, sym: str, position: int, spread: float) -> float:
        lim = POSITION_LIMITS[sym]
        ratio = position / lim
        if abs(ratio) <= INVENTORY_THR:
            return 0.0
        excess = (abs(ratio) - INVENTORY_THR) / (1.0 - INVENTORY_THR)
        sign = -1.0 if ratio > 0 else 1.0
        return sign * INVENTORY_SHIFT * excess * max(spread, 1.0)

    def persist(self, persisted: dict) -> None:
        persisted["peak_pnl"] = self.peak_pnl
        persisted["last_pnl"] = self.cur_pnl


# ----------------------------------------------------------------------------
# BaseProductTrader — shared MAKE quote scaffold
# ----------------------------------------------------------------------------
class BaseProductTrader:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.pos_limit = POSITION_LIMITS[symbol]
        self.edge = EDGES.get(symbol, 1.0)

    def _make_quote(self, fair: float, edge: float, bb: int, ba: int,
                    position: int, buy_vol: int, sell_vol: int,
                    risk: RiskManager, side_buy_extra_skew: float = 1.0,
                    side_sell_extra_skew: float = 1.0,
                    size_cap_frac_override: Optional[float] = None
                    ) -> Tuple[Optional[Order], Optional[Order]]:
        my_bid_candidates = [bb + 1, int(round(fair - edge))]
        my_ask_candidates = [ba - 1, int(round(fair + edge))]
        my_bid = min(my_bid_candidates)
        my_ask = max(my_ask_candidates)
        if my_bid >= my_ask:
            my_bid = int(round(fair)) - 1
            my_ask = int(round(fair)) + 1
        if my_bid < 1:
            my_bid = 1

        buy_cap = self.pos_limit - position - buy_vol
        sell_cap = self.pos_limit + position - sell_vol

        pos_after = position + buy_vol - sell_vol
        pos_ratio = pos_after / self.pos_limit
        cap_frac = size_cap_frac_override if size_cap_frac_override is not None else SIZE_CAP_FRAC.get(self.symbol, 0.3)
        max_make = int(self.pos_limit * cap_frac)

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        buy_cap = int(buy_cap * side_buy_extra_skew)
        sell_cap = int(sell_cap * side_sell_extra_skew)

        buy_cap = risk.apply_taper(buy_cap, self.symbol, position, "BUY")
        sell_cap = risk.apply_taper(sell_cap, self.symbol, position, "SELL")

        if self.symbol in STRIKES:
            buy_cap = risk.can_increase_voucher_delta(self.symbol, "BUY", buy_cap)
            sell_cap = risk.can_increase_voucher_delta(self.symbol, "SELL", sell_cap)

        if risk.block_due_to_drawdown(self.symbol, position, "BUY"):
            buy_cap = 0
        if risk.block_due_to_drawdown(self.symbol, position, "SELL"):
            sell_cap = 0

        buy_order = Order(self.symbol, int(my_bid), buy_cap) if buy_cap > 0 else None
        sell_order = Order(self.symbol, int(my_ask), -sell_cap) if sell_cap > 0 else None
        return buy_order, sell_order


# ----------------------------------------------------------------------------
# HydrogelTrader — MAKE-only, hybrid anchor fair
# ----------------------------------------------------------------------------
class HydrogelTrader(BaseProductTrader):
    def __init__(self):
        super().__init__("HYDROGEL_PACK")

    def quote(self, state: TradingState, risk: RiskManager) -> List[Order]:
        orders: List[Order] = []
        od = state.order_depths.get(self.symbol)
        if od is None:
            return orders
        bb, ba = best_levels(od)
        if bb is None:
            return orders

        position = state.position.get(self.symbol, 0)
        l1_mid = (bb + ba) / 2.0
        if abs(l1_mid - HP_ANCHOR) > HP_BAND:
            fair = float(HP_ANCHOR)
        else:
            fair = l1_mid

        spread = ba - bb
        fair += risk.inventory_fair_shift(self.symbol, position, spread)

        sell_vol = 0
        buy_vol = 0

        if position < 0:
            for ap in sorted(od.sell_orders.keys()):
                if ap > fair + 0.5: break
                if ap < fair - self.edge: continue
                avail = abs(od.sell_orders[ap])
                cap = min(abs(position), self.pos_limit - position - buy_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(self.symbol, ap, q))
                    buy_vol += q

        if position > 0:
            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp < fair - 0.5: break
                if bp > fair + self.edge: continue
                avail = od.buy_orders[bp]
                cap = min(position, self.pos_limit + position - sell_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(self.symbol, bp, -q))
                    sell_vol += q

        bo, so = self._make_quote(fair, self.edge, bb, ba, position, buy_vol, sell_vol, risk)
        if bo: orders.append(bo)
        if so: orders.append(so)
        return orders


# ----------------------------------------------------------------------------
# VelvetfruitExtractTrader — adds hedge-aware size skew
# ----------------------------------------------------------------------------
class VelvetfruitExtractTrader(BaseProductTrader):
    def __init__(self):
        super().__init__("VELVETFRUIT_EXTRACT")

    def quote(self, state: TradingState, risk: RiskManager,
              vf_mid: float) -> List[Order]:
        orders: List[Order] = []
        od = state.order_depths.get(self.symbol)
        if od is None:
            return orders
        bb, ba = best_levels(od)
        if bb is None:
            return orders

        position = state.position.get(self.symbol, 0)
        fair = vf_mid

        spread = ba - bb
        fair += risk.inventory_fair_shift(self.symbol, position, spread)

        # Bias quote size toward closing the gap to the hedge target
        vf_target = risk.vf_target_position()
        gap = vf_target - position
        if gap > 20:
            buy_skew, sell_skew = 1.5, 0.5
        elif gap < -20:
            buy_skew, sell_skew = 0.5, 1.5
        else:
            buy_skew, sell_skew = 1.0, 1.0

        buy_vol = 0
        sell_vol = 0

        for ap in sorted(od.sell_orders.keys()):
            if ap >= fair - self.edge:
                break
            avail = abs(od.sell_orders[ap])
            cap = self.pos_limit - position - buy_vol
            q = min(avail, cap)
            if q > 0 and not risk.block_due_to_drawdown(self.symbol, position + buy_vol, "BUY"):
                orders.append(Order(self.symbol, ap, q))
                buy_vol += q

        if position + buy_vol < 0:
            for ap in sorted(od.sell_orders.keys()):
                if ap > fair + 0.5: break
                if ap < fair - self.edge: continue
                avail = abs(od.sell_orders[ap])
                cap = min(abs(position + buy_vol), self.pos_limit - position - buy_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(self.symbol, ap, q))
                    buy_vol += q

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp <= fair + self.edge:
                break
            avail = od.buy_orders[bp]
            cap = self.pos_limit + position - sell_vol
            q = min(avail, cap)
            if q > 0 and not risk.block_due_to_drawdown(self.symbol, position - sell_vol, "SELL"):
                orders.append(Order(self.symbol, bp, -q))
                sell_vol += q

        if position - sell_vol > 0:
            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp < fair - 0.5: break
                if bp > fair + self.edge: continue
                avail = od.buy_orders[bp]
                cap = min(position - sell_vol, self.pos_limit + position - sell_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(self.symbol, bp, -q))
                    sell_vol += q

        bo, so = self._make_quote(fair, self.edge, bb, ba, position, buy_vol, sell_vol, risk,
                                  side_buy_extra_skew=buy_skew, side_sell_extra_skew=sell_skew)
        if bo: orders.append(bo)
        if so: orders.append(so)
        return orders


# ----------------------------------------------------------------------------
# VoucherTrader — handles all twelve strikes; routes between intrinsic / BS / smile
# ----------------------------------------------------------------------------
class VoucherTrader:
    def __init__(self):
        pass

    def update_smile(self, state_dict: dict, vf_mid: float, tte_years: float,
                     voucher_books) -> None:
        smile_data = state_dict.get('smile_data', [])

        for sym in OPTION_VOUCHERS:
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
            if iv_bid < MIN_IV or iv_bid > MAX_IV or iv_ask < MIN_IV or iv_ask > MAX_IV:
                continue
            m_t = log(strike / vf_mid) / sqrt(tte_years)
            smile_data.append((m_t, iv_bid, iv_ask))

        if len(smile_data) > SMILE_WINDOW:
            smile_data = smile_data[-SMILE_WINDOW:]
        state_dict['smile_data'] = smile_data

        last_fit_size = state_dict.get('smile_last_fit_size', 0)
        if len(smile_data) >= MIN_SMILE_SAMPLES and \
           len(smile_data) - last_fit_size >= SMILE_REFIT_EVERY:
            m_ts = [d[0] for d in smile_data]
            iv_bids = [d[1] for d in smile_data]
            iv_asks = [d[2] for d in smile_data]
            bid_fit = fit_quadratic(m_ts, iv_bids)
            ask_fit = fit_quadratic(m_ts, iv_asks)
            if bid_fit is not None and ask_fit is not None:
                state_dict['smile_coefs'] = {
                    'a_bid': bid_fit[0], 'b_bid': bid_fit[1], 'c_bid': bid_fit[2],
                    'a_ask': ask_fit[0], 'b_ask': ask_fit[1], 'c_ask': ask_fit[2],
                }
                state_dict['smile_last_fit_size'] = len(smile_data)

    def quote_delta1(self, sym: str, state: TradingState, risk: RiskManager,
                     vf_mid: float) -> List[Order]:
        """ITM voucher (VEV_4000/4500) — intrinsic-fair MM with the standard risk overlay."""
        orders: List[Order] = []
        strike = STRIKES[sym]
        fair = vf_mid - strike
        if fair <= 0:
            return orders
        edge = EDGES[sym]
        od = state.order_depths.get(sym)
        if od is None:
            return orders
        bb, ba = best_levels(od)
        if bb is None:
            return orders

        pos_limit = POSITION_LIMITS[sym]
        position = state.position.get(sym, 0)

        spread = ba - bb
        fair += risk.inventory_fair_shift(sym, position, spread)

        buy_vol = 0
        sell_vol = 0

        for ap in sorted(od.sell_orders.keys()):
            if ap >= fair - edge:
                break
            avail = abs(od.sell_orders[ap])
            cap = pos_limit - position - buy_vol
            q = min(avail, cap)
            q = risk.can_increase_voucher_delta(sym, "BUY", q)
            if q > 0 and not risk.block_due_to_drawdown(sym, position + buy_vol, "BUY"):
                orders.append(Order(sym, ap, q))
                buy_vol += q

        if position + buy_vol < 0:
            for ap in sorted(od.sell_orders.keys()):
                if ap > fair + 0.5: break
                if ap < fair - edge: continue
                avail = abs(od.sell_orders[ap])
                cap = min(abs(position + buy_vol), pos_limit - position - buy_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(sym, ap, q))
                    buy_vol += q

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp <= fair + edge:
                break
            avail = od.buy_orders[bp]
            cap = pos_limit + position - sell_vol
            q = min(avail, cap)
            q = risk.can_increase_voucher_delta(sym, "SELL", q)
            if q > 0 and not risk.block_due_to_drawdown(sym, position - sell_vol, "SELL"):
                orders.append(Order(sym, bp, -q))
                sell_vol += q

        if position - sell_vol > 0:
            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp < fair - 0.5: break
                if bp > fair + edge: continue
                avail = od.buy_orders[bp]
                cap = min(position - sell_vol, pos_limit + position - sell_vol)
                q = min(avail, cap)
                if q > 0:
                    orders.append(Order(sym, bp, -q))
                    sell_vol += q

        my_bid_candidates = [bb + 1, int(round(fair - edge))]
        my_ask_candidates = [ba - 1, int(round(fair + edge))]
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
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(sym, 0.3))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        buy_cap = risk.apply_taper(buy_cap, sym, position, "BUY")
        sell_cap = risk.apply_taper(sell_cap, sym, position, "SELL")
        buy_cap = risk.can_increase_voucher_delta(sym, "BUY", buy_cap)
        sell_cap = risk.can_increase_voucher_delta(sym, "SELL", sell_cap)
        if risk.block_due_to_drawdown(sym, position, "BUY"):
            buy_cap = 0
        if risk.block_due_to_drawdown(sym, position, "SELL"):
            sell_cap = 0

        if buy_cap > 0:
            orders.append(Order(sym, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(sym, int(my_ask), -sell_cap))

        return orders

    def quote_option(self, sym: str, state: TradingState, risk: RiskManager,
                     vf_mid: float, tte_years: float, state_dict: dict) -> List[Order]:
        """BS-fair voucher MM with rolling IV and Z-score overlay."""
        orders: List[Order] = []
        pos_limit = POSITION_LIMITS[sym]
        strike = STRIKES[sym]
        position = state.position.get(sym, 0)

        od = state.order_depths.get(sym)
        if od is None:
            return orders
        bb, ba = best_levels(od)
        if bb is None or vf_mid is None:
            return orders

        voucher_mid = voucher_swmid(od) or ((bb + ba) / 2.0)

        cur_iv = implied_vol(voucher_mid, vf_mid, strike, tte_years)
        iv_key = f"iv_{sym}"
        iv_hist = state_dict.get(iv_key, [])
        if cur_iv is not None:
            iv_hist.append(cur_iv)
            if len(iv_hist) > SIGMA_WINDOW:
                iv_hist = iv_hist[-SIGMA_WINDOW:]
            state_dict[iv_key] = iv_hist

        if len(iv_hist) < MIN_SIGMA_SAMPLES:
            return orders

        sigma = rolling_median(iv_hist)
        fair = bs_call(vf_mid, strike, tte_years, sigma)
        if fair < 0.5 or fair > vf_mid:
            return orders

        spread = max(1.0, ba - bb)
        fair += risk.inventory_fair_shift(sym, position, spread)

        price_key = f"price_{sym}"
        price_hist = state_dict.get(price_key, [])
        price_hist.append(voucher_mid)
        required = ZSCORE_PERIOD + SMOOTHING_PERIOD
        if len(price_hist) > required:
            price_hist = price_hist[-required:]
        state_dict[price_key] = price_hist

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

        edge = EDGES.get(sym, 1.0)
        buy_vol = 0
        sell_vol = 0

        for ap in sorted(od.sell_orders.keys()):
            if ap >= fair - edge:
                break
            avail = abs(od.sell_orders[ap])
            cap = pos_limit - position - buy_vol
            q = min(avail, cap)
            q = risk.can_increase_voucher_delta(sym, "BUY", q)
            if q > 0 and not risk.block_due_to_drawdown(sym, position + buy_vol, "BUY"):
                orders.append(Order(sym, ap, q))
                buy_vol += q

        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp <= fair + edge:
                break
            avail = od.buy_orders[bp]
            cap = pos_limit + position - sell_vol
            q = min(avail, cap)
            q = risk.can_increase_voucher_delta(sym, "SELL", q)
            if q > 0 and not risk.block_due_to_drawdown(sym, position - sell_vol, "SELL"):
                orders.append(Order(sym, bp, -q))
                sell_vol += q

        if zscore is not None:
            if zscore < -ZSCORE_THRESHOLD_LONG and position + buy_vol < pos_limit:
                for ap in sorted(od.sell_orders.keys()):
                    if ap > fair + edge:
                        break
                    avail = abs(od.sell_orders[ap])
                    cap = pos_limit - position - buy_vol
                    q = min(avail, cap, int(pos_limit * 0.2))
                    q = risk.can_increase_voucher_delta(sym, "BUY", q)
                    if q > 0 and not risk.block_due_to_drawdown(sym, position + buy_vol, "BUY"):
                        orders.append(Order(sym, ap, q))
                        buy_vol += q
                        break
            elif zscore > ZSCORE_THRESHOLD_SHORT and position - sell_vol > -pos_limit:
                for bp in sorted(od.buy_orders.keys(), reverse=True):
                    if bp < fair - edge:
                        break
                    avail = od.buy_orders[bp]
                    cap = pos_limit + position - sell_vol
                    q = min(avail, cap, int(pos_limit * 0.1))
                    q = risk.can_increase_voucher_delta(sym, "SELL", q)
                    if q > 0 and not risk.block_due_to_drawdown(sym, position - sell_vol, "SELL"):
                        orders.append(Order(sym, bp, -q))
                        sell_vol += q
                        break

        my_bid_candidates = [bb + 1, int(round(fair - edge))]
        my_ask_candidates = [ba - 1, int(round(fair + edge))]
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
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(sym, 0.15))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        buy_cap = risk.apply_taper(buy_cap, sym, position, "BUY")
        sell_cap = risk.apply_taper(sell_cap, sym, position, "SELL")
        buy_cap = risk.can_increase_voucher_delta(sym, "BUY", buy_cap)
        sell_cap = risk.can_increase_voucher_delta(sym, "SELL", sell_cap)
        if risk.block_due_to_drawdown(sym, position, "BUY"):
            buy_cap = 0
        if risk.block_due_to_drawdown(sym, position, "SELL"):
            sell_cap = 0

        if buy_cap > 0:
            orders.append(Order(sym, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(sym, int(my_ask), -sell_cap))

        return orders

    def quote_smile(self, sym: str, state: TradingState, risk: RiskManager,
                    vf_mid: float, tte_years: float, state_dict: dict) -> List[Order]:
        """Smile-priced voucher MM (uses the pooled quadratic fit)."""
        orders: List[Order] = []
        pos_limit = POSITION_LIMITS[sym]
        strike = STRIKES[sym]
        position = state.position.get(sym, 0)

        od = state.order_depths.get(sym)
        if od is None:
            return orders
        bb, ba = best_levels(od)
        if bb is None or vf_mid is None:
            return orders

        coefs = state_dict.get('smile_coefs')
        if coefs is None:
            iv_bid_pred = FALLBACK_SIGMA
            iv_ask_pred = FALLBACK_SIGMA
        else:
            m_t = log(strike / vf_mid) / sqrt(tte_years)
            iv_bid_pred = coefs['a_bid']*m_t*m_t + coefs['b_bid']*m_t + coefs['c_bid']
            iv_ask_pred = coefs['a_ask']*m_t*m_t + coefs['b_ask']*m_t + coefs['c_ask']
            iv_bid_pred += STRIKE_IV_CORRECTION_BID.get(strike, 0.0)
            iv_ask_pred += STRIKE_IV_CORRECTION_ASK.get(strike, 0.0)
            iv_bid_pred = max(MIN_IV, min(MAX_IV, iv_bid_pred))
            iv_ask_pred = max(MIN_IV, min(MAX_IV, iv_ask_pred))

        voucher_mid = voucher_swmid(od) or ((bb + ba) / 2.0)
        cur_iv = implied_vol(voucher_mid, vf_mid, strike, tte_years)
        iv_key = f"iv_{sym}"
        iv_hist = state_dict.get(iv_key, [])
        if cur_iv is not None:
            iv_hist.append(cur_iv)
            if len(iv_hist) > SIGMA_WINDOW:
                iv_hist = iv_hist[-SIGMA_WINDOW:]
            state_dict[iv_key] = iv_hist

        pred_bid_price = bs_call(vf_mid, strike, tte_years, iv_bid_pred)
        pred_ask_price = bs_call(vf_mid, strike, tte_years, iv_ask_pred)
        if pred_bid_price < 0.5 or pred_ask_price < 0.5 or pred_ask_price <= pred_bid_price:
            pred_bid_price = voucher_mid - 1
            pred_ask_price = voucher_mid + 1
        pred_mid = (pred_bid_price + pred_ask_price) / 2.0

        spread = max(1.0, ba - bb)
        shift = risk.inventory_fair_shift(sym, position, spread)
        pred_bid_price += shift
        pred_ask_price += shift
        pred_mid += shift

        smile_samples = len(state_dict.get('smile_data', []))
        smile_matured = smile_samples >= 100

        price_key = f"price_{sym}"
        price_hist = state_dict.get(price_key, [])
        price_hist.append(voucher_mid)
        max_len = ZSCORE_PERIOD + SMOOTHING_PERIOD + 10
        if len(price_hist) > max_len:
            price_hist = price_hist[-max_len:]
        state_dict[price_key] = price_hist

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
                q = risk.can_increase_voucher_delta(sym, "BUY", q)
                if q > 0 and not risk.block_due_to_drawdown(sym, position + buy_vol, "BUY"):
                    orders.append(Order(sym, ap, q))
                    buy_vol += q

            for bp in sorted(od.buy_orders.keys(), reverse=True):
                if bp <= pred_ask_price + SMILE_TAKE_EDGE:
                    break
                avail = od.buy_orders[bp]
                cap = pos_limit + position - sell_vol
                q = min(avail, cap)
                q = risk.can_increase_voucher_delta(sym, "SELL", q)
                if q > 0 and not risk.block_due_to_drawdown(sym, position - sell_vol, "SELL"):
                    orders.append(Order(sym, bp, -q))
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
                        q = risk.can_increase_voucher_delta(sym, "BUY", q)
                        if q > 0 and not risk.block_due_to_drawdown(sym, position + buy_vol, "BUY"):
                            orders.append(Order(sym, best_ask, q))
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
                        q = risk.can_increase_voucher_delta(sym, "SELL", q)
                        if q > 0 and not risk.block_due_to_drawdown(sym, position - sell_vol, "SELL"):
                            orders.append(Order(sym, best_bid, -q))
                            sell_vol += q

        my_bid = max(bb + 1, int(pred_bid_price))
        my_ask = min(ba - 1, int(pred_ask_price) + 1)
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
        max_make = int(pos_limit * SIZE_CAP_FRAC.get(sym, 0.15))

        if pos_ratio > 0.3:
            buy_cap = min(buy_cap, max_make // 3)
            sell_cap = min(sell_cap, max_make)
        elif pos_ratio < -0.3:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make // 3)
        else:
            buy_cap = min(buy_cap, max_make)
            sell_cap = min(sell_cap, max_make)

        buy_cap = risk.apply_taper(buy_cap, sym, position, "BUY")
        sell_cap = risk.apply_taper(sell_cap, sym, position, "SELL")
        buy_cap = risk.can_increase_voucher_delta(sym, "BUY", buy_cap)
        sell_cap = risk.can_increase_voucher_delta(sym, "SELL", sell_cap)
        if risk.block_due_to_drawdown(sym, position, "BUY"):
            buy_cap = 0
        if risk.block_due_to_drawdown(sym, position, "SELL"):
            sell_cap = 0

        if buy_cap > 0:
            orders.append(Order(sym, int(my_bid), buy_cap))
        if sell_cap > 0:
            orders.append(Order(sym, int(my_ask), -sell_cap))

        return orders

    def quote_dead(self, sym: str, state: TradingState) -> List[Order]:
        """Deep-OTM passive fallback — emits no orders by default."""
        orders: List[Order] = []
        od = state.order_depths.get(sym)
        if od is None:
            return orders
        position = state.position.get(sym, 0)
        if position < POSITION_LIMITS[sym] and od.buy_orders:
            pass
        return orders


# ----------------------------------------------------------------------------
# Trader — entrypoint
# ----------------------------------------------------------------------------
class Trader:
    _tte_override: Optional[float] = None

    def __init__(self):
        self.hp = HydrogelTrader()
        self.vf = VelvetfruitExtractTrader()
        self.vouchers = VoucherTrader()
        self.bots = CounterpartyEngine(BOT_TABLE_JSON, ENABLE_BOT_INTELLIGENCE)

    def bid(self):
        return 5000

    def run(self, state: TradingState):
        try:
            persisted = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            persisted = {}

        result: Dict[str, List[Order]] = {}

        vf_mid = None
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            bb, ba = best_levels(state.order_depths["VELVETFRUIT_EXTRACT"])
            if bb is not None:
                vf_mid = (bb + ba) / 2.0

        start_tte = self._tte_override if self._tte_override is not None else TTE_DAYS_AT_START
        tte_days = max(0.1, start_tte - state.timestamp / TIMESTAMPS_PER_DAY)
        tte_years = tte_days / 365.0

        if vf_mid is not None:
            voucher_books = {sym: state.order_depths[sym] for sym in OPTION_VOUCHERS
                             if sym in state.order_depths}
            self.vouchers.update_smile(persisted, vf_mid, tte_years, voucher_books)

        risk = RiskManager(state, persisted)
        if vf_mid is not None:
            risk.compute_voucher_deltas(vf_mid, tte_years, persisted)

        if "HYDROGEL_PACK" in state.order_depths:
            result["HYDROGEL_PACK"] = self.hp.quote(state, risk)

        if "VELVETFRUIT_EXTRACT" in state.order_depths and vf_mid is not None:
            result["VELVETFRUIT_EXTRACT"] = self.vf.quote(state, risk, vf_mid)

        for sym in DELTA1_VOUCHERS:
            if sym not in state.order_depths or vf_mid is None:
                continue
            result[sym] = self.vouchers.quote_delta1(sym, state, risk, vf_mid)

        for sym in OPTION_VOUCHERS:
            if sym not in state.order_depths or vf_mid is None:
                continue
            strike = STRIKES[sym]
            if strike in SMILE_STRIKES:
                result[sym] = self.vouchers.quote_smile(sym, state, risk, vf_mid, tte_years, persisted)
            else:
                result[sym] = self.vouchers.quote_option(sym, state, risk, vf_mid, tte_years, persisted)

        for sym in ["VEV_6000", "VEV_6500"]:
            if sym not in state.order_depths:
                continue
            result[sym] = self.vouchers.quote_dead(sym, state)

        risk.persist(persisted)

        return result, 0, json.dumps(persisted)
