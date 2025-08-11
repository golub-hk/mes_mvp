import streamlit as st
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import psycopg2
from psycopg2 import pool
from streamlit_extras.stylable_container import stylable_container
import uuid

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
            'show_confirmation': False
        })
        return True
    
    st.error("Неверный логин или пароль")
    return False

def update_operation_status(operation_id, status):
    return db_query(
        "INSERT INTO status_changes (operation_id, status, changed_at) VALUES (%s, %s, %s)",
        (operation_id, status, datetime.now()),
        return_result=False
    )

def create_operation_record(operator_guid, work_center_guid, operation_guid, status):
    result = db_query(
        """
        INSERT INTO completed_operations 
        (operator_guid, work_center_guid, operation_guid, status, started_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (operator_guid, work_center_guid, operation_guid, status, datetime.now()),
        return_result=True
    )
    return result[0]['id'] if result else None

def operation_control_panel():
    if not st.session_state.get('operation_data'):
        return
    
    op_data = st.session_state.operation_data
    reasons = get_downtime_reasons()
    panel_key = f"control_panel_{op_data.get('operation_guid', str(uuid.uuid4()))}"
    
    with st.container(border=True, key=panel_key):
        st.subheader(f"Текущая операция: {op_data.get('name', 'Неизвестно')}")
        st.write(f"**Статус:** {op_data.get('status', 'Не начата')}")
        
        if st.session_state.current_state != 'idle' and 'start_time' in op_data:
            elapsed = (datetime.now() - op_data['start_time']).total_seconds()
            active_time = elapsed - op_data.get('total_paused', 0)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Общее время", f"{elapsed/60:.1f} мин")
            col2.metric("Рабочее время", f"{active_time/60:.1f} мин")
            col3.metric("Время пауз", f"{op_data.get('total_paused', 0)/60:.1f} мин")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("Начать", 
                        disabled=st.session_state.current_state != 'idle',
                        type="primary",
                        key=f"start_btn_{panel_key}"):
                try:
                    st.session_state.current_state = 'running'
                    op_data['start_time'] = datetime.now()
                    op_data['status'] = 'В работе'
                    
                    if 'operation_id' not in op_data:
                        op_id = create_operation_record(
                            st.session_state.user_guid,
                            op_data.get('work_center_guid'),
                            op_data.get('operation_guid'),
                            'В работе'
                        )
                        if op_id:
                            op_data['operation_id'] = op_id
                            st.session_state.operation_data = op_data
                    else:
                        update_operation_status(op_data.get('operation_id'), 'В работе')
                    st.rerun()
                except Exception as e:
                    logging.error(f"Ошибка при запуске операции: {e}")
                    st.error("Ошибка при запуске операции")
                    st.session_state.current_state = 'idle'
        
        with col2:
            pause_reason = st.selectbox(
                "Причина паузы",
                reasons,
                disabled=st.session_state.current_state != 'running',
                key=f"pause_reason_{panel_key}"
            )
            if st.button("Пауза",
                        disabled=not pause_reason or st.session_state.current_state != 'running',
                        key=f"pause_btn_{panel_key}"):
                try:
                    st.session_state.current_state = 'paused'
                    op_data['pause_start'] = datetime.now()
                    op_data['current_reason'] = pause_reason
                    op_data['status'] = 'Приостановлена'
                    if 'operation_id' in op_data:
                        update_operation_status(op_data.get('operation_id'), 'Приостановлена')
                    st.rerun()
                except Exception as e:
                    logging.error(f"Ошибка при паузе операции: {e}")
                    st.error("Ошибка при постановке операции на паузу")
                    st.session_state.current_state = 'running'
        
        with col3:
            if st.button("Продолжить",
                        disabled=st.session_state.current_state != 'paused',
                        key=f"resume_btn_{panel_key}"):
                try:
                    if 'pause_start' in op_data:
                        pause_duration = (datetime.now() - op_data['pause_start']).total_seconds()
                        if 'pauses' not in op_data:
                            op_data['pauses'] = []
                        op_data['pauses'].append({
                            'duration': pause_duration,
                            'reason': op_data.get('current_reason', 'Не указана')
                        })
                        op_data['total_paused'] = op_data.get('total_paused', 0) + pause_duration
                    
                    st.session_state.current_state = 'running'
                    op_data['status'] = 'В работе'
                    if 'operation_id' in op_data:
                        update_operation_status(op_data.get('operation_id'), 'В работе')
                    st.rerun()
                except Exception as e:
                    logging.error(f"Ошибка при возобновлении операции: {e}")
                    st.error("Ошибка при возобновлении операции")
                    st.session_state.current_state = 'paused'
        
        with col4:
            if st.button("Завершить",
                        disabled=st.session_state.current_state == 'idle',
                        type="secondary",
                        key=f"complete_btn_{panel_key}"):
                st.session_state.show_confirmation = True
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
                        
                        if st.session_state.current_state == 'paused' and 'pause_start' in op_data:
                            last_pause = (end_time - op_data['pause_start']).total_seconds()
                            if 'pauses' not in op_data:
                                op_data['pauses'] = []
                            op_data['pauses'].append({
                                'duration': last_pause,
                                'reason': op_data.get('current_reason', 'Не указана')
                            })
                            op_data['total_paused'] = op_data.get('total_paused', 0) + last_pause
                        
                        active_time = (end_time - op_data['start_time']).total_seconds() - op_data.get('total_paused', 0)
                        
                        success = save_operation(
                            st.session_state.user_guid,
                            op_data.get('work_center_guid'),
                            op_data.get('operation_guid'),
                            op_data.get('start_time'),
                            end_time,
                            active_time,
                            op_data.get('pauses', []),
                            'Завершена'
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

def save_operation(operator_guid, wc_guid, op_guid, start_time, end_time, duration, pauses, status):
    try:
        # Приведение duration к int (секунды)
        duration = int(round(duration))
        
        # Обновляем основную запись операции
        success = db_query(
            """
            UPDATE completed_operations 
            SET ended_at = %s, duration = %s, status = %s
            WHERE operation_guid = %s AND operator_guid = %s
            RETURNING id
            """,
            (end_time, duration, status, op_guid, operator_guid),
            return_result=True
        )
        
        if not success:
            return False
            
        operation_id = success[0]['id']
        
        # Сохраняем паузы
        for pause in pauses:
            db_query(
                "INSERT INTO downtime (operation_id, reason, duration) VALUES (%s, %s, %s)",
                (operation_id, pause.get('reason', 'Не указана'), timedelta(seconds=pause.get('duration', 0))),
                return_result=False
            )
        
        # Обновляем статус операции
        db_query(
            "INSERT INTO status_changes (operation_id, status, changed_at) VALUES (%s, %s, %s)",
            (operation_id, status, end_time),
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
        }
        .logout-btn:hover {
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
    </style>
    """, unsafe_allow_html=True)
    
    with st.container(key="main_header"):
        col1, col2 = st.columns([4,1])
        col1.markdown(f"<div class='header'><h1>MES система</h1></div>", unsafe_allow_html=True)
        col2.markdown(f"<div class='user-info'>👤 {st.session_state.get('user_name', '')}</div>", unsafe_allow_html=True)
        if col2.button("Выйти", key="logout_btn", type="secondary"):
            st.session_state.clear()
            st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["Назначенные операции", "Ручной подбор", "История операций"])
    
    with tab1:
        st.header("Назначенные операции")
        
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
                END as operation_status,
                co.id as operation_id
            FROM production_operations po
            LEFT JOIN completed_operations co ON co.operation_guid = po."ProductionOperationGUID" AND co.operator_guid = %s
            LEFT JOIN (
                SELECT operation_id, status 
                FROM status_changes 
                WHERE id IN (
                    SELECT MAX(id) 
                    FROM status_changes 
                    GROUP BY operation_id
                )
            ) sc ON sc.operation_id = co.id
            WHERE po."ExecutorGUID" = %s 
            AND (sc.status IS NULL OR sc.status != 'Завершена')
            ORDER BY po."WorkCenter", po."MainProductBatchNumber", po."ProductionOperationDate"
        """, (st.session_state.get('user_guid'), st.session_state.get('user_guid')))
        
        if operations and len(operations) > 0:
            work_centers = {}
            for op in operations:
                if op.get('work_center_name') not in work_centers:
                    work_centers[op.get('work_center_name')] = {}
                if op.get('product_batch') not in work_centers[op.get('work_center_name')]:
                    work_centers[op.get('work_center_name')][op.get('product_batch')] = []
                work_centers[op.get('work_center_name')][op.get('product_batch')].append(op)
            
            for wc_name, batches in work_centers.items():
                with st.container(key=f"wc_container_{wc_name}"):
                    st.markdown(f'<div class="work-center-header">Рабочий центр: {wc_name}</div>', unsafe_allow_html=True)
                    
                    for batch, ops in batches.items():
                        st.markdown(f'<div class="batch-header">Серия: {batch}</div>', unsafe_allow_html=True)
                        
                        for op in ops:
                            status_class = {
                                'В работе': 'status-running',
                                'Приостановлена': 'status-paused',
                                'Завершена': 'status-completed',
                                'Не начата': 'status-not-started'
                            }.get(op.get('operation_status', ''), '')
                            
                            op_key = f"op_{op.get('operation_guid')}_{op.get('work_center_guid')}_{op.get('product_batch')}"
                            
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
                                            'start_time': None,
                                            'pauses': [],
                                            'total_paused': 0,
                                            'status': op.get('operation_status', 'Не начата'),
                                            'operation_id': op.get('operation_id')
                                        }
                                        st.rerun()
        else:
            st.markdown('<div class="no-data">Нет назначенных операций</div>', unsafe_allow_html=True)
        
        operation_control_panel()
    
    with tab2:
        st.header("Ручной подбор операции")
        
        work_centers = db_query("""
            SELECT DISTINCT 
                "WorkCenterGUID" as guid, 
                "WorkCenter" as name 
            FROM production_operations
            WHERE NOT EXISTS (
                SELECT 1 
                FROM completed_operations 
                WHERE operation_guid = production_operations."ProductionOperationGUID"
                AND operator_guid = %s
            )
            ORDER BY "WorkCenter"
        """, (st.session_state.get('user_guid'),)) or []
        
        wc_names = [wc.get('name') for wc in work_centers] if work_centers else []
        wc_name = st.selectbox(
            "Рабочий центр",
            wc_names,
            index=None,
            placeholder="Выберите рабочий центр",
            key="wc_select"
        )
        
        if wc_name:
            wc_guid = next((wc.get('guid') for wc in work_centers if wc.get('name') == wc_name), None)
            
            products = db_query("""
                SELECT DISTINCT 
                    "MainProductGUID" as guid, 
                    "MainProduct" as name 
                FROM production_operations
                WHERE "WorkCenterGUID" = %s
                AND NOT EXISTS (
                    SELECT 1 
                    FROM completed_operations 
                    WHERE operation_guid = production_operations."ProductionOperationGUID"
                    AND operator_guid = %s
                )
                ORDER BY "MainProduct"
            """, (wc_guid, st.session_state.get('user_guid'))) if wc_guid else []
            
            product_names = [p.get('name') for p in products] if products else []
            product_name = st.selectbox(
                "Продукт",
                product_names,
                index=None,
                placeholder="Выберите продукт",
                key=f"product_select_{wc_guid}",
                disabled=not products
            )
            
            if product_name and products:
                product_guid = next((p.get('guid') for p in products if p.get('name') == product_name), None)
                
                operations = db_query("""
                    SELECT 
                        po."ProductionOperationGUID" as guid, 
                        po."ProductionOperationName" as name,
                        CASE 
                            WHEN sc.status IS NOT NULL THEN sc.status
                            ELSE 'Не начата'
                        END as status,
                        co.id as operation_id
                    FROM production_operations po
                    LEFT JOIN completed_operations co ON co.operation_guid = po."ProductionOperationGUID" AND co.operator_guid = %s
                    LEFT JOIN (
                        SELECT operation_id, status 
                        FROM status_changes 
                        WHERE id IN (
                            SELECT MAX(id) 
                            FROM status_changes 
                            GROUP BY operation_id
                        )
                    ) sc ON sc.operation_id = co.id
                    WHERE po."MainProductGUID" = %s 
                    AND po."WorkCenterGUID" = %s 
                    AND po."ProductionOperationStatus" = 'active'
                    ORDER BY po."ProductionOperationName"
                """, (st.session_state.get('user_guid'), product_guid, wc_guid)) if product_guid and wc_guid else []
                
                op_names = [op.get('name') for op in operations] if operations else []
                op_name = st.selectbox(
                    "Операция",
                    op_names,
                    index=None,
                    placeholder="Выберите операцию",
                    key=f"operation_select_{product_guid}",
                    disabled=not operations
                )
                
                if op_name and operations and st.button("Выбрать операцию", 
                                                      key=f"select_op_{product_guid}_{wc_guid}"):
                    op_guid = next((op.get('guid') for op in operations if op.get('name') == op_name), None)
                    if op_guid:
                        current_op = next(op for op in operations if op.get('guid') == op_guid)
                        st.session_state.operation_data = {
                            'operation_guid': op_guid,
                            'name': op_name,
                            'work_center_guid': wc_guid,
                            'start_time': None,
                            'pauses': [],
                            'total_paused': 0,
                            'status': current_op.get('status', 'Не начата'),
                            'operation_id': current_op.get('operation_id')
                        }
                        st.rerun()
    
    with tab3:
        st.header("История операций")
        history = db_query("""
            SELECT 
                c.id,
                p."ProductionOperationName" as operation_name, 
                p."WorkCenter" as work_center_name, 
                c.started_at, 
                c.ended_at, 
                c.duration, 
                c.operation_guid,
                sc.status
            FROM completed_operations c
            JOIN production_operations p ON c.operation_guid = p."ProductionOperationGUID"
            LEFT JOIN (
                SELECT operation_id, status 
                FROM status_changes 
                WHERE id IN (
                    SELECT MAX(id) 
                    FROM status_changes 
                    GROUP BY operation_id
                )
            ) sc ON sc.operation_id = c.id
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
                    
                    cols = st.columns(3)
                    cols[0].metric("Начало", op.get('started_at').strftime('%H:%M') if op.get('started_at') else '-')
                    cols[1].metric("Завершение", op.get('ended_at').strftime('%H:%M') if op.get('ended_at') else '-')
                    cols[2].metric("Длительность", f"{op.get('duration', 0)/60:.1f} мин" if op.get('duration') else '-')
                    
                    pauses = db_query("""
                        SELECT reason, duration FROM downtime 
                        WHERE operation_id = %s
                    """, (op.get('id'),)) or []
                    
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
    
    if not st.session_state.authenticated:
        auth_page()
    else:
        main_interface()

if __name__ == "__main__":
    main()
