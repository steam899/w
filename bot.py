import json
import time
import random
import requests
import sys

# ---------------- ANSI colors ----------------
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"
RESET   = "\033[0m"

GRADIENT = [RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA]

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
        self.multiplier_factor = float(self.cfg.get("multiplier", 2.0))
        self.max_bet = float(self.cfg.get("max_bet", 0.0001))
        self.chance = float(self.cfg.get("chance", 49.5))
        self.rule_mode = str(self.cfg.get("rule_mode", "auto")).lower()
        self.take_profit = float(self.cfg.get("take_profit", 0.0005))
        self.stop_loss = float(self.cfg.get("stop_loss", -0.0005))
        self.cooldown = float(self.cfg.get("cooldown_sec", 1.0))
        self.debug = bool(self.cfg.get("debug", True))
        self.auto_start = bool(self.cfg.get("auto_start", False))
        self.auto_start_delay = int(self.cfg.get("auto_start_delay", 5))

        self.session_profit = 0.0
        self.current_bet = self.base_bet

        self._summary_drawn = False
        self._summary_height = 5

    # ---------------- REST calls ----------------
    def _get(self, path):
        try:
            r = requests.get(f"{API_BASE}{path}", headers=self.headers, timeout=20)
            return r
        except Exception as e:
            if self.debug:
                print(f"{RED}⚠️ GET {path} network error:{RESET} {e}")
            return None

    def _post(self, path, payload):
        try:
            r = requests.post(f"{API_BASE}{path}", headers=self.headers, json=payload, timeout=20)
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
        except Exception:
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
        win_chance = bet_value if rule == "under" else (100.0 - bet_value)
        multiplier = 99.0 / win_chance
        multiplier = float(f"{multiplier:.4f}")

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
        except Exception:
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

    # -------------- UI helpers --------------
    def _summary_lines(self, start_balance, current_balance, total_bets, win, lose):
        return [
            f"{YELLOW}📊 Ringkasan Sesi{RESET}",
            f"   🔹 Baki awal : {start_balance:.8f} {self.currency.upper()}",
            f"   🔹 Baki      : {current_balance:.8f} {self.currency.upper()}",
            f"   🔹 Untung/Rugi: {self.session_profit:.8f} {self.currency.upper()}",
            f"   🔹 Jumlah BET : {total_bets} (WIN {win} / LOSE {lose})",
        ]

    def _insert_bet_and_refresh_summary(self, bet_line, start_balance, current_balance, total_bets, win, lose):
        n = self._summary_height
        if not self._summary_drawn:
            print("\n" * n)
            self._summary_drawn = True

        sys.stdout.write(f"\x1b[{n}F")
        sys.stdout.write("\x1b[1L")
        print(bet_line)
        sys.stdout.write("\x1b[1E")

        lines = self._summary_lines(start_balance, current_balance, total_bets, win, lose)
        for i, line in enumerate(lines):
            sys.stdout.write("\x1b[2K")
            sys.stdout.write(line)
            if i < len(lines) - 1:
                sys.stdout.write("\n")
        sys.stdout.flush()

    # -------------- Logo --------------
    def draw_logo(self):
        logo_text = "W O L F   D I C E   B O T"
        for i, c in enumerate(logo_text):
            color = GRADIENT[i % len(GRADIENT)]
            print(f"{color}{c}{RESET}", end="")
        print("\n")
        emoji_line = "🎲🐺  🎲🐺  🎲🐺  🎲🐺  🎲🐺"
        print(emoji_line, "\n")

    # -------------- Strategy loops --------------
    def martingale(self):
        self.draw_logo()
        start_balance = self.get_balance_currency(self.currency)
        if start_balance is None:
            print(f"{RED}❌ Tak dapat baca balance. Semak token/endpoint atau headers.{RESET}")
            return
        print(f"{GREEN}💰 Baki awal:{RESET} {start_balance:.8f} {self.currency.upper()}")

        self.session_profit = 0.0
        self.current_bet = self.base_bet
        win_count, lose_count, total_bets = 0, 0, 0
        current_balance = start_balance

        while True:
            if self.session_profit <= self.stop_loss:
                print(f"\n{YELLOW}🛑 Stop-loss triggered:{RESET} {self.session_profit:.8f} {self.currency.upper()}")
                break
            if self.session_profit >= self.take_profit:
                print(f"\n{GREEN}✅ Take-profit triggered:{RESET} {self.session_profit:.8f} {self.currency.upper()}")
                break
            if self.current_bet > self.max_bet:
                print(f"\n{CYAN}⚠️ current_bet reset base.{RESET}")
                self.current_bet = self.base_bet

            rule, bet_value = self.chance_to_rule_and_threshold()

            data, _ = self.place_dice_bet(
                amount=self.current_bet,
                rule=rule,
                bet_value=bet_value
            )
            if not data:
                time.sleep(self.cooldown)
                continue

            bet = data.get("bet")
            ub  = data.get("user_balance")
            if bet is None:
                time.sleep(self.cooldown)
                continue

            state = bet.get("state")
            profit = float(bet.get("profit", 0) or 0)
            total_bets += 1
            result_value = bet.get("result_value")

            if state == "win":
                self.session_profit += profit
                win_count += 1
                outcome = f"{GREEN}WIN +{profit:.8f}{RESET}"
                self.current_bet = self.base_bet
            else:
                loss_amount = float(bet.get("amount", self.current_bet))
                self.session_profit -= float(loss_amount)
                lose_count += 1
                outcome = f"{RED}LOSE -{loss_amount:.8f}{RESET}"
                self.current_bet = round(self.current_bet * self.multiplier_factor, 12)

            if self.session_profit >= 0:
                profit_amount = f"{GREEN}{self.session_profit:.8f}{RESET}"
            else:
                profit_amount = f"{RED}{self.session_profit:.8f}{RESET}"

            MAGENTA_SEP = f"{MAGENTA}|{RESET}"

            bet_line = f"🎲🐺 {MAGENTA_SEP} {result_value} {MAGENTA_SEP} {BLUE}Bet{RESET} {self.current_bet:.8f} {MAGENTA_SEP} {outcome} {MAGENTA_SEP} {YELLOW}P{RESET} {profit_amount}"

            self._insert_bet_and_refresh_summary(
                bet_line=bet_line,
                start_balance=start_balance,
                current_balance=current_balance,
                total_bets=total_bets,
                win=win_count,
                lose=lose_count,
            )

            time.sleep(self.cooldown)

        print("\n")
        final_lines = self._summary_lines(start_balance, current_balance, total_bets, win_count, lose_count)
        print("\n".join(final_lines))

    def run(self):
        self.martingale()


if __name__ == "__main__":
    bot = WolfBetBot("config.json")

    while True:
        bot.run()
        if not bot.auto_start:
            break
        print(f"\n{CYAN}🔄 Auto-restart in {bot.auto_start_delay} seconds...{RESET}")
        time.sleep(bot.auto_start_delay)
