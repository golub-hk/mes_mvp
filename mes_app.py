import streamlit as st
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import pool
from streamlit_extras.stylable_container import stylable_container
import uuid
import time  # Для автообновления

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('mes_app.log', maxBytes=10*1024*1024, backupCount=5)
    ]
)

# Инициализация пула соединений с БД
def init_db():
    try:
        return psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dbname="mes_db",
            user="mes_user",
            password="mes_pass",
            host="localhost",
            port="5432"
        )
    except Exception as e:
        logging.error(f"Ошибка подключения к БД: {e}")
        st.error("Ошибка подключения к базе данных")
        return None

DB_POOL = init_db()

def db_query(query, params=None, return_result=True):
    if DB_POOL is None:
        st.error("Нет подключения к базе данных")
        return None if return_result else False
    
    conn = None
    try:
        conn = DB_POOL.getconn()
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if return_result:
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows] if columns and rows else []
            conn.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка запроса: {e}\nQuery: {query}\nParams: {params}")
        st.error("Ошибка выполнения запроса")
        return None if return_result else False
    finally:
        if conn:
            DB_POOL.putconn(conn)

@st.cache_data(ttl=300)
def get_downtime_reasons():
    result = db_query('SELECT "Name" FROM downtime_reasons ORDER BY "Name"')
    return [r['Name'] for r in result] if result else []

def authenticate(login, password):
    if not login or not password:
        st.error("Введите логин и пароль")
        return False
    
    user = db_query(
        "SELECT operator_guid, full_name FROM users WHERE login = %s AND password = %s", 
        (login, password)
    )
    
    if user and len(user) > 0:
        st.session_state.update({
            'user_guid': user[0]['operator_guid'],
            'user_name': user[0]['full_name'],
            'authenticated': True,
            'current_state': 'idle',
            'operation_data': None,
            'show_pause_dialog': False,  # Новый флаг для окна причины паузы
            'show_confirmation': False
        })
        return True
    
    st.error("Неверный логин или пароль")
    return False

def update_operation_status(operation_guid, operator_guid, status):
    return db_query(
        "INSERT INTO status_changes (operation_guid, operator_guid, status, changed_at) VALUES (%s, %s, %s, %s)",
        (operation_guid, operator_guid, status, datetime.now()),
        return_result=False
    )

def start_pause(op_data, reason):
    # Создаём новую запись в downtime
    db_query(
        "INSERT INTO downtime (operation_guid, operator_guid, reason, started_at, ended_at) VALUES (%s, %s, %s, %s, NULL)",
        (op_data['operation_guid'], st.session_state.user_guid, reason, datetime.now()),
        return_result=False
    )
    # Обновляем статус операции
    update_operation_status(op_data['operation_guid'], st.session_state.user_guid, 'Приостановлена')
    op_data['status'] = 'Приостановлена'
    op_data['pause_start'] = datetime.now()
    op_data['current_reason'] = reason

def save_pause(op_data):
    # Обновляем ended_at для последней незавершённой паузы
    db_query(
        """
        UPDATE downtime SET ended_at = %s
        WHERE operation_guid = %s AND ended_at IS NULL
        """,
        (datetime.now(), op_data['operation_guid']),
        return_result=False
    )
    # Обновляем статус операции
    update_operation_status(op_data['operation_guid'], st.session_state.user_guid, 'В работе')
    op_data['status'] = 'В работе'

def load_pause_data(op_data):
    if op_data.get('status') == 'Приостановлена':
        pause_data = db_query(
            "SELECT started_at, reason FROM downtime WHERE operation_guid = %s AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (op_data['operation_guid'],)
        )
        if pause_data:
            op_data['pause_start'] = pause_data[0]['started_at']
            op_data['current_reason'] = pause_data[0]['reason']
            st.session_state.current_state = 'paused'

