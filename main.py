import asyncio
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters.command import Command
from aiogram.filters.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram import F
# from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
# from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import sqlite3
import os
from datetime import datetime
import requests
from typing import List, Tuple, Optional
from dotenv import load_dotenv


load_dotenv()
#  Создание экземпляра бота
api_token = os.getenv('API_TOKEN')
bot = Bot(token=api_token)
storage = MemoryStorage()
#  Создание экземпляра диспетчера
dp = Dispatcher(bot=bot, storage=storage)
router = Router()
dp.include_router(router)


#Создание класса с пользователем
class User:
    def __init__(self, telegram_id):
        self.telegram_id = telegram_id

    def check_user_data(self):
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name='users'")
        result = cursor.fetchone()
        if result is None:
            conn.close()
            return None
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (self.telegram_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def create_user_record(self):
        inserted_id = None
        if not self.check_user_data():
            conn = sqlite3.connect('./app_data/database.db')
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY)''')
            cursor.execute('INSERT INTO users (telegram_id) VALUES (?)', (self.telegram_id,))
            inserted_id = cursor.lastrowid
            conn.commit()
            conn.close()
        return inserted_id


class Currency:
    def __init__(self, owner_id, dollar_purchase):
        self.owner_id: int = owner_id
        self.dollar_purchase: float = dollar_purchase

    def add_dollar_purchase(self):
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS currency (
                          owner_id INTEGER,
                          dollar_purchase REAL,
                          FOREIGN KEY (owner_id) REFERENCES users(telegram_id) ON DELETE CASCADE)  
                      ''')
        values = (self.owner_id, self.dollar_purchase)
        cursor.execute('INSERT INTO currency (owner_id, dollar_purchase) VALUES (?, ?)', values)
        inserted_id: int = cursor.lastrowid
        conn.commit()
        conn.close()
        return inserted_id


