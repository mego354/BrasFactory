"""
Management command to run the Telegram Bot in Long-Polling mode.
Usage:
  python manage.py run_telegram_bot
  python manage.py run_telegram_bot --test-phone 01000000000 --test-cmd "/start"
"""
import time
import requests
from django.core.management.base import BaseCommand
from django.conf import settings

from notifications.services import TelegramBot, process_telegram_update


class Command(BaseCommand):
    help = 'Runs the Factory Telegram Bot in polling mode or executes a test simulation.'

    def add_arguments(self, parser):
        parser.add_argument('--test-phone', type=str, help='Test phone number to simulate contact login')
        parser.add_argument('--test-cmd', type=str, help='Test command string to simulate')
        parser.add_argument('--base-url', type=str, default='http://127.0.0.1:8000', help='Base URL for web links')

    def handle(self, *args, **options):
        test_phone = options.get('test_phone')
        test_cmd = options.get('test_cmd')
        base_url = options.get('base_url')

        # Test simulation mode
        if test_phone or test_cmd:
            self.stdout.write(self.style.SUCCESS("🤖 Running Telegram Bot in SIMULATION mode..."))
            chat_id = "test_chat_999"

            if test_phone:
                self.stdout.write(f"Simulating contact sharing for phone: {test_phone}")
                update_contact = {
                    'message': {
                        'chat': {'id': chat_id},
                        'from': {'first_name': 'مستخدم تجريبي', 'username': 'testuser'},
                        'contact': {'phone_number': test_phone}
                    }
                }
                res = process_telegram_update(update_contact, base_url=base_url)
                self.stdout.write(f"Contact login result: {res}")

            if test_cmd:
                self.stdout.write(f"Simulating command: {test_cmd}")
                update_cmd = {
                    'message': {
                        'chat': {'id': chat_id},
                        'from': {'first_name': 'مستخدم تجريبي', 'username': 'testuser'},
                        'text': test_cmd
                    }
                }
                res = process_telegram_update(update_cmd, base_url=base_url)
                self.stdout.write(f"Command result: {res}")

            return

        # Real polling mode
        token = TelegramBot.get_token()
        if not token:
            self.stdout.write(self.style.WARNING(
                "⚠️ TELEGRAM_BOT_TOKEN is not set in .env!\n"
                "To connect to live Telegram, add your token from @BotFather in .env:\n"
                "TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrs\n\n"
                "Running in interactive console simulation loop (type messages or 'exit'):"
            ))
            while True:
                try:
                    user_input = input("Telegram User Input > ").strip()
                    if user_input.lower() in ('exit', 'quit'):
                        break
                    if not user_input:
                        continue

                    # Check if user typed a phone
                    if user_input.startswith('+') or (user_input.isdigit() and len(user_input) >= 10):
                        update = {
                            'message': {
                                'chat': {'id': 'console_user_1'},
                                'from': {'first_name': 'مستخدم الكونسول'},
                                'contact': {'phone_number': user_input}
                            }
                        }
                    else:
                        update = {
                            'message': {
                                'chat': {'id': 'console_user_1'},
                                'from': {'first_name': 'مستخدم الكونسول'},
                                'text': user_input
                            }
                        }
                    res = process_telegram_update(update, base_url=base_url)
                    self.stdout.write(f"Action: {res}")
                except (KeyboardInterrupt, EOFError):
                    break
            return

        self.stdout.write(self.style.SUCCESS(f"🤖 Starting Telegram Bot polling (Token: {token[:8]}...)..."))
        offset = 0
        while True:
            try:
                url = TelegramBot.api_url('getUpdates')
                resp = requests.get(url, params={'offset': offset, 'timeout': 30}, timeout=35)
                data = resp.json()
                if not data.get('ok'):
                    self.stdout.write(self.style.ERROR(f"Telegram API error: {data}"))
                    time.sleep(3)
                    continue

                for item in data.get('result', []):
                    offset = item['update_id'] + 1
                    res = process_telegram_update(item, base_url=base_url)
                    self.stdout.write(f"Processed update {item['update_id']}: {res.get('status')}")

            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS("\nStopped bot polling."))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Polling loop exception: {e}"))
                time.sleep(3)