def operation_control_panel(tab_key):
    if not st.session_state.get('operation_data'):
        return
    
    op_data = st.session_state.operation_data
    load_pause_data(op_data)  # Загружаем данные паузы если нужно
    reasons = get_downtime_reasons()
    panel_key = f"control_panel_{tab_key}_{op_data.get('operation_guid', str(uuid.uuid4()))}"  # Добавлен tab_key для уникальности
    
    with st.container(border=True, key=panel_key):
        st.subheader(f"Текущая операция: {op_data.get('name', 'Неизвестно')}")
        st.write(f"**Статус:** {op_data.get('status', 'Не начата')}")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("Начать", 
                        disabled=op_data.get('status', '') != 'Не начата',
                        type="primary",
                        key=f"start_btn_{panel_key}"):
                try:
                    st.session_state.current_state = 'running'
                    op_data['start_time'] = datetime.now()
                    update_operation_status(op_data.get('operation_guid'), st.session_state.user_guid, 'В работе')
                    op_data['status'] = 'В работе'
                    st.rerun()
                except Exception as e:
                    logging.error(f"Ошибка при запуске операции: {e}")
                    st.error("Ошибка при запуске операции")
                    st.session_state.current_state = 'idle'
        
        with col2:
            if st.button("Остановить",
                        disabled=op_data.get('status', '') != 'В работе',
                        key=f"pause_btn_{panel_key}"):
                st.session_state.show_pause_dialog = True
                st.rerun()
        
        with col3:
            if st.button("Продолжить",
                        disabled=op_data.get('status', '') != 'Приостановлена',
                        key=f"resume_btn_{panel_key}"):
                try:
                    save_pause(op_data)
                    st.session_state.current_state = 'running'
                    st.rerun()
                except Exception as e:
                    logging.error(f"Ошибка при возобновлении операции: {e}")
                    st.error("Ошибка при возобновлении операции")
                    st.session_state.current_state = 'paused'
        
        with col4:
            if st.button("Завершить",
                        disabled=op_data.get('status', '') in ['Не начата', 'Завершена'],
                        type="secondary",
                        key=f"complete_btn_{panel_key}"):
                st.session_state.show_confirmation = True
                st.rerun()
        
        if st.session_state.current_state != 'idle' and op_data.get('start_time') is not None:
            elapsed = (datetime.now() - op_data['start_time']).total_seconds()
            active_time = elapsed - op_data.get('total_paused', 0)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Общее время", f"{elapsed/60:.1f} мин")
            col2.metric("Время работы", f"{active_time/60:.1f} мин")
            col3.metric("Время пауз", f"{op_data.get('total_paused', 0)/60:.1f} мин")
        
        if st.session_state.get('show_pause_dialog'):
            st.warning("Выберите причину остановки")
            pause_reason = st.selectbox(
                "Причина",
                reasons,
                key=f"pause_reason_dialog_{panel_key}"
            )
            if pause_reason and st.button("OK", key=f"ok_pause_{panel_key}"):
                try:
                    st.session_state.current_state = 'paused'
                    start_pause(op_data, pause_reason)
                    st.session_state.show_pause_dialog = False
                    st.rerun()
                except Exception as e:
                    logging.error(f"Ошибка при паузе операции: {e}")
                    st.error("Ошибка при постановке операции на паузу")
                    st.session_state.current_state = 'running'
                    st.session_state.show_pause_dialog = False
                    st.rerun()
            if st.button("Отмена", key=f"cancel_pause_{panel_key}"):
                st.session_state.show_pause_dialog = False
                st.rerun()
        
        if st.session_state.get('show_confirmation'):
            st.warning("Подтвердите завершение операции")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Да, завершить", 
                            type="primary",
                            key=f"confirm_complete_{panel_key}"):
                    try:
                        end_time = datetime.now()
                        if op_data.get('status') == 'Приостановлена':
                            save_pause(op_data)  # Завершаем паузу, если она активна
                        success = save_operation(
                            st.session_state.user_guid,
                            op_data.get('work_center_guid'),
                            op_data.get('operation_guid'),
                            op_data.get('start_time'),
                            end_time
                        )
                        
                        if success:
                            st.session_state.current_state = 'idle'
                            st.session_state.operation_data = None
                            st.session_state.show_confirmation = False
                            st.success("Операция успешно сохранена!")
                            st.rerun()
                    except Exception as e:
                        logging.error(f"Ошибка при завершении операции: {e}")
                        st.error("Ошибка при завершении операции")
            
            with col2:
                if st.button("Отмена",
                            key=f"cancel_complete_{panel_key}"):
                    st.session_state.show_confirmation = False
                    st.rerun()
        
        if op_data.get('pauses'):
            with st.expander("История пауз"):
                for i, pause in enumerate(op_data.get('pauses', []), 1):
                    st.write(f"{i}. {pause.get('reason', 'Не указана')} - {pause.get('duration', 0)/60:.1f} мин")

