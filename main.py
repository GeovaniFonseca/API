from flask import Flask, jsonify
import requests
import threading
import time
import re

app = Flask(__name__)



# Classe de Serviço de Leilão
class AuctionService:
    def get_auction_data(self):
        auction_items = []
        page = 0
        more_pages = True
        while more_pages:
            response = requests.get(f"https://api.hypixel.net/skyblock/auctions?page={page}")
            response.raise_for_status()
            data = response.json()
            total_pages = data['totalPages']
            print(f"Fetching page {page + 1} of {total_pages}")
            more_pages = page + 1 < total_pages
            page += 1
            auction_items.extend(data["auctions"])
        return auction_items

# Classe de Preço de Atributos
class AttributePricer:
    VALID_ARMOR_PIECES = ["Helmet", "Chestplate", "Leggings", "Boots"]
    VALID_EQUIPMENT_PIECES = ["Belt", "Bracelet", "Cloak", "Necklace"]
    VALID_ATTRIBUTES = [
        "Arachno", "Attack Speed", "Blazing", "Combo", "Elite", "Ender", "Ignition", "Life Recovery", "Mana Steal",
        "Midas Touch", "Undead", "Warrior", "Deadeye", "Arachno Resistance", "Blazing Resistance", "Breeze", "Dominance", 
        "Ender Resistance", "Experience", "Fortitude", "Life Regeneration", "Lifeline", "Magic Find", "Mana Pool", "Mana Regeneration",
        "Vitality", "Speed", "Undead Resistance", "Veteran", "Blazing Fortune", "Fishing Experience", "Infection", "Double Hook", "Fisherman", 
        "Fishing Speed", "Hunter", "Trophy Hunter"] 
    ATTRIBUTE_SHARD = "Attribute Shard"

    def __init__(self, auction_service):
        self.auction_service = auction_service

    def extract_attributes(self, item_lore):
        regex = re.compile(r"(?i)(%s)\s([IVXLCDM]+)" % "|".join(self.VALID_ATTRIBUTES))
        normalized_lore = re.sub(r'§[0-9a-fk-or]', '', item_lore)
        attributes = {}
        for match in regex.findall(normalized_lore):
            attribute_name = match[0].strip().lower().replace(" ", "_")
            level = self.roman_to_integer(match[1])
            attributes[f"{attribute_name}_{level}"] = None
        return attributes

    @staticmethod
    def roman_to_integer(roman):
        roman_numerals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
        result = 0
        prev_value = 0
        for char in reversed(roman):
            value = roman_numerals[char.upper()]
            if value < prev_value:
                result -= value
            else:
                result += value
            prev_value = value
        return result

    def group_and_price_items(self, auctions):
        grouped_data = {piece.upper(): {} for piece in self.VALID_ARMOR_PIECES + self.VALID_EQUIPMENT_PIECES}
        grouped_data["ATTRIBUTE_SHARD"] = {}

        for auction in auctions:
            item_name = auction.get("item_name", "")
            item_lore = auction.get("item_lore", "")
            starting_bid = auction.get("starting_bid", float("inf"))
            bin_status = auction.get("bin", False)
            item_uuid = auction.get("uuid", "")

            if not bin_status or not item_lore:
                continue

            # Verificar se é um Attribute Shard
            if self.ATTRIBUTE_SHARD.lower() in item_name.lower():
                attributes = self.extract_attributes(item_lore)
                for attr in attributes.keys():
                    if attr not in grouped_data["ATTRIBUTE_SHARD"]:
                        grouped_data["ATTRIBUTE_SHARD"][attr] = {"price": starting_bid}
                        # grouped_data["ATTRIBUTE_SHARD"][attr] = {"price": starting_bid, "uuid": item_uuid}
                    else:
                        if starting_bid < grouped_data["ATTRIBUTE_SHARD"][attr]["price"]:
                            grouped_data["ATTRIBUTE_SHARD"][attr] = {"price": starting_bid}
                            # grouped_data["ATTRIBUTE_SHARD"][attr] = {"price": starting_bid, "uuid": item_uuid}
                continue

            # Verificar tipo de armadura ou equipamento
            piece_type = next((piece for piece in self.VALID_ARMOR_PIECES if piece in item_name), None)
            if not piece_type:
                piece_type = next((equip for equip in self.VALID_EQUIPMENT_PIECES if equip in item_name), None)

            if not piece_type:
                continue

            # Agrupar os atributos
            attributes = self.extract_attributes(item_lore)
            for attr, _ in attributes.items():
                if attr not in grouped_data[piece_type.upper()]:
                    # grouped_data[piece_type.upper()][attr] = {"price": starting_bid, "uuid": item_uuid}
                    grouped_data[piece_type.upper()][attr] = {"price": starting_bid}
                else:
                    if starting_bid < grouped_data[piece_type.upper()][attr]["price"]:
                        # grouped_data[piece_type.upper()][attr] = {"price": starting_bid, "uuid": item_uuid}
                        grouped_data[piece_type.upper()][attr] = {"price": starting_bid}

        return grouped_data

# Cache Global
cache_data = {"data": None, "last_updated": None}
cache_lock = threading.Lock()

def update_cache():
    global cache_data
    auction_service = AuctionService()
    attribute_pricer = AttributePricer(auction_service)

    while True:
        try:
            print("Updating cache...")
            auctions = auction_service.get_auction_data()
            grouped_prices = attribute_pricer.group_and_price_items(auctions)
            with cache_lock:
                cache_data["data"] = grouped_prices
                cache_data["last_updated"] = time.time()
            print("Cache updated successfully.")
        except Exception as e:
            print(f"Error updating cache: {e}")
        time.sleep(240)

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "API is running"})

@app.route('/attribute_prices', methods=['GET'])
def attribute_prices():
    with cache_lock:
        if cache_data["data"] is None:
            return jsonify({"error": "Cache not ready. Please try again later."}), 503
        
        # Encapsular a resposta em uma lista
        response = [cache_data["data"]]
        return jsonify(response)


if __name__ == '__main__':
    cache_thread = threading.Thread(target=update_cache, daemon=True)
    cache_thread.start()
    app.run(host='0.0.0.0', port=5000, debug=True)
