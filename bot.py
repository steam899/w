import json
import time
import math
import random
import requests

API_BASE = "https://wolfbet.com/api/v1"

class WolfBetBot:
    def __init__(self, cfg_path="config.json"):
        with open(cfg_path, "r") as f:
            self.cfg = json.load(f)

        token = self.cfg.get("access_token", "").strip()
        if not token:
            raise ValueError("access_token kosong dalam config.json")

        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Sesuai contoh rasmi curl — sesetengah CDN expect header ni
            "X-Requested-With": "XMLHttpRequest",
        }

        self.currency = str(self.cfg.get("currency", "btc")).lower()
        self.base_bet = float(self.cfg.get("base_bet", 0.00000001))
        self.multiplier_factor = float(self.cfg.get("multiplier", 2.0))
        self.max_bet = float(self.cfg.get("max_bet", 0.0001))
        self.chance = float(self.cfg.get("chance", 49.5))     # % peluang
        self.rule_mode = str(self.cfg.get("rule_mode", "auto")).lower()  # auto|over|under
        self.take_profit = float(self.cfg.get("take_profit", 0.0005))
        self.stop_loss = float(self.cfg.get("stop_loss", -0.0005))
        self.cooldown = float(self.cfg.get("cooldown_sec", 1.0))
        self.debug = bool(self.cfg.get("debug", True))

        self.session_profit = 0.0
        self.current_bet = self.base_bet

    # ---------------- REST calls ----------------
    def _get(self, path):
        try:
            r = requests.get(f"{API_BASE}{path}", headers=self.headers, timeout=20)
            if self.debug and r.status_code != 200:
                print(f"[GET {path}] HTTP {r.status_code}: {r.text[:200]}")
            return r
        except Exception as e:
            if self.debug:
                print(f"⚠️ GET {path} network error: {e}")
            return None

    def _post(self, path, payload):
        try:
            r = requests.post(f"{API_BASE}{path}", headers=self.headers, json=payload, timeout=20)
            if self.debug and r.status_code != 200:
                print(f"[POST {path}] HTTP {r.status_code}: {r.text[:200]}")
            return r
        except Exception as e:
            if self.debug:
                print(f"⚠️ POST {path} network error: {e}")
            return None

    def get_balances(self):
        r = self._get("/user/balances")
        if not r:
            return None
        try:
            data = r.json()
            return data.get("balances", [])
        except Exception as e:
            if self.debug:
                print(f"⚠️ Parse balances JSON error: {e} | raw: {r.text[:200]}")
            return None

    def get_balance_currency(self, currency):
        balances = self.get_balances()
        if not balances:
            return None
        for b in balances:
            if str(b.get("currency", "")).lower() == currency.lower():
                try:
                    return float(b.get("amount"))
                except Exception:
                    return None
        return None

    def place_dice_bet(self, amount, rule, bet_value, multiplier):
        payload = {
            "currency": self.currency,  # enum lower-case per docs
            "game": "dice",
            "amount": str(amount),      # docs sample uses strings; both ok
            "rule": rule,               # "over" | "under"
            "multiplier": str(multiplier),
            "bet_value": str(bet_value)
        }
        r = self._post("/bet/place", payload)
        if not r:
            return None, None

        # Rate limit headers (docs mention x-ratelimit-*)
        rl_limit = r.headers.get("x-ratelimit-limit")
        rl_left  = r.headers.get("x-ratelimit-remaining")

        try:
            data = r.json()
            return data, (rl_limit, rl_left)
        except Exception as e:
            if self.debug:
                print(f"⚠️ Parse bet JSON error: {e} | raw: {r.text[:200]}")
            return None, (rl_limit, rl_left)