def save_operation(operator_guid, wc_guid, op_guid, start_time, end_time):
    try:
        db_query(
            """
            INSERT INTO completed_operations 
            (operator_guid, work_center_guid, operation_guid, started_at, ended_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (operator_guid, wc_guid, op_guid, start_time, end_time),
            return_result=False
        )
        
        # Обновляем статус операции
        db_query(
            "INSERT INTO status_changes (operation_guid, operator_guid, status, changed_at) VALUES (%s, %s, %s, %s)",
            (op_guid, operator_guid, 'Завершена', end_time),
            return_result=False
        )
        
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения операции: {e}")
        st.error("Ошибка при сохранении операции")
        return False

def auth_page():
    st.markdown("""
    <style>
        .auth-container {
            max-width: 400px;
            margin: 50px auto;
            padding: 2rem;
            border-radius: 15px;
            background: white;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        .auth-title {
            text-align: center;
            color: #2c3e50;
            margin-bottom: 1.5rem;
            font-size: 1.8rem;
            font-weight: 600;
        }
        .auth-logo {
            text-align: center;
            margin-bottom: 1.5rem;
            font-size: 3rem;
        }
        .stTextInput>div>div>input {
            border-radius: 8px;
            padding: 10px;
        }
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            padding: 10px;
            font-weight: 500;
        }
        .error-message {
            color: #e74c3c;
            text-align: center;
            margin-top: 1rem;
            font-weight: 500;
        }
    </style>
    """, unsafe_allow_html=True)

    with stylable_container(
        key="auth_container",
        css_styles="""
            {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                width: 100%;
                max-width: 400px;
            }
        """,
    ):
        st.markdown('<div class="auth-logo">🏭</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-title">MES система</div>', unsafe_allow_html=True)
        
        with st.form("auth_form"):
            login = st.text_input("Логин", placeholder="Введите ваш логин", key="login_input")
            password = st.text_input("Пароль", type="password", placeholder="Введите пароль", key="pass_input")
            
            submitted = st.form_submit_button("Войти", type="primary")
            
            if submitted:
                with st.spinner("Проверка данных..."):
                    if authenticate(login, password):
                        st.rerun()
                    else:
                        st.markdown('<div class="error-message">Неверный логин или пароль</div>', unsafe_allow_html=True)

def main_interface():
    st.markdown("""
    <style>
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }
        .user-info {
            display: flex;
            align-items: center;
            gap: 10px;
            color: #2c3e50;
            font-weight: 500;
        }
        .logout-btn {
            border: 1px solid #e74c3c !important;
            color: #e74c3c !important;
            width: 30px !important; # Уменьшаем ширину кнопки
            height: 30px !important; # Уменьшаем высоту кнопки
            padding: 0 !important; # Убираем отступы внутри
            font-size: 20px !important; # Уменьшаем шрифт
            min-width: auto !important; # Разрешаем сжиматься
        }
