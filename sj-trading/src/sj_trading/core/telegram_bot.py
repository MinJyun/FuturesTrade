import time
import requests
import traceback
from typing import Optional
from shioaji.constant import Action, FuturesPriceType, StockPriceType
from .notification import NotificationManager
from ..data.info import InfoManager
from ..trading.order import OrderManager

class TelegramBotManager:
    """
    Long-polling Telegram Bot to interact with the Shioaji trading system.
    Runs in a simple while loop to avoid async collision with Shioaji's threads.
    """
    def __init__(self, order_manager: OrderManager, simulation: bool):
        self._notif = NotificationManager()
        self.tg_token = self._notif.tg_token
        self.tg_chat_id = self._notif.tg_chat_id
        
        self.om = order_manager
        self.im = InfoManager()
        self.simulation = simulation
        self.env_name = "SIMULATED" if simulation else "REAL"

        if not self.tg_token or not self.tg_chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env")

        self.last_update_id = 0

    def run(self):
        """Starts the long polling loop."""
        self._notif.notify(f"Bot Started [{self.env_name}]", "Telegram listener is active and waiting for commands.")
        
        url = f"https://api.telegram.org/bot{self.tg_token}/getUpdates"
        
        while True:
            params = {"timeout": 10, "offset": self.last_update_id}
            try:
                response = requests.get(url, params=params, timeout=15)
                if response.status_code != 200:
                    time.sleep(2)
                    continue

                data = response.json()
                if not data.get("ok"):
                    time.sleep(2)
                    continue

                for update in data.get("result", []):
                    self.last_update_id = update["update_id"] + 1
                    
                    message = update.get("message")
                    if not message or "text" not in message:
                        continue
                        
                    chat_id = str(message["chat"]["id"])
                    text = message["text"].strip()

                    # Security Check: Only accept messages from AUTHORIZED chat_id
                    if chat_id != str(self.tg_chat_id):
                        print(f"⚠️ Unauthorized access attempt from Chat ID: {chat_id}. Message: {text}")
                        continue

                    # Process authorized command
                    self._handle_command(text)

            except requests.exceptions.RequestException:
                time.sleep(2) # Network issue, wait and retry
            except Exception as e:
                print(f"Error in bot polling loop: {e}")
                time.sleep(5)

    def _send_reply(self, text: str):
        """Send a message back to the authorized chat_id."""
        url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
        payload = {"chat_id": self.tg_chat_id, "text": text, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Failed to send bot reply: {e}")

    def _handle_command(self, text: str):
        """Parse and execute the Telegram command."""
        print(f"➡️ Received command: {text}")
        
        parts = text.split()
        if not parts:
            return
            
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "/start" or cmd == "/help":
                self._cmd_help()
            elif cmd == "/list":
                self._cmd_list()
            elif cmd == "/cancelall":
                self._cmd_cancelall()
            elif cmd == "/cancel":
                self._cmd_cancel(args)
            elif cmd == "/update":
                self._cmd_update(args)
            elif cmd == "/order":
                self._cmd_order(args)
            elif cmd == "/info":
                self._cmd_info(args)
            else:
                self._send_reply(f"❌ Unknown command: `{cmd}`. Type /help for options.")
        except Exception as e:
            err_msg = traceback.format_exc()
            print(err_msg)
            self._send_reply(f"❌ Error executing command:\n`{e}`")

    # ================= COMMAND HANDLERS =================

    def _cmd_help(self):
        msg = (
            f"🤖 *SJ-Trading Bot ({self.env_name})*\n\n"
            "*/list* - List active limit orders\n"
            "*/order <code> <buy/sell> <price> <qty>* - Place limit order (e.g. `/order TMFR1 buy 33800 1`)\n"
            "*/update <id> <price>* - Update order price\n"
            "*/cancel <id>* - Cancel specific order\n"
            "*/cancelall* - Cancel all active orders\n"
            "*/info <query>* - Search for contract"
        )
        self._send_reply(msg)

    def _cmd_list(self):
        # Force a status update before listing
        self.om.update_status()
        trades = self.om.list_trades()
        
        # Filter for active orders (not filled/cancelled/failed)
        active_statuses = ["PendingSubmit", "PreSubmitted", "Submitted", "PartFilled"]
        active_trades = [t for t in trades if t.status.status.name in active_statuses]
        
        if not active_trades:
            self._send_reply("📝 No active trades/orders found.")
            return
            
        lines = [f"📊 *Active Trades/Orders ({self.env_name})*"]
        for t in active_trades:
            # Check if there is a modified price in the status, otherwise fallback to original order price
            # In Shioaji, t.status.deal_quantity might exist, but for price, t.status.modified_price often holds updates
            current_price = getattr(t.status, "modified_price", t.order.price)
            if current_price == 0: # Sometimes modified_price is 0 if not modified
                current_price = t.order.price
            lines.append(f"⏳ `{t.status.id}` | {t.contract.code} | {t.order.action.name} {t.order.quantity} @ {current_price} | {t.status.status.name}")
            
        self._send_reply("\n".join(lines))

    def _cmd_update(self, args: list):
        if len(args) < 2:
            self._send_reply("❌ Usage: `/update <id> <new_price>`\nExample: `/update ee3aefe6 33900`")
            return
            
        order_id = args[0]
        try:
            new_price = float(args[1])
            self.om.update_order_price(order_id, new_price)
            self._send_reply(f"✏️ Update request sent: Order `{order_id}` to price `{new_price}`.")
        except ValueError as ve:
            self._send_reply(f"❌ Failed to update: {ve}")
        except Exception as e:
            self._send_reply(f"❌ Error updating order:\n`{e}`")

    def _cmd_cancel(self, args: list):
        if not args:
            self._send_reply("❌ Please provide an Order ID: `/cancel <id>`")
            return
            
        order_id = args[0]
        self.om.cancel_order(order_id)
        self._send_reply(f"🗑️ Cancellation request sent for Order `{order_id}`.")

    def _cmd_cancelall(self):
        count = self.om.cancel_all_orders()
        self._send_reply(f"🗑️ Sent cancellation requests for {count} order(s).")

    def _cmd_order(self, args: list):
        if len(args) < 4:
            self._send_reply("❌ Usage: `/order <code> <buy/sell> <price> <qty>`\nExample: `/order TMFR1 buy 33800 1`")
            return
            
        code = args[0].upper()
        action_str = args[1].lower()
        price = float(args[2])
        qty = int(args[3])
        
        act_enum = Action.Buy if action_str == "buy" else Action.Sell
        
        # Check if Future or Stock via InfoManager
        is_future = False
        res = self.im.search(code)
        if "Futures" in res and not res["Futures"].is_empty():
            is_future = True
            
        symbol_type = "Future" if is_future else "Stock"
        
        self._send_reply(f"⚙️ Placing {self.env_name} {symbol_type} Limit Order: {act_enum.name} {qty} {code} @ {price} ...")
        
        if is_future:
            trade = self.om.place_futures_order(
                code=code, action=act_enum, price=price, quantity=qty, price_type=FuturesPriceType.LMT
            )
        else:
            trade = self.om.place_stock_order(
                code=code, action=act_enum, price=price, quantity=qty, price_type=StockPriceType.LMT
            )
            
        self._send_reply(f"✅ Order Placed Successfully!\nID: `{trade.status.id}`\nStatus: {trade.status.status.name}")

    def _cmd_info(self, args: list):
        if not args:
            self._send_reply("❌ Usage: `/info <query>`")
            return
            
        query = args[0]
        results = self.im.search(query)
        
        lines = []
        if "Futures" in results and not results["Futures"].is_empty():
            lines.append("📈 *Futures*")
            for row in results["Futures"].iter_rows(named=True):
                lines.append(f"`{row['Symbol']}` - {row['Name']}")
                
        if "Stocks" in results and not results["Stocks"].is_empty():
            lines.append("🏢 *Stocks*")
            # Limit to 5 results to avoid telegram message size limits
            for row in results["Stocks"].head(5).iter_rows(named=True):
                lines.append(f"`{row['證券代號']}` - {row['股票名稱']}")
                
        if not lines:
            self._send_reply(f"❌ No results found for '{query}'.")
        else:
            self._send_reply("\n".join(lines))