# -------------- Dice helpers --------------
    @staticmethod
    def _cap(val, lo, hi):
        return max(lo, min(hi, val))

    def chance_to_rule_and_threshold(self):
        """
        Tukar chance (%) kepada (rule, bet_value) ikut API:
          - rule: "under"  -> menang bila roll < bet_value
          - rule: "over"   -> menang bila roll > bet_value
        bet_value range 0..99.99
        """
        chance = self._cap(self.chance, 0.01, 99.99)

        if self.rule_mode == "over":
            rule = "over"
            bet_value = self._cap(100.0 - chance, 0.01, 99.99)
        elif self.rule_mode == "under":
            rule = "under"
            bet_value = self._cap(chance, 0.01, 99.99)
        else:
            # auto: randomize sedikit untuk tak predictable
            if random.randint(0, 1) == 1:
                rule = "under"
                bet_value = self._cap(chance, 0.01, 99.99)
            else:
                rule = "over"
                bet_value = self._cap(100.0 - chance, 0.01, 99.99)

        # Multiplier anggaran tanpa house-edge: 99 / chance  (docs tunjuk contoh 1.98 @ 49.99)
        win_chance = bet_value if rule == "under" else (100.0 - bet_value)
        win_chance = self._cap(win_chance, 0.01, 99.99)
        theo_multiplier = 99.0 / win_chance
        # bulatkan ke 2–4 dp supaya dekat dengan sistem
        theo_multiplier = float(f"{theo_multiplier:.4f}")
        return rule, bet_value, theo_multiplier

    # -------------- Strategy loops --------------
    def martingale(self):
        print("🚀 Wolf.bet Auto Dice Bot Started")
        bal = self.get_balance_currency(self.currency)
        if bal is None:
            print("❌ Tak dapat baca balance. Semak token/endpoint atau headers.")
            return
        print(f"💰 Balance: {bal:.8f} {self.currency.upper()}")

        self.session_profit = 0.0
        self.current_bet = self.base_bet

        while True:
            # safety
            if self.session_profit <= self.stop_loss:
                print(f"🛑 Stop-loss triggered: {self.session_profit:.8f} {self.currency.upper()}")
                break
            if self.session_profit >= self.take_profit:
                print(f"✅ Take-profit triggered: {self.session_profit:.8f} {self.currency.upper()}")
                break
            if self.current_bet > self.max_bet:
                print(f"⚠️ current_bet {self.current_bet} > max_bet {self.max_bet} → reset base.")
                self.current_bet = self.base_bet

            rule, bet_value, theo_mult = self.chance_to_rule_and_threshold()

            if self.debug:
                print(f"🎯 BET | {rule.upper()} {bet_value:.2f} | amt={self.current_bet:.8f} {self.currency} | theo_mult≈{theo_mult}")

            data, rate_headers = self.place_dice_bet(
                amount=self.current_bet,
                rule=rule,
                bet_value=bet_value,
                multiplier=theo_mult
            )

            if rate_headers and rate_headers[0] and rate_headers[1] and self.debug:
                print(f"⏳ Rate-limit: {rate_headers[1]}/{rate_headers[0]} remaining")

            if not data:
                print("⚠️ Tiada data bet (network/parse). Re-try lepas cooldown.")
                time.sleep(self.cooldown)
                continue

            # API success sample contains keys: bet{...}, user_balance{...}
            bet = data.get("bet")
            ub  = data.get("user_balance")

            if bet is None:
                # kemungkinan error 400/422 format JSON { error: ... }
                err = data.get("error") or data
                print(f"❌ Bet error: {err}")
                time.sleep(self.cooldown)
                continue

            state = bet.get("state")  # "win" / "loss"
            profit = float(bet.get("profit", 0) or 0)

            if state == "win":
                self.session_profit += profit
                print(f"✅ WIN | roll={bet.get('result_value')} | profit=+{profit:.8f} | session={self.session_profit:.8f}")
                self.current_bet = self.base_bet
            else:
                # pada loss, API `profit` biasanya negatif / 0 — kita tolak amount manual jika perlu
                loss_amount = float(bet.get("amount", self.current_bet))
                self.session_profit -= float(loss_amount)
                print(f"❌ LOSE | roll={bet.get('result_value')} | -{loss_amount:.8f} | session={self.session_profit:.8f}")
                self.current_bet = round(self.current_bet * self.multiplier_factor, 12)

            if ub and "amount" in ub and self.debug:
                try:
                    print(f"💼 New balance: {float(ub['amount']):.8f} {ub.get('currency','').upper()}")
                except Exception:
                    pass

            # Jika rate-limit habis, tunggu 60s (ikut docs)
            if rate_headers and rate_headers[1] == "0":
                print("⏱️ Rate-limit habis. Tidur 60s.")
                time.sleep(60)
            else:
                time.sleep(self.cooldown)

    def run(self):
        self.martingale()


if __name__ == "__main__":
    bot = WolfBetBot("config.json")
    bot.run()