.        logout-btn:hover {
            background-color: #ffeeee !important;
        }
        .tab-content {
            padding-top: 1rem;
        }
        .no-data {
            text-align: center;
            color: #7f8c8d;
            margin-top: 2rem;
        }
        .operation-card {
            border: 1px solid #eee;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
            background: white;
        }
        .status-running {
            color: #27ae60;
            font-weight: bold;
        }
        .status-paused {
            color: #f39c12;
            font-weight: bold;
        }
        .status-completed {
            color: #3498db;
            font-weight: bold;
        }
        .status-not-started {
            color: #95a5a6;
            font-weight: bold;
        }
        .work-center-header {
            background-color: #f8f9fa;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            font-weight: bold;
        }
        .batch-header {
            background-color: #e9ecef;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            margin-top: 0.5rem;
            margin-bottom: 0.25rem;
            font-weight: 500;
        }
        div.stButton > button {
            width: 100% !important;  # Чтобы кнопки были одинаковой ширины
        }
    </style>
    """, unsafe_allow_html=True)
    
    with st.container(key="main_header"):
        col_user, col_logout = st.columns(2)
        col_user.markdown(f"<div class='user-info'>👤 {st.session_state.get('user_name', '')}</div>", unsafe_allow_html=True)
        if col_logout.button("Выйти", key="logout_btn", type="secondary"):
            st.session_state.clear()
            st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["Выбор операций", "Мои операции", "Моя статистика"])
    
    with tab1:
        st.header("Ручной подбор операции")
        
        today = datetime.today().date()
        
        work_centers = db_query("""
            SELECT guid, name 
            FROM work_centers
            WHERE guid IS NOT NULL
            ORDER BY name
        """) or []
        
        wc_names = [wc.get('name') for wc in work_centers] if work_centers else []
        wc_name = st.selectbox(
            "Рабочий центр",
            wc_names,
            index=None,
            placeholder="Выберите рабочий центр",
            key="wc_select"
        )
        
        selected_product_guid = None
        if wc_name:
            wc_guid = next((wc.get('guid') for wc in work_centers if wc.get('name') == wc_name), None)
            
            products = db_query("""
                SELECT DISTINCT 
                    po."MainProductGUID" as guid, 
                    po."MainProduct" as name 
                FROM production_operations po
                WHERE po."WorkCenterGUID" = %s
                AND po."ProductionShiftDate"::date = %s
                AND NOT EXISTS (
                    SELECT 1 
                    FROM completed_operations co
                    WHERE co.operation_guid = po."ProductionOperationGUID"
                )
                ORDER BY po."MainProduct"
            """, (wc_guid, today)) if wc_guid else []
            
            product_names = [p.get('name') for p in products] if products else []
            product_name = st.selectbox(
                "Продукт",
                product_names,
                index=None,
                placeholder="Выберите продукт",
                key=f"product_select_{wc_guid}",
                disabled=not products
            )
            
            selected_product_guid = next((p.get('guid') for p in products if p.get('name') == product_name), None)
        
        selected_batch_number = None
        if selected_product_guid:
            batches = db_query("""
                SELECT DISTINCT 
                    po."MainProductBatchNumber" as number, 
                    po."MainProductBatch" as name 
                FROM production_operations po
                WHERE po."WorkCenterGUID" = %s
                AND po."MainProductGUID" = %s
                AND po."ProductionShiftDate"::date = %s
                AND NOT EXISTS (
                    SELECT 1 
                    FROM completed_operations co
                    WHERE co.operation_guid = po."ProductionOperationGUID"
                )
                ORDER BY po."MainProductBatch"
            """, (wc_guid, selected_product_guid, today)) if wc_guid else []
            
            batch_names = [b.get('name') for b in batches] if batches else []
            batch_name = st.selectbox(
                "Серия",
                batch_names,
                index=None,
                placeholder="Выберите серию",
                key=f"batch_select_{selected_product_guid}",
                disabled=not batches
            )
            
            selected_batch_number = next((b.get('number') for b in batches if b.get('name') == batch_name), None)
        
        if selected_batch_number:
            operations = db_query("""
                SELECT 
                    po."ProductionOperationGUID" as guid, 
                    po."ProductionOperationName" as name,
                    CASE 
                        WHEN sc.status IS NOT NULL THEN sc.status
                        ELSE 'Не начата'
                    END as status
                FROM production_operations po
                LEFT JOIN completed_operations co ON co.operation_guid = po."ProductionOperationGUID"
                LEFT JOIN (
                    SELECT operation_guid, status 
                    FROM status_changes 
                    WHERE id IN (
                        SELECT MAX(id) 
                        FROM status_changes 
                        GROUP BY operation_guid
                    )
                ) sc ON sc.operation_guid = po."ProductionOperationGUID"
                WHERE po."MainProductGUID" = %s 
                AND po."WorkCenterGUID" = %s 
                AND po."MainProductBatchNumber" = %s
                AND po."ProductionShiftDate"::date = %s
                AND co.operation_guid IS NULL
                ORDER BY po."ProductionOperationName"
            """, (selected_product_guid, wc_guid, selected_batch_number, today)) if selected_product_guid and wc_guid else []
            
            op_names = [op.get('name') for op in operations] if operations else []
            op_name = st.selectbox(
                "Операция",
                op_names,
                index=None,
                placeholder="Выберите операцию",
                key=f"operation_select_{selected_product_guid}_{selected_batch_number}",
                disabled=not operations
            )
            
            if op_name:
                op_guid = next((op.get('guid') for op in operations if op.get('name') == op_name), None)
                if op_guid:
                    current_op = next(op for op in operations if op.get('guid') == op_guid)
                    st.session_state.operation_data = {
                        'operation_guid': op_guid,
                        'name': op_name,
                        'work_center_guid': wc_guid,
                        'pauses': [],
                        'total_paused': 0,
                        'status': current_op.get('status', 'Не начата')
                    }
                    operation_control_panel('tab1')
                else:
                    st.warning("Не удалось найти GUID операции")
            else:
                if st.session_state.get('operation_data'):
                    st.session_state.operation_data = None  # Сбрасываем, если операция не выбрана
        
    
    with tab2:
        st.header("Назначенные операции")
        
        today = datetime.today().date()
        
        operations = db_query("""
            SELECT 
                po."ProductionOperationGUID" as operation_guid, 
                po."ProductionOperationName" as operation_name,
                po."WorkCenterGUID" as work_center_guid, 
                po."WorkCenter" as work_center_name,
                po."MainProduct" as product_name,
                po."MainProductBatchNumber" as product_batch,
                po."ProductionOperationDate" as planned_date,
                CASE 
                    WHEN sc.status IS NOT NULL THEN sc.status
                    ELSE 'Не начата'
                END as operation_status
            FROM production_operations po
            LEFT JOIN completed_operations co ON co.operation_guid = po."ProductionOperationGUID" AND co.operator_guid = %s
            LEFT JOIN (
                SELECT operation_guid, status 
                FROM status_changes 
                WHERE id IN (
                    SELECT MAX(id) 
                    FROM status_changes 
                    GROUP BY operation_guid
                )
            ) sc ON sc.operation_guid = po."ProductionOperationGUID"
            WHERE po."ExecutorGUID" = %s 
            AND po."ProductionShiftDate"::date = %s
            AND (sc.status IS NULL OR sc.status != 'Завершена')
            ORDER BY po."WorkCenter", po."MainProductBatchNumber", po."ProductionOperationDate"
        """, (st.session_state.get('user_guid'), st.session_state.get('user_guid'), today))
        
        if operations and len(operations) > 0:
            work_centers = {}
            for op in operations:
                wc = op.get('work_center_name') or 'Unknown'
                pb = op.get('product_batch') or 'Unknown'
                if wc not in work_centers:
                    work_centers[wc] = {}
                if pb not in work_centers[wc]:
                    work_centers[wc][pb] = []
                work_centers[wc][pb].append(op)
            
            for wc_name, batches in work_centers.items():
                with st.container(key=f"wc_container_{wc_name}"):
                    st.markdown(f'<div class="work-center-header">Рабочий центр: {wc_name}</div>', unsafe_allow_html=True)
                    
                    for batch, ops in batches.items():
                        st.markdown(f'<div class="batch-header">Серия: {batch}</div>', unsafe_allow_html=True)
                        
                        for idx, op in enumerate(ops):
                            status_class = {
                                'В работе': 'status-running',
                                'Приостановлена': 'status-paused',
                                'Завершена': 'status-completed',
                                'Не начата': 'status-not-started'
                            }.get(op.get('operation_status', ''), '')
                            
                            op_key = f"op_{op.get('operation_guid')}_{op.get('work_center_guid')}_{op.get('product_batch')}_{idx}"
                            
                            with st.container(border=True, key=op_key):
                                cols = st.columns([3, 1])
                                cols[0].markdown(f"**{op.get('operation_name', 'Неизвестно')}**")
                                cols[1].markdown(f"<div class='{status_class}'>**Статус:** {op.get('operation_status', 'Неизвестно')}</div>", 
                                                unsafe_allow_html=True)
                                
                                st.write(f"**Продукт:** {op.get('product_name', 'Неизвестно')}")
                                st.write(f"**Планируемая дата:** {op.get('planned_date').strftime('%d.%m.%Y %H:%M') if op.get('planned_date') else 'Не указана'}")
                                
                                is_disabled = bool(
                                    op.get('operation_status', '') not in ['Не начата', 'Приостановлена'] 
                                    or st.session_state.get('operation_data')
                                )
                                
                                if st.button("Начать выполнение", 
                                           key=f"start_op_{op_key}",
                                           disabled=is_disabled):
                                    if st.session_state.get('operation_data'):
                                        st.warning("Завершите текущую операцию перед началом новой.")
                                    else:
                                        st.session_state.operation_data = {
                                            'operation_guid': op.get('operation_guid'),
                                            'name': op.get('operation_name'),
                                            'work_center_guid': op.get('work_center_guid'),
                                            'pauses': [],
                                            'total_paused': 0,
                                            'status': op.get('operation_status', 'Не начата'),
                                        }
                                        st.rerun()
        else:
            st.markdown('<div class="no-data">Нет назначенных операций</div>', unsafe_allow_html=True)
        
        operation_control_panel('tab2')
    
    with tab3:
        st.header("История операций")
        history = db_query("""
            SELECT 
                c.id,
                p."ProductionOperationName" as operation_name, 
                p."WorkCenter" as work_center_name, 
                c.ended_at, 
                c.operation_guid,
                sc.status
            FROM completed_operations c
            JOIN production_operations p ON c.operation_guid = p."ProductionOperationGUID"
            LEFT JOIN (
                SELECT operation_guid, status 
                FROM status_changes 
                WHERE id IN (
                    SELECT MAX(id) 
                    FROM status_changes 
                    GROUP BY operation_guid
                )
            ) sc ON sc.operation_guid = c.operation_guid
            WHERE c.operator_guid = %s
            ORDER BY c.ended_at DESC
            LIMIT 50
        """, (st.session_state.get('user_guid'),)) or []
        
        if history and len(history) > 0:
            for idx, op in enumerate(history):
                status_class = {
                    'В работе': 'status-running',
                    'Приостановлена': 'status-paused',
                    'Завершена': 'status-completed',
                    'Не начата': 'status-not-started'
                }.get(op.get('status', ''), '')
                
                history_key = f"history_item_{op.get('id')}_{idx}"
                
                with st.container(border=True, key=history_key):
                    cols = st.columns([3, 1])
                    cols[0].markdown(f"**{op.get('operation_name', 'Неизвестно')}** ({op.get('work_center_name', 'Неизвестно')})")
                    cols[1].markdown(f"<div class='{status_class}'>**Статус:** {op.get('status', 'Неизвестно')}</div>", 
                                    unsafe_allow_html=True)
                    
                    cols = st.columns(1)
                    cols[0].metric("Завершение", op.get('ended_at').strftime('%H:%M') if op.get('ended_at') else '-')
                    
                    pauses = db_query("""
                        SELECT reason, (ended_at - started_at) AS duration FROM downtime 
                        WHERE operation_guid = %s AND ended_at IS NOT NULL
                    """, (op.get('operation_guid'),)) or []
                    
                    if pauses:
                        with st.expander(f"Показать паузы ({len(pauses)})"):
                            for pause in pauses:
                                duration = pause.get('duration') or timedelta(seconds=0)
                                st.write(f"- {pause.get('reason', 'Не указана')}: {duration.total_seconds()/60:.1f} мин")
        else:
            st.markdown('<div class="no-data">Нет данных о выполненных операциях</div>', unsafe_allow_html=True)

def main():
    if not hasattr(st.session_state, 'authenticated'):
        st.session_state.authenticated = False
    if 'current_state' not in st.session_state:
        st.session_state.current_state = 'idle'
    if 'operation_data' not in st.session_state:
        st.session_state.operation_data = None
    if 'show_confirmation' not in st.session_state:
        st.session_state.show_confirmation = False
    if 'show_pause_dialog' not in st.session_state:
        st.session_state.show_pause_dialog = False  # Новый флаг
    
    if not st.session_state.authenticated:
        auth_page()
    else:
        main_interface()

if __name__ == "__main__":
    main()