#Создаем класс для работы с акциями
class Stock:
    def __init__(self, owner_id, stock_id, quantity, unit_price, purchase_date):
        self.owner_id = owner_id
        self.stock_id = stock_id
        self.quantity = quantity
        self.unit_price = unit_price
        self.purchase_date = datetime.now()

    def __eq__(self, other):
        if isinstance(other, Stock):
            return (
                    self.owner_id == other.owner_id
                    and self.stock_id == other.stock_id
                    and self.quantity == other.quantity
                    and self.unit_price == other.unit_price
                    and self.purchase_date == other.purchase_date
            )
        return False

    # Function to add stock
    def add_stock(self):
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS stocks
                          (owner_id INTEGER, 
                          stock_id TEXT, 
                          quantity INTEGER, 
                          unit_price REAL, 
                          purchase_date TEXT,
                          FOREIGN KEY (owner_id) REFERENCES users(telegram_id) ON DELETE CASCADE)''')
        purchase_date_str = self.purchase_date.isoformat()
        values = (self.owner_id, self.stock_id, self.quantity, self.unit_price, self.purchase_date)
        cursor.execute('INSERT INTO stocks VALUES (?, ?, ?, ?, ?)', values)
        inserted_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return inserted_id

    # Function to get user's stocks
    @classmethod
    def get_user_stocks(cls, owner_id: int) -> List:
        stocks = []
        conn = sqlite3.connect('./app_data/database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'")
        result = cursor.fetchone()
        if result is None:
            conn.close()
            return stocks
        cursor.execute('SELECT * FROM stocks where owner_id = ?', (owner_id,))
        result: List[Tuple] = cursor.fetchall()
        conn.close()

        for row in result:
            owner_id, stock_id, quantity, unit_price, purchase_date = row
            stock = cls(owner_id, stock_id, quantity, unit_price, purchase_date)
            stocks.append(stock)

        return stocks


# ———————— РАБОТА С СОСТОЯНИЯМИ ————————
#Подготовка хранилища состояний для многошагового сценария:
# Создаем классы для сохранения состояний
class CheckStockStates(StatesGroup):
    StockID = State()
    Rub_Amount = State()


class AddStockStates(StatesGroup):
    StockID = State()
    StockPrice = State()
    StockQuantity = State()


#Функция проверки существования акции на бирже
def check_stock_existence(stock_id: str) -> bool:
    # Обращаемся к МосБирже
    url = f'https://iss.moex.com/iss/securities/{stock_id}.json'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        exist = data.get('boards',{}).get('data',[])
        if exist != []:
            return bool(exist)
        else:
            return False
    else:
        return False


#Функция для получения цены акции
def get_stock_price(stock_id: str) -> Tuple[float, str]:
    url = f'https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{stock_id}.json?iss.only=securities&securities.columns=PREVPRICE,CURRENCYID'
    response = requests.get(url)
    stock_price: Optional[float] = None
    stock_currency: Optional[str] = None
    if response.status_code == 200:
        data_json = response.json()
        data: List = data_json.get('securities').get('data')
        if len(data) != 0:
            stock_price = data[0][0]
            stock_currency = data[0][1]
            if stock_currency == 'SUR':
                stock_currency = 'RUB'

    return stock_price, stock_currency


#Получение текущего курса доллара
def get_current_usd_rub() -> float:
    # URL to fetch the current value of USD/RUB
    url = 'https://www.cbr-xml-daily.ru/daily_json.js'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        # Extract the current exchange rate
        current_value = data.get('Valute', {}).get('USD', {})
        if current_value:
            return current_value["Value"]
        else:
            print("No data found for USD/RUB.")
            return None
    else:
        print(f"Error: {response.status_code}")
        return None


def convert_rub_to_dol(amount_rub: int) -> float:
    current_dollar_value = get_current_usd_rub()
    if current_dollar_value is None or current_dollar_value == 0:
        print("Не удалось определить текущий курс.")
    return amount_rub / current_dollar_value


keyboard_builder = ReplyKeyboardBuilder()

# Create buttons for the various actions
keyboard_builder.add(KeyboardButton(text='start'))
keyboard_builder.add(KeyboardButton(text='stock price'))
keyboard_builder.add(KeyboardButton(text='USD_RUB'))
keyboard_builder.add(KeyboardButton(text='AddStock'))
keyboard_builder.add(KeyboardButton(text="CheckPortfolio"))
keyboard = keyboard_builder.as_markup(resize_keyboard=True)


# ----------------------------------------------------------------------------
@router.message(F.text == 'start')
async def reg_user(message: types.Message):
    new_user = User(message.from_user.id)
    new_user.create_user_record()
    await message.reply('Добро пожаловать!', reply_markup=keyboard)

# -----------------------------------------------------------------------------


@router.message(F.text == 'stock price')
async def check_stock_command(message: types.Message, state: FSMContext):
    await message.reply("Назовите тикер акции и я сообщу ее курс")
    await state.set_state(CheckStockStates.StockID)


@dp.message(CheckStockStates.StockID)
async def check_stock_id(message: types.Message, state: FSMContext):
    stock_id = message.text.upper()
    stock_existence = check_stock_existence(stock_id)
    await message.reply(f"Вы запросили курс для тикера: {stock_id}")
    if stock_existence == True:
        stock_price, stock_currency = get_stock_price(stock_id)
        await message.reply(f'Стоимость {stock_price} {stock_currency}')
    else:
        await message.reply('Ценная бумага не существует')
    await state.clear()
# ------------------------------------------------------------------


@router.message(F.text =='AddStock')
async def check_stock_start(message: types.Message, state: FSMContext):
    await message.reply('Введите идентификатор приобретенного инструмента')
    # await bot.send_message(message.chat.id, '')
    await state.set_state(AddStockStates.StockID)


@router.message(AddStockStates.StockID)
async def add_stock_id(message: types.Message, state: FSMContext):
    # Check if the user is trying to stop the process
    if message.text.lower() != "/stop":
        stock_exists = check_stock_existence(message.text)

        if stock_exists:
            await message.answer('Введите стоимость единицы ценной бумаги')

            # Store the stock ID in FSMContext using `update_data`
            await state.update_data(StockID=message.text)

            # Set the next state (StockPrice)
            await state.set_state(AddStockStates.StockPrice)
        else:
            await message.reply('Указанный идентификатор ценной бумаги не найден на Московской бирже')
            await message.answer('Введите корректный идентификатор приобретенного инструмента или введите /stop для отмены')
    else:
        # If the user enters "/stop", clear the FSM state and stop the process
        await state.clear()
        await message.reply('Добавление информации о приобретенной ценной бумаге отменено')


@router.message(AddStockStates.StockPrice)
async def add_stock_price(message: types.Message, state: FSMContext):
    # Check if the user is trying to stop the process
    if message.text.lower() != '/stop':
        try:
            # Convert the input to a valid float, replacing commas with dots
            stock_price = float(message.text.replace(',', '.'))

            # Prompt the user for the quantity of stocks purchased
            await message.answer('Введите количество приобретенных единиц инструмента')

            # Store the stock price in FSMContext
            await state.update_data(StockPrice=str(stock_price))

            # Move to the next state (StockQuantity)
            await state.set_state(AddStockStates.StockQuantity)

        except ValueError:
            # If the input is invalid (not a number), notify the user
            await message.reply('Вы некорректно указали стоимость одной ценной бумаги.')
            await message.answer('Введите стоимость приобретения в числовом формате или введите /stop для отмены.')

    else:
        # If the user enters "/stop", clear the FSM state and stop the process
        await state.clear()
        await message.reply('Добавление информации о приобретенной ценной бумаге отменено')


@router.message(AddStockStates.StockQuantity)
async def add_stock_quantity(message: types.Message, state: FSMContext):
    if message.text.lower() != "/stop":
        try:
            # Attempt to convert the input to an integer
            stock_quantity = int(message.text)

            # Store the necessary data in the FSMContext
            data = await state.get_data()  # Fetch current data from FSMContext
            data['StockQuantity'] = stock_quantity
            data['StockOwnerID'] = message.from_user.id
            data['StockPurchaseDate'] = datetime.now()

            # Create a Stock record and save it
            stock_record = Stock(data['StockOwnerID'], data['StockID'], data['StockQuantity'], data['StockPrice'],
                                 data['StockPurchaseDate'])
            stock_record.add_stock()

            # Clear the state and notify the user
            await state.clear()
            await message.answer('Информация о приобретенной ценной бумаге успешно сохранена!')

        except ValueError:
            # Handle the case where the input was not a valid integer
            await message.reply('Вы некорректно указали количество приобретенных единиц ценной бумаги.')
            await message.answer('Введите количество в виде целого числа или введите /stop для отмены.')
    else:
        # If the user enters "/stop", clear the FSM state and stop the process
        await state.clear()
        await message.reply('Добавление информации о приобретенной ценной бумаге отменено.')
# ------------------------------------------------------------------------------------------------


@router.message(F.text == 'USD_RUB')
async def check_stock_command(message: types.Message, state: FSMContext):
    await message.reply("Назовите сумму в рублях, которую хотите перевести в доллары")
    await state.set_state(CheckStockStates.Rub_Amount)


@dp.message(CheckStockStates.Rub_Amount)
async def check_rub_usd(message: types.Message, state: FSMContext):
    rub_amount = float(message.text)
    current_dollar_value = get_current_usd_rub()
    usd_amount = rub_amount / current_dollar_value
    await message.reply(f"На {rub_amount} RUB вы сможете купить {usd_amount:.2f} USD.")
    await state.update_data(usd_amount=usd_amount)
    yes_button = InlineKeyboardButton(text="Да", callback_data='add_transaction_yes')
    no_button = InlineKeyboardButton(text="Нет", callback_data='add_transaction_no')

    # Create inline keyboard layout
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[yes_button, no_button]])

    # Ask user if they want to add the transaction
    await message.reply("Добавить данную покупку в БД?", reply_markup=keyboard)

    # await state.clear()


@dp.callback_query(lambda c: c.data in ['add_transaction_yes', 'add_transaction_no'])
async def process_transaction_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    user_data = await state.get_data()
    # print(f"User Data: {user_data}")
    dollar_amount = user_data.get('usd_amount')
    if dollar_amount is None:
        await bot.answer_callback_query(callback_query.id, text="Ошибка: сумма покупки не найдена.")
        return
    formatted_dollar_amount = "{:.2f}".format(dollar_amount)
    if callback_query.data == 'add_transaction_yes':
        new_currency_record = Currency(user_id, formatted_dollar_amount)
        new_currency_record.add_dollar_purchase()
        await bot.answer_callback_query(callback_query.id, text="Транзакция добавлена в БД.")
        await state.clear()
        # Implement your transaction adding logic here
    else:
        await bot.answer_callback_query(callback_query.id, text="Транзакция отменена.")
        await state.clear()
    await callback_query.message.delete_reply_markup()  # Optional: Remove the inline keyboard
# ---------------------------------------------------------------------------------


@router.message(F.text == 'CheckPortfolio')
async def check_portfolio(message: types.Message):
    user_stocks = Stock.get_user_stocks(message.from_user.id)
    portfolio_price = 0
    portfolio_stocks_count = 0
    portfolio_details: List = []

    for stock in user_stocks:
        # Получение текущий цены по каждой акции в портфеле пользователя
        current_price, currency = get_stock_price(stock.stock_id)
        if current_price:
            # Текущая цена акции
            stock_value: float = int(stock.quantity) * float(current_price)
            portfolio_price += stock_value
            portfolio_stocks_count += 1

            # Подсчет изменения цены
            price_change = float(current_price) - float(stock.unit_price)  # Change in price
            price_change_percent = (price_change / float(stock.unit_price)) * 100  # Percent change

            # Collect detailed info for the reply
            portfolio_details.append(
                f"{stock.stock_id}: {stock.quantity} units × {current_price:.2f} {currency} = {stock_value:.2f} {currency}\n"
                f"  • Куплено по {float(stock.unit_price):.2f} {currency}, разница: {price_change:.2f} {currency} "
                f"({price_change_percent:.2f}%)"
            )
        else:
            portfolio_details.append(f"{stock.stock_id}: {stock.quantity} units, current price unavailable")

    if portfolio_stocks_count == 0:
        response_message = "Ваш портфель пуст."
    else:
        response_message = f'Вы приобрели {portfolio_stocks_count} инструментов, на общую сумму {portfolio_price:.2f} RUB\n\n'
        response_message += "\n".join(portfolio_details)

    await message.reply(response_message)


async def main():
# далее используется await вместо executor
    await dp.start_polling(bot)


#  Запуск бота
if __name__ == '__main__':
     asyncio.run(main())

