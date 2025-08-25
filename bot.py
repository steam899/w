import json
import time
import random
import requests

# ANSI colors
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

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
            "X-Requested-With": "XMLHttpRequest",
        }

        self.currency = str(self.cfg.get("currency", "btc")).lower()
        self.base_bet = float(self.cfg.get("base_bet", 0.00000001))
        self.multiplier_factor = float(self.cfg.get("multiplier", 2.0))  # utk gandakan stake bila kalah
        self.max_bet = float(self.cfg.get("max_bet", 0.0001))
        self.chance = float(self.cfg.get("chance", 49.5))
        self.rule_mode = str(self.cfg.get("rule_mode", "auto")).lower()
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
                print(f"{YELLOW}[GET {path}] HTTP {r.status_code}:{RESET} {r.text[:200]}")
            return r
        except Exception as e:
            if self.debug:
                print(f"{RED}⚠️ GET {path} network error:{RESET} {e}")
            return None

    def _post(self, path, payload):
        try:
            r = requests.post(f"{API_BASE}{path}", headers=self.headers, json=payload, timeout=20)
            if self.debug and r.status_code != 200:
                print(f"{BLUE}[POST {path}] HTTP {r.status_code}:{RESET} {r.text[:200]}")
            return r
        except Exception as e:
            if self.debug:
                print(f"{YELLOW}⚠️ POST {path} network error:{RESET} {e}")
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
                print(f"{RED}⚠️ Parse balances JSON error:{RESET} {e} | raw: {r.text[:200]}")
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

    def place_dice_bet(self, amount, rule, bet_value):
        amount = round(float(amount), 8)

        # ✅ multiplier wajib ikut formula win_chance
        win_chance = bet_value if rule == "under" else (100.0 - bet_value)
        multiplier = 99.0 / win_chance
        multiplier = float(f"{multiplier:.4f}")  # round 4 dp

        payload = {
            "currency": self.currency,
            "game": "dice",
            "amount": str(amount),
            "rule": rule,
            "bet_value": str(bet_value),
            "multiplier": str(multiplier)
        }
        r = self._post("/bet/place", payload)
        if not r:
            return None, None

        rl_limit = r.headers.get("x-ratelimit-limit")
        rl_left  = r.headers.get("x-ratelimit-remaining")

        try:
            data = r.json()
            return data, (rl_limit, rl_left)
        except Exception as e:
            if self.debug:
                print(f"{RED}⚠️ Parse bet JSON error:{RESET} {e} | raw: {r.text[:200]}")
            return None, (rl_limit, rl_left)

    # -------------- Dice helpers --------------
    @staticmethod
    def _cap(val, lo, hi):
        return max(lo, min(hi, val))

    def chance_to_rule_and_threshold(self):
        chance = self._cap(self.chance, 0.01, 99.99)

        if self.rule_mode == "over":
            rule = "over"
            bet_value = self._cap(100.0 - chance, 0.01, 99.99)
        elif self.rule_mode == "under":
            rule = "under"
            bet_value = self._cap(chance, 0.01, 99.99)
        else:
            if random.randint(0, 1) == 1:
                rule = "under"
                bet_value = self._cap(chance, 0.01, 99.99)
            else:
                rule = "over"
                bet_value = self._cap(100.0 - chance, 0.01, 99.99)

        return rule, bet_value

    # -------------- Strategy loops --------------
    def martingale(self):
        print(f"{CYAN}🚀 Wolf.bet Auto Dice Bot Started{RESET}")
        bal = self.get_balance_currency(self.currency)
        if bal is None:
            print(f"{RED}❌ Tak dapat baca balance. Semak token/endpoint atau headers.{RESET}")
            return
        print(f"{GREEN}💰 Balance:{RESET} {bal:.8f} {self.currency.upper()}")

        self.session_profit = 0.0
        self.current_bet = self.base_bet

        while True:
            # safety checks
            if self.session_profit <= self.stop_loss:
                print(f"{YELLOW}🛑 Stop-loss triggered:{RESET} {self.session_profit:.8f} {self.currency.upper()}")
                break
            if self.session_profit >= self.take_profit:
                print(f"{GREEN}✅ Take-profit triggered:{RESET} {self.session_profit:.8f} {self.currency.upper()}")
                break
            if self.current_bet > self.max_bet:
                print(f"{CYAN}⚠️ current_bet reset base.{RESET}")
                self.current_bet = self.base_bet

            rule, bet_value = self.chance_to_rule_and_threshold()

            if self.debug:
                print(f"{BLUE}🎯 BET{RESET} | {rule.upper()} {bet_value:.2f} | amt={self.current_bet:.8f} {self.currency}")

            data, rate_headers = self.place_dice_bet(
                amount=self.current_bet,
                rule=rule,
                bet_value=bet_value
            )

            if rate_headers and rate_headers[0] and rate_headers[1] and self.debug:
                print(f"{BLUE}⏳ Rate-limit{RESET}: {rate_headers[1]}/{rate_headers[0]} remaining")

            if not data:
                print("⚠️ Tiada data bet (network/parse). Re-try lepas cooldown.")
                time.sleep(self.cooldown)
                continue

            bet = data.get("bet")
            ub  = data.get("user_balance")

            if bet is None:
                err = data.get("error") or data
                print(f"{RED}❌ Bet error:{RESET} {err}")
                time.sleep(self.cooldown)
                continue

            state = bet.get("state")
            profit = float(bet.get("profit", 0) or 0)

            if state == "win":
                self.session_profit += profit
                print(f"{GREEN}✅ WIN{RESET} | roll={bet.get('result_value')} | profit=+{profit:.8f} | session={self.session_profit:.8f}")
                self.current_bet = self.base_bet
            else:
                loss_amount = float(bet.get("amount", self.current_bet))
                self.session_profit -= float(loss_amount)
                print(f"{RED}❌ LOSE{RESET} | roll={bet.get('result_value')} | -{loss_amount:.8f} | session={self.session_profit:.8f}")
                self.current_bet = round(self.current_bet * self.multiplier_factor, 12)

            if ub and "amount" in ub and self.debug:
                try:
                    print(f"{CYAN}💼 New balance:{RESET} {float(ub['amount']):.8f} {ub.get('currency','').upper()}")
                except Exception:
                    pass

            if rate_headers and rate_headers[1] == "0":
                print(f"{RED}⏱️ Rate-limit habis. Tidur 60s.{RESET}")
                time.sleep(60)
            else:
                time.sleep(self.cooldown)

    def run(self):
        self.martingale()


if __name__ == "__main__":
    bot = WolfBetBot("config.json")
    bot.run()
