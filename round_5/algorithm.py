"""
IMC Prosperity 4 — Round 5 submission.

Products: 50 items across 10 groups (GALAXY_SOUNDS, SLEEP_POD, MICROCHIP,
PEBBLES, ROBOT, UV_VISOR, TRANSLATOR, PANEL, OXYGEN, SNACKPACK), each with
5 variants. Position limit: 10 per product.

Final algorithm PnL: +186,005 (rank 69 globally, top 0.4%).
"""
from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json

POS_LIMIT = 10

GROUPS = {
    'GALAXY_SOUNDS': ['GALAXY_SOUNDS_DARK_MATTER','GALAXY_SOUNDS_BLACK_HOLES','GALAXY_SOUNDS_PLANETARY_RINGS','GALAXY_SOUNDS_SOLAR_WINDS','GALAXY_SOUNDS_SOLAR_FLAMES'],
    'SLEEP_POD': ['SLEEP_POD_SUEDE','SLEEP_POD_LAMB_WOOL','SLEEP_POD_POLYESTER','SLEEP_POD_NYLON','SLEEP_POD_COTTON'],
    'MICROCHIP': ['MICROCHIP_CIRCLE','MICROCHIP_OVAL','MICROCHIP_SQUARE','MICROCHIP_RECTANGLE','MICROCHIP_TRIANGLE'],
    'PEBBLES': ['PEBBLES_XS','PEBBLES_S','PEBBLES_M','PEBBLES_L','PEBBLES_XL'],
    'ROBOT': ['ROBOT_VACUUMING','ROBOT_MOPPING','ROBOT_DISHES','ROBOT_LAUNDRY','ROBOT_IRONING'],
    'UV_VISOR': ['UV_VISOR_YELLOW','UV_VISOR_AMBER','UV_VISOR_ORANGE','UV_VISOR_RED','UV_VISOR_MAGENTA'],
    'TRANSLATOR': ['TRANSLATOR_SPACE_GRAY','TRANSLATOR_ASTRO_BLACK','TRANSLATOR_ECLIPSE_CHARCOAL','TRANSLATOR_GRAPHITE_MIST','TRANSLATOR_VOID_BLUE'],
    'PANEL': ['PANEL_1X2','PANEL_2X2','PANEL_1X4','PANEL_2X4','PANEL_4X4'],
    'OXYGEN': ['OXYGEN_SHAKE_MORNING_BREATH','OXYGEN_SHAKE_EVENING_BREATH','OXYGEN_SHAKE_MINT','OXYGEN_SHAKE_CHOCOLATE','OXYGEN_SHAKE_GARLIC'],
    'SNACKPACK': ['SNACKPACK_CHOCOLATE','SNACKPACK_VANILLA','SNACKPACK_PISTACHIO','SNACKPACK_STRAWBERRY','SNACKPACK_RASPBERRY'],
}

ALL_PRODUCTS = [p for prods in GROUPS.values() for p in prods]


def best_bid_ask(od: OrderDepth):
    bb = max(od.buy_orders.keys()) if od.buy_orders else None
    ba = min(od.sell_orders.keys()) if od.sell_orders else None
    return bb, ba


def mid_price(od: OrderDepth):
    bb, ba = best_bid_ask(od)
    if bb is None or ba is None:
        return None
    return (bb + ba) / 2.0


class Trader:
    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        try:
            mem = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            mem = {}
        ewma = mem.get('ewma', {})
        ALPHA = 0.05

        for product in ALL_PRODUCTS:
            if product not in state.order_depths:
                continue
            od = state.order_depths[product]
            pos = state.position.get(product, 0)

            bb, ba = best_bid_ask(od)
            if bb is None or ba is None:
                continue
            mid = (bb + ba) / 2.0
            spread = ba - bb

            prev = ewma.get(product, mid)
            anchor = (1 - ALPHA) * prev + ALPHA * mid
            ewma[product] = anchor

            orders: List[Order] = []

            fair = 0.5 * mid + 0.5 * anchor
            edge = 1 if spread <= 2 else 2
            skew = -pos * 0.2

            buy_px = int(round(fair + skew - edge))
            sell_px = int(round(fair + skew + edge))

            if buy_px >= sell_px:
                buy_px = sell_px - 1
            buy_px = min(buy_px, bb + 1) if bb is not None else buy_px
            sell_px = max(sell_px, ba - 1) if ba is not None else sell_px

            if ba is not None and ba <= fair - 1.5 and pos < POS_LIMIT:
                ask_vol = -od.sell_orders[ba]
                qty = min(ask_vol, POS_LIMIT - pos)
                if qty > 0:
                    orders.append(Order(product, ba, qty))
                    pos += qty
            if bb is not None and bb >= fair + 1.5 and pos > -POS_LIMIT:
                bid_vol = od.buy_orders[bb]
                qty = min(bid_vol, POS_LIMIT + pos)
                if qty > 0:
                    orders.append(Order(product, bb, -qty))
                    pos -= qty

            buy_room = POS_LIMIT - pos
            sell_room = POS_LIMIT + pos
            mm_size = 5
            buy_size = min(mm_size, buy_room)
            sell_size = min(mm_size, sell_room)

            if buy_size > 0:
                orders.append(Order(product, buy_px, buy_size))
            if sell_size > 0:
                orders.append(Order(product, sell_px, -sell_size))

            result[product] = orders

        new_data = json.dumps({'ewma': ewma})
        return result, 0, new_data
