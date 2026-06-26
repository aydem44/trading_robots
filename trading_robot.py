#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
import sys
import time
import pandas as pd
from pybit.unified_trading import HTTP
from dotenv import load_dotenv


class SimpleBybitBot:
    """
    Тестовый торговый робот для Bybit для самообразования.
    Стратегия: Покупка на кресте скользящийх средний( быстрая MA > медленной MA), продажа при мертвом кресте (быстрая MA < медленной MA).
    Маржинальная торговля исключена. Сделки только на Spot.
    """

    def __init__(self, api_key, api_secret, testnet=False):

        # Попробуем зайти через прокси
        proxy_url="http://pydA627P:CPcsSL91@156.244.211.110:64902"
        os.environ['HTTP_PROXY'] = proxy_url
        os.environ['HTTPS_PROXY'] = proxy_url
        
        # Настраиваем подключение в зависимости от режима (testnet/mainnet)
        self.session = HTTP(
            api_key=api_key,
            api_secret=api_secret,
        )
        print("⚠️ Внимание! РЕАЛЬНАЯ ТОРГОВЛЯ (будут использоваться настоящие средства)")

        # Параметры торговли
        self.symbol = "MNTUSDT"  # Торговая пара
        self.fast_ma_period = 10  # Период быстрой скользящей средней
        self.slow_ma_period = 30  # Период медленной скользящей средней
        self.trade_quantity = 10  # Количество монет для торговли 
        self.in_position = False  # Флаг открытой позиции
        self.last_signal = None  # Последний сигнал ('buy' или 'sell')

        print(f"📊 Торговая пара: {self.symbol}")
        print(f"📈 Периоды MA: быстрая={self.fast_ma_period}, медленная={self.slow_ma_period}")
        print("-" * 50)

    def get_klines(self, limit=50):

        # Получение исторических свечей (K-line данных) с биржи. Возвращает датафрейм с ценами открытия, закрытия, максимум, минимум
        try:
            # Запрашиваем свечи
            response = self.session.get_kline(
                category="spot",  # Спотовый рынок
                symbol=self.symbol,
                interval=5,  # 5-минутные свечи
                limit=limit
            )

            if response['retCode'] == 0:
                # Преобразуем данные в DataFrame для удобной работы [citation:4]
                kline_data = response['result']['list']
                df = pd.DataFrame(
                    kline_data,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
                )

                # Конвертируем строки в числа и меняем порядок (от старых к новым)
                df = df.astype({
                    'open': float,
                    'high': float,
                    'low': float,
                    'close': float,
                    'volume': float
                })
                df = df.iloc[::-1].reset_index(drop=True)  # Переворачиваем

                return df
            else:
                print(f"Ошибка API: {response['retMsg']}")
                return None

        except Exception as e:
            print(f"Ошибка при получении данных: {e}")
            return None

    def calculate_signals(self, df):
        # Расчет сигнала. На входе датафрейм. На выходе 'buy', 'sell' или None (нет сигнала)

        if df is None or len(df) < self.slow_ma_period:
            return None

        # Рассчитываем простые скользящие средние (SMA)
        df['fast_ma'] = df['close'].rolling(window=self.fast_ma_period).mean()
        df['slow_ma'] = df['close'].rolling(window=self.slow_ma_period).mean()

        # Получаем последние значения
        current_fast = df['fast_ma'].iloc[-1]
        current_slow = df['slow_ma'].iloc[-1]
        prev_fast = df['fast_ma'].iloc[-2]
        prev_slow = df['slow_ma'].iloc[-2]

        # Логируем текущие значения для отладки
        current_price = df['close'].iloc[-1]
        print(f"Цена: {current_price:.4f} | MA{self.fast_ma_period}: {current_fast:.4f} | MA{self.slow_ma_period}: {current_slow:.4f}")

        # Проверяем пересечения
        if prev_fast <= prev_slow and current_fast > current_slow:
            return 'buy'  # Золотой крест (быстрая пересекает медленную снизу вверх)
        elif prev_fast >= prev_slow and current_fast < current_slow:
            return 'sell'  # Мертвый крест (быстрая пересекает медленную сверху вниз)
        else:
            return None

    def place_order(self, side):
        # Размещение ордера на бирже.

        try:
            # Проверяем, не пытаемся ли мы продать то, чего не купили
            if side == "Sell" and not self.in_position:
                print("⏭️  Нет позиции для продажи")
                return

            # В ордер покупки добавим комиссию
            qty_plus=1
            if side == "Buy":
                qty_plus=1.1

            # Отправляем рыночный ордер [citation:6]
            response = self.session.place_order(
                category="spot",
                symbol=self.symbol,
                side=side,
                orderType="Market",
                qty=str(self.trade_quantity*qty_plus),
                marketUnit='baseCoin',
                timeInForce="GTC"
            )

            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                print(f"✅ Успешный ордер {side} | ID: {order_id}")

                # Обновляем состояние позиции
                self.in_position = (side == "Buy")
                return True
            else:
                print(f"❌ Ошибка ордера: {response['retMsg']}")
                return False

        except Exception as e:
            print(f"❌ Ошибка при размещении ордера: {e}")
            return False

    def get_account_info(self):
        # Получение информации о кошельке (баланс USDT и BTC).

        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED",
                coin="USDT,BTC,MNT"
            )

            if response['retCode'] == 0:
                balances = response['result']['list'][0]['coin']
                usdt_balance = 0
                btc_balance = 0
                mnt_balance = 0

                for coin in balances:
                    if coin['coin'] == 'USDT':
                        usdt_balance = float(coin['walletBalance'])
                    elif coin['coin'] == 'BTC':
                        btc_balance = float(coin['walletBalance'])
                    elif coin['coin'] == 'MNT':
                        mnt_balance = float(coin['walletBalance'])

                print(f"💰 Баланс: {usdt_balance:.2f} USDT | {btc_balance:.6f} BTC | {mnt_balance:.6f} MNT")
                return usdt_balance, btc_balance, mnt_balance
            else:
                print(f"Не удалось получить баланс: {response['retMsg']}")
                return 0, 0, 0

        except Exception as e:
            print(f"Ошибка баланса: {e}")
            return 0, 0, 0

    def run(self, interval_seconds=60):
        # Запуск основного цикла бота.

        print(f"🚀 Запуск бота (проверка каждые {interval_seconds} сек)")
        print("Нажмите Ctrl+C для остановки\n")

        try:
            while True:
                # Получаем текущие балансы
                usdt_balance, btc_balance, mnt_balance = self.get_account_info()

                # Обновляем флаг позиции на основе реального баланса
                self.in_position = mnt_balance > 11

                # Получаем рыночные данные
                df = self.get_klines(limit=self.slow_ma_period + 10)

                if df is not None:
                    # Рассчитываем сигналы
                    signal = self.calculate_signals(df)

                    # Проверяем, изменился ли сигнал с прошлого раза
                    if signal: #and signal != self.last_signal:
                        if signal == 'buy' and not self.in_position:
                            print(f"\n🟢 СИГНАЛ К ПОКУПКЕ (MA{self.fast_ma_period} > MA{self.slow_ma_period})")
                            self.place_order("Buy")
                            self.last_signal = signal

                        elif signal == 'sell' and self.in_position:
                            print(f"\n🔴 СИГНАЛ К ПРОДАЖЕ (MA{self.fast_ma_period} < MA{self.slow_ma_period})")
                            self.place_order("Sell")
                            self.last_signal = signal

                # Ждем до следующей проверки
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\n\n🛑 Бот остановлен пользователем")
        except Exception as e:
            print(f"\n💥 Критическая ошибка: {e}")

def main():

    # Загружаем переменные из файла .env в окружение ОС
    load_dotenv("trading_robot.env")

    # Получаем ключи из переменных окружения
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")

    if not api_key or not api_secret:
        print("❌ Ошибка: Не найдены API ключи в файле .env")
        print("Создайте файл .env с содержимым:")
        print("BYBIT_API_KEY=ваш_ключ")
        print("BYBIT_API_SECRET=ваш_секрет")
        return

    # Выбор режима работы
    print("Запускаем торговлю на реальные деньги?")
    print("1 - Да! Подтверждаю")
    print("2 - Нет! Надо вернуться к коду.")
    choice = input("Ваш выбор (1/2): ").strip()

    if choice == "2":
        print("Выход из программы...")
        sys.exit(0)  # 0 - успешное завершение

    # Создаем и запускаем бота
    bot = SimpleBybitBot(api_key, api_secret, testnet=False)

    # Частота проверки: 60 секунд [citation:1]
    bot.run(interval_seconds=60)

if __name__ == "__main__":
    main()


# In[ ]:




