import sqlite3
import unittest
from unittest import mock
from unittest.mock import MagicMock
from unittest.mock import patch
from main import check_stock_existence
from main import get_stock_price
from main import get_current_usd_rub
from main import convert_rub_to_dol
import main as bot
from typing import List, Tuple, Text


# Class Test for User Class
class UserTestCase(unittest.TestCase):
    check_telegram_id = 5555555
    create_telegram_id = 4444444

    def setUp(self) -> None:
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS users '
                       '(telegram_id INTEGER PRIMARY KEY)')
        cursor.execute('INSERT INTO users (telegram_id) VALUES (?)',
                       (self.check_telegram_id,))
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE telegram_id = ?',
                       (self.check_telegram_id,))
        cursor.execute('DELETE FROM users WHERE telegram_id = ?',
                       (self.create_telegram_id,))
        conn.commit()
        conn.close()

    def test_check_user_data(self) -> None:
        user = bot.User(self.check_telegram_id)
        result = user.check_user_data()
        self.assertEqual(result, (self.check_telegram_id,))

    def test_create_user_record(self) -> None:
        user = bot.User(self.create_telegram_id)
        result = user.create_user_record()
        self.assertEqual(result, self.create_telegram_id)


class StockTestCase(unittest.TestCase):

    check_telegram_id = 999999999999
    create_telegram_id = 999999999998

    create_stock = bot.Stock(create_telegram_id, 'SBER', 100, 10, '2024-10-10 03:09:21.123454')

    test_stock_values = (check_telegram_id, 'SBER', 100, 10, '2024-10-10 03:09:21.123454')

    def setUp(self) -> None:
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS stocks
                          (owner_id INTEGER, stock_id TEXT, quantity INTEGER, unit_price REAL, purchase_date TIMESTAMP, FOREIGN KEY (owner_id) REFERENCES users(telegram_id) ON DELETE CASCADE)''')
        cursor.execute('INSERT INTO users (telegram_id) VALUES (?)', (self.check_telegram_id,))
        cursor.execute('INSERT INTO stocks VALUES (?, ?, ?, ?, ?)', self.test_stock_values)
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE telegram_id = ?', (self.check_telegram_id,))
        cursor.execute('DELETE FROM stocks WHERE owner_id = ?', (self.check_telegram_id,))
        cursor.execute('DELETE FROM users WHERE telegram_id = ?', (self.create_telegram_id,))
        cursor.execute('DELETE FROM stocks WHERE owner_id = ?', (self.create_telegram_id,))
        conn.commit()
        conn.close()

    def test_add_stock(self):
        result = []
        bot.Stock.add_stock(self.create_stock)
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stocks WHERE owner_id = ?', (self.create_telegram_id,))
        result = cursor.fetchall()
        conn.close()
        self.assertNotEqual(result, [])

    def test_get_user_stocks(self):
        result = bot.Stock.get_user_stocks(self.check_telegram_id)
        self.assertIsNotNone(result)


# class Test for Currency class
class CurrencyTestClass(unittest.TestCase):
    create_telegram_id: int = 444444
    dollar_transaction: float = 450.98

    def setUp(self) -> None:
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS currency (
                          owner_id INTEGER,
                          dollar_purchase REAL,
                          FOREIGN KEY (owner_id) REFERENCES users(telegram_id) ON DELETE CASCADE)  
                      ''')
        cursor.execute('INSERT INTO currency VALUES (?, ?)', (self.create_telegram_id, self.dollar_transaction))
        conn.commit()
        conn.close()

    def tearDown(self):
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM currency WHERE owner_id = ?',
                       (self.create_telegram_id,))
        cursor.execute('DELETE FROM currency WHERE dollar_purchase = ?',
                       (self.dollar_transaction,))
        conn.commit()
        conn.close()

    def test_add_dollar_purchase(self):
        actual = bot.Currency(self.create_telegram_id, self.dollar_transaction)
        result: int = actual.add_dollar_purchase()
        self.assertIsInstance(result, int)


class TestFunctions(unittest.TestCase):

    def set_up(self) -> None:
        pass

    def test_check_stock_existence(self):
        ticker_name = 'SBER'
        expected = True
        actual = check_stock_existence(ticker_name)
        self.assertEqual(expected, actual)
        # --------------------------------
        ticker_name = 'GTTUGI'
        expected = False
        actual = check_stock_existence(ticker_name)
        self.assertEqual(expected, actual)

    def test_get_stock_price(self):
        result: Tuple[float, str] = get_stock_price('SBER')
        expected = True
        actual = isinstance(result[0], float) and isinstance(result[1], str)
        self.assertEqual(expected, actual)

        result: Tuple[float, str] = get_stock_price('GHGYFTVK')
        expected = True
        actual = result[0] is None and result[1] is None
        self.assertEqual(expected, actual)

    def test_get_current_usd_rub(self):
        result: float = get_current_usd_rub()
        self.assertIsInstance(result, float)

    def test_convert_rub_to_dol(self):
        amount_in_rubles = 15000
        result: float = convert_rub_to_dol(amount_in_rubles)
        self.assertIsInstance(result, float)


class CheckStockExistence(unittest.TestCase):
    test_stock_id = 'GAZP'
    test_url = f'https://iss.moex.com/iss/securities/{test_stock_id}.json'
    test_response = {'boards': {'data': [['GAZP']]}}

    @patch('main.requests')
    def test_check_stock_existence(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.test_response

        mock_response_fail = mock.Mock()
        mock_response_fail.status_code = 404
        mock_response_fail.json.return_value = None

        mock_requests.get.return_value = mock_response
        result_success = check_stock_existence(self.test_stock_id)
        self.assertTrue(result_success)

        mock_requests.get.return_value = mock_response_fail
        fail_success = check_stock_existence(self.test_stock_id)
        self.assertFalse(fail_success)














