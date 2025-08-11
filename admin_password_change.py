
import streamlit as st
import psycopg2
from psycopg2 import sql
import hashlib

# Конфигурация БД
DB_CONFIG = {
    "host": "db",
    "port": 5432,
    "dbname": "mes_db",
    "user": "mes_user",
    "password": "mes_pass"
}

# Функция для получения подключения к БД
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# Функция для обновления пароля
def update_password(operator_login, new_password):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            sql.SQL("UPDATE operators SET password_hash = crypt(%s, gen_salt('bf')) WHERE login = %s"),
            [new_password, operator_login]
        )
        conn.commit()
        return cursor.rowcount > 0

# Вкладка для администратора
st.title("Управление операторами: изменение паролей")

# Проверка, что это админ
admin_password = st.text_input("Введите пароль администратора", type='password')

if admin_password == "123456":  # Заменить на реальный пароль администратора
    operator_login = st.text_input("Логин оператора для изменения пароля")
    new_password = st.text_input("Новый пароль", type='password')
    confirm_password = st.text_input("Подтвердите новый пароль", type='password')

    if st.button("Сохранить новый пароль"):
        if new_password == confirm_password:
            if update_password(operator_login, new_password):
                st.success(f"Пароль для оператора {operator_login} успешно обновлён!")
            else:
                st.error(f"Не удалось обновить пароль для оператора {operator_login}. Проверьте логин.")
        else:
            st.error("Пароли не совпадают, попробуйте снова.")
else:
    st.error("Неверный пароль администратора!")
