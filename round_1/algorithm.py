"""
IMC Prosperity 4 — Round 1 submission.

Products: ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT. Position limit 80 each.

Final algorithm PnL: +96,942 (rank 1231).
"""
from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict
import json, math


OSMIUM_FAIR = 10000.0
POSITION_LIMIT = 80


class Trader:
    def __init__(self):
        self.position_limits = {"ASH_COATED_OSMIUM": 80, "INTARIAN_PEPPER_ROOT": 80}

    def bid(self):
        return 15

    def trade_osmium(self, order_depth, position):
        orders = []
        fair_value = OSMIUM_FAIR
        pos_limit = POSITION_LIMIT
        buy_vol = 0
        sell_vol = 0

        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys())
            if best_ask < fair_value - 1:
                amt = abs(order_depth.sell_orders[best_ask])
                qty = min(amt, pos_limit - position)
                if qty > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", best_ask, qty))
                    buy_vol += qty

        if order_depth.buy_orders:
            best_bid = max(order_depth.buy_orders.keys())
            if best_bid > fair_value + 1:
                amt = order_depth.buy_orders[best_bid]
                qty = min(amt, pos_limit + position)
                if qty > 0:
                    orders.append(Order("ASH_COATED_OSMIUM", best_bid, -qty))
                    sell_vol += qty

        pos_after = position + buy_vol - sell_vol
        if pos_after > 0 and 10000 in order_depth.buy_orders:
            cq = min(order_depth.buy_orders[10000], pos_after, pos_limit + position - sell_vol)
            if cq > 0:
                orders.append(Order("ASH_COATED_OSMIUM", 10000, -cq))
                sell_vol += cq
        elif pos_after < 0 and 10000 in order_depth.sell_orders:
            cq = min(abs(order_depth.sell_orders[10000]), abs(pos_after), pos_limit - position - buy_vol)
            if cq > 0:
                orders.append(Order("ASH_COATED_OSMIUM", 10000, cq))
                buy_vol += cq

        asks_above = [p for p in order_depth.sell_orders.keys() if p > 10001]
        bids_below = [p for p in order_depth.buy_orders.keys() if p < 9999]
        ba = min(asks_above) if asks_above else 10002
        bb = max(bids_below) if bids_below else 9998
        bp = int(bb + 1)
        sp = int(ba - 1)
        if bp >= sp:
            bp, sp = 9999, 10001

        rb = pos_limit - (position + buy_vol)
        if rb > 0:
            orders.append(Order("ASH_COATED_OSMIUM", bp, rb))
        rs = pos_limit + (position - sell_vol)
        if rs > 0:
            orders.append(Order("ASH_COATED_OSMIUM", sp, -rs))

        return orders

    def trade_pepper(self, order_depth, position):
        orders = []
        pos_limit = POSITION_LIMIT
        buy_vol = 0
        remaining = pos_limit - position

        if remaining <= 0:
            if order_depth.sell_orders:
                best_ask = min(order_depth.sell_orders.keys())
                orders.append(Order("INTARIAN_PEPPER_ROOT", best_ask + 50, -1))
            return orders

        if order_depth.sell_orders:
            for ask_price in sorted(order_depth.sell_orders.keys()):
                if remaining - buy_vol <= 0:
                    break
                ask_amount = abs(order_depth.sell_orders[ask_price])
                qty = min(ask_amount, remaining - buy_vol)
                if qty > 0:
                    orders.append(Order("INTARIAN_PEPPER_ROOT", ask_price, qty))
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
            orders.append(Order("INTARIAN_PEPPER_ROOT", int(buy_price), leftover))

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

