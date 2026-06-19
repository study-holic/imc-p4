"""
IMC Prosperity 4 — Round 2 submission.

Products: ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT. Position limit 80 each.
Plus a sealed MAF (market access fee) bid.

Final algorithm PnL: +76,850 (rank 3242).
"""
from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict


OSMIUM_FAIR = 10000
OSMIUM_BUY_EDGE = 1
OSMIUM_SELL_EDGE = 2
OSMIUM_MAKE_BID_EDGE = 1
OSMIUM_MAKE_ASK_EDGE = 2
POSITION_LIMIT = 80
MAF_BID = 5000


class Trader:
    def __init__(self):
        self.position_limits = {"ASH_COATED_OSMIUM": 80, "INTARIAN_PEPPER_ROOT": 80}

    def bid(self):
        return MAF_BID

    def trade_osmium(self, order_depth, position):
        orders = []
        fair_value = OSMIUM_FAIR
        pos_limit = POSITION_LIMIT
        SYM = "ASH_COATED_OSMIUM"
        buy_vol = 0
        sell_vol = 0

        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys())
            if best_ask < fair_value - OSMIUM_BUY_EDGE:
                amt = abs(order_depth.sell_orders[best_ask])
                qty = min(amt, pos_limit - position)
                if qty > 0:
                    orders.append(Order(SYM, best_ask, qty))
                    buy_vol += qty

        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders.keys())
            if best_bid > fair_value + OSMIUM_SELL_EDGE:
                amt = order_depth.buy_orders[best_bid]
                qty = min(amt, pos_limit + position)
                if qty > 0:
                    orders.append(Order(SYM, best_bid, -qty))
                    sell_vol += qty

        pos_after = position + buy_vol - sell_vol
        if pos_after > 0 and fair_value in order_depth.buy_orders:
            cq = min(order_depth.buy_orders[fair_value], pos_after,
                     pos_limit + position - sell_vol)
            if cq > 0:
                orders.append(Order(SYM, fair_value, -cq))
                sell_vol += cq
        elif pos_after < 0 and fair_value in order_depth.sell_orders:
            cq = min(abs(order_depth.sell_orders[fair_value]), abs(pos_after),
                     pos_limit - position - buy_vol)
            if cq > 0:
                orders.append(Order(SYM, fair_value, cq))
                buy_vol += cq

        asks_above = [p for p in order_depth.sell_orders.keys() if p > fair_value + OSMIUM_MAKE_ASK_EDGE]
        bids_below = [p for p in order_depth.buy_orders.keys() if p < fair_value - OSMIUM_MAKE_BID_EDGE]
        ba = min(asks_above) if asks_above else fair_value + OSMIUM_MAKE_ASK_EDGE + 1
        bb = max(bids_below) if bids_below else fair_value - OSMIUM_MAKE_BID_EDGE - 1
        bp = int(bb + 1)
        sp = int(ba - 1)
        bp = min(bp, fair_value - OSMIUM_MAKE_BID_EDGE)
        sp = max(sp, fair_value + OSMIUM_MAKE_ASK_EDGE)

        rb = pos_limit - (position + buy_vol)
        if rb > 0:
            orders.append(Order(SYM, bp, rb))
        rs = pos_limit + (position - sell_vol)
        if rs > 0:
            orders.append(Order(SYM, sp, -rs))

        return orders

    def trade_pepper(self, order_depth, position):
        orders = []
        pos_limit = POSITION_LIMIT
        SYM = "INTARIAN_PEPPER_ROOT"
        buy_vol = 0
        remaining = pos_limit - position

        if remaining <= 0:
            if order_depth.sell_orders:
                best_ask = min(order_depth.sell_orders.keys())
                orders.append(Order(SYM, best_ask + 50, -1))
            return orders

        if order_depth.sell_orders:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if remaining - buy_vol <= 0:
                    break
                ask_amount = abs(order_depth.sell_orders[ask_price])
                qty = min(ask_amount, remaining - buy_vol)
                if qty > 0:
                    orders.append(Order(SYM, ask_price, qty))
                    buy_vol += qty

        leftover = remaining - buy_vol
        if leftover > 0:
            if order_depth.buy_orders:
                best_bid = max(order_depth.buy_orders.keys())
                buy_price = best_bid + 1
            else:
                if order_depth.sell_orders:
                    best_ask = min(order_depth.sell_orders.keys())
                    buy_price = best_ask - 10
                else:
                    buy_price = 12000
            orders.append(Order(SYM, int(buy_price), leftover))

        return orders

    def run(self, state: TradingState):
        result = {}
        for product in state.order_depths:
            od = state.order_depths[product]
            pos = state.position.get(product, 0)
            if product == "ASH_COATED_OSMIUM":
                result[product] = self.trade_osmium(od, pos)
            elif product == "INTARIAN_PEPPER_ROOT":
                result[product] = self.trade_pepper(od, pos)
        return result, 0, ""
