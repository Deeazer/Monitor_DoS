import sys
import socket
import time
import csv
from datetime import datetime
import paramiko
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
                             QLineEdit, QLabel, QSpinBox, QCheckBox, QTextEdit, QFileDialog, QMessageBox,
                             QToolBar, QAction, QSizePolicy, QStyle, QTabWidget, QSplitter, QTableWidget,
                             QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import QTimer, Qt, QSize, QSizeF
from PyQt5.QtGui import QIcon, QPixmap, QPainter
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from pyqtgraph import PlotWidget, mkPen

class PortMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Port Availability Monitor")
        self.setGeometry(100, 100, 1000, 800)
        
        # Data storage
        self.time_data = []
        self.port_status = {}
        self.monitoring = False
        self.start_time = None
        self.ssh_clients = {}
        
        self.init_ui()
        
    def init_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Create toolbar
        self.toolbar = QToolBar("Панель инструментов")
        self.addToolBar(self.toolbar)
        
        # Add zoom actions
        self.zoom_in_action = QAction("Увеличить", self)
        self.zoom_in_action.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_TitleBarMaxButton')))
        self.zoom_in_action.triggered.connect(self.zoom_in)
        self.toolbar.addAction(self.zoom_in_action)
        
        self.zoom_out_action = QAction("Уменьшить", self)
        self.zoom_out_action.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_TitleBarMinButton')))
        self.zoom_out_action.triggered.connect(self.zoom_out)
        self.toolbar.addAction(self.zoom_out_action)
        
        self.zoom_reset_action = QAction("Сбросить масштаб", self)
        self.zoom_reset_action.triggered.connect(self.reset_zoom)
        self.toolbar.addAction(self.zoom_reset_action)
        
        # Add separator
        self.toolbar.addSeparator()
        
        # Add export graph action
        self.export_graph_action = QAction("Экспорт графика", self)
        self.export_graph_action.triggered.connect(self.export_graph)
        self.toolbar.addAction(self.export_graph_action)
        
        # Top controls
        control_layout = QHBoxLayout()
        
        # Host input
        host_layout = QVBoxLayout()
        host_layout.addWidget(QLabel("Целевой хост:"))
        self.host_input = QLineEdit("localhost")
        host_layout.addWidget(self.host_input)
        control_layout.addLayout(host_layout)
        
        # Port input
        port_layout = QVBoxLayout()
        port_layout.addWidget(QLabel("Порты (через запятую):"))
        self.port_input = QLineEdit("80, 443, 8080")
        port_layout.addWidget(self.port_input)
        control_layout.addLayout(port_layout)
        
        # Interval input
        interval_layout = QVBoxLayout()
        interval_layout.addWidget(QLabel("Интервал проверки (сек):"))
        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 60)
        self.interval_input.setValue(5)
        interval_layout.addWidget(self.interval_input)
        control_layout.addLayout(interval_layout)
        
        # Start/Stop button
        self.start_button = QPushButton("Начать мониторинг")
        self.start_button.clicked.connect(self.toggle_monitoring)
        control_layout.addWidget(self.start_button)
        
        # Add export buttons
        self.export_data_button = QPushButton("Экспорт данных")
        self.export_data_button.clicked.connect(self.export_data)
        control_layout.addWidget(self.export_data_button)
        
        self.export_response_button = QPushButton("Экспорт графика отклика")
        self.export_response_button.clicked.connect(lambda: self.export_graph('response'))
        control_layout.addWidget(self.export_response_button)
        
        self.export_availability_button = QPushButton("Экспорт графика доступности")
        self.export_availability_button.clicked.connect(lambda: self.export_graph('availability'))
        control_layout.addWidget(self.export_availability_button)
        
        layout.addLayout(control_layout)
        
        # Create tab widget for graphs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, stretch=2)
        
        # Response time tab
        response_tab = QWidget()
        response_layout = QVBoxLayout(response_tab)
        self.response_graph = PlotWidget()
        self.response_graph.setBackground('w')
        self.response_graph.setLabel('left', 'Время отклика (мс)')
        self.response_graph.setLabel('bottom', 'Время (сек)')
        self.response_graph.addLegend()
        self.response_graph.setMouseEnabled(x=True, y=True)
        self.response_graph.showGrid(x=True, y=True)
        response_layout.addWidget(self.response_graph)
        self.tabs.addTab(response_tab, "Время отклика")
        
        # Availability tab
        availability_tab = QWidget()
        availability_layout = QVBoxLayout(availability_tab)
        self.availability_graph = PlotWidget()
        self.availability_graph.setBackground('w')
        self.availability_graph.setLabel('left', 'Доступность')
        self.availability_graph.setLabel('bottom', 'Время (сек)')
        self.availability_graph.setYRange(0, 1.1, padding=0)
        self.availability_graph.addLegend()
        self.availability_graph.setMouseEnabled(x=True, y=True)
        self.availability_graph.showGrid(x=True, y=True)
        availability_layout.addWidget(self.availability_graph)
        self.tabs.addTab(availability_tab, "Доступность")

        # SSH monitoring tab
        ssh_tab = QWidget()
        ssh_layout = QVBoxLayout(ssh_tab)

        ssh_control_layout = QHBoxLayout()

        server_layout = QVBoxLayout()
        server_layout.addWidget(QLabel("Linux серверы (user@host:port, через запятую):"))
        self.ssh_servers_input = QLineEdit("root@127.0.0.1:22")
        server_layout.addWidget(self.ssh_servers_input)
        ssh_control_layout.addLayout(server_layout)

        password_layout = QVBoxLayout()
        password_layout.addWidget(QLabel("SSH пароль:"))
        self.ssh_password_input = QLineEdit()
        self.ssh_password_input.setEchoMode(QLineEdit.Password)
        password_layout.addWidget(self.ssh_password_input)
        ssh_control_layout.addLayout(password_layout)

        key_layout = QVBoxLayout()
        key_layout.addWidget(QLabel("SSH ключ (опционально):"))
        key_input_layout = QHBoxLayout()
        self.ssh_key_input = QLineEdit()
        self.ssh_key_input.setPlaceholderText("Путь до private key")
        key_input_layout.addWidget(self.ssh_key_input)
        self.ssh_key_button = QPushButton("...")
        self.ssh_key_button.clicked.connect(self.select_ssh_key)
        key_input_layout.addWidget(self.ssh_key_button)
        key_layout.addLayout(key_input_layout)
        ssh_control_layout.addLayout(key_layout)

        ssh_interval_layout = QVBoxLayout()
        ssh_interval_layout.addWidget(QLabel("Интервал SSH (сек):"))
        self.ssh_interval_input = QSpinBox()
        self.ssh_interval_input.setRange(5, 300)
        self.ssh_interval_input.setValue(15)
        ssh_interval_layout.addWidget(self.ssh_interval_input)
        ssh_control_layout.addLayout(ssh_interval_layout)

        self.ssh_connect_button = QPushButton("Подключиться")
        self.ssh_connect_button.clicked.connect(self.start_ssh_monitoring)
        ssh_control_layout.addWidget(self.ssh_connect_button)

        self.ssh_disconnect_button = QPushButton("Отключиться")
        self.ssh_disconnect_button.clicked.connect(self.stop_ssh_monitoring)
        self.ssh_disconnect_button.setEnabled(False)
        ssh_control_layout.addWidget(self.ssh_disconnect_button)

        self.ssh_refresh_button = QPushButton("Обновить")
        self.ssh_refresh_button.clicked.connect(self.check_ssh_servers)
        self.ssh_refresh_button.setEnabled(False)
        ssh_control_layout.addWidget(self.ssh_refresh_button)

        ssh_layout.addLayout(ssh_control_layout)

        self.ssh_status_label = QLabel("SSH мониторинг не запущен")
        ssh_layout.addWidget(self.ssh_status_label)

        self.ssh_table = QTableWidget(0, 8)
        self.ssh_table.setHorizontalHeaderLabels([
            "Сервер", "Подключение", "Состояние", "Uptime",
            "Load Avg", "RAM (%)", "Disk / (%)", "Последняя проверка"
        ])
        self.ssh_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ssh_table.setEditTriggers(QTableWidget.NoEditTriggers)
        ssh_layout.addWidget(self.ssh_table)

        self.tabs.addTab(ssh_tab, "SSH Linux")
        
        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, stretch=1)
        
        # Status bar
        self.statusBar().showMessage("Готово")
        
        # Timer for periodic checks
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_ports)
        self.ssh_timer = QTimer()
        self.ssh_timer.timeout.connect(self.check_ssh_servers)
        
    def toggle_monitoring(self):
        if not self.monitoring:
            # Start monitoring
            self.time_data = []
            self.port_status = {}
            self.start_time = time.time()
            
            # Initialize port data
            ports = [p.strip() for p in self.port_input.text().split(',') if p.strip().isdigit()]
            for port in ports:
                self.port_status[int(port)] = {'response_times': [], 'plot': None}
            
            if not self.port_status:
                QMessageBox.warning(self, "Ошибка", "Не указаны действительные порты")
                return
                
            self.monitoring = True
            self.start_button.setText("Остановить мониторинг")
            self.host_input.setEnabled(False)
            self.port_input.setEnabled(False)
            self.interval_input.setEnabled(False)
            self.export_data_button.setEnabled(False)
            self.export_response_button.setEnabled(False)
            self.export_availability_button.setEnabled(False)
            
            # Start timer
            self.timer.start(self.interval_input.value() * 1000)
            self.log_message("Начат мониторинг портов: " + ", ".join(str(p) for p in self.port_status.keys()))
            
        else:
            # Stop monitoring
            self.monitoring = False
            self.start_button.setText("Начать мониторинг")
            self.host_input.setEnabled(True)
            self.port_input.setEnabled(True)
            self.interval_input.setEnabled(True)
            self.export_data_button.setEnabled(True)
            self.export_response_button.setEnabled(True)
            self.export_availability_button.setEnabled(True)
            self.timer.stop()
            self.log_message("Мониторинг остановлен")
    
    def check_ports(self):
        current_time = time.time() - self.start_time
        self.time_data.append(current_time)
        
        # Initialize ports if not already done
        ports = [int(p.strip()) for p in self.port_input.text().split(',') if p.strip().isdigit()]
        for port in ports:
            # Ensure port status is properly initialized
            if port not in self.port_status:
                self.port_status[port] = {
                    'response_times': [],
                    'availability': [],
                    'plot': {}
                }
            # Double-check plot dictionary
            if 'plot' not in self.port_status[port] or not isinstance(self.port_status[port]['plot'], dict):
                self.port_status[port]['plot'] = {}
            
        for port, data in self.port_status.items():
            start_time = time.time()
            status = self.check_port(self.host_input.text(), port)
            response_time = (time.time() - start_time) * 1000  # in ms
            
            # Update response times
            data['response_times'].append(response_time)
            
            # Update availability (1 for available, 0 for not available)
            data.setdefault('availability', []).append(1 if status else 0)
            
            # Update response time graph
            self.update_graph(self.response_graph, port, data['response_times'], 
                            f"Порт {port} (мс)", 'response')
            
            # Update availability graph
            self.update_graph(self.availability_graph, port, data['availability'],
                            f"Порт {port}", 'availability')
            
            status_text = "открыт" if status else "закрыт"
            self.log_message(f"Порт {port}: {status_text} (Время отклика: {response_time:.2f}мс)")
    
    def update_graph(self, graph, port, values, name, graph_type):
        # Ensure port status has the plot dictionary
        if port not in self.port_status:
            self.port_status[port] = {'response_times': [], 'availability': [], 'plot': {}}
            
        # Ensure plot dictionary exists and is a dictionary
        if 'plot' not in self.port_status[port] or not isinstance(self.port_status[port]['plot'], dict):
            self.port_status[port]['plot'] = {}
            
        # Remove old plot if exists
        if graph_type in self.port_status[port]['plot'] and self.port_status[port]['plot'][graph_type] is not None:
            try:
                graph.removeItem(self.port_status[port]['plot'][graph_type])
            except Exception as e:
                print(f"Error removing plot item: {e}")
                # If item no longer exists in the graph, just continue
                pass
        
        # Create new plot
        pen = mkPen(color=(port * 50 % 255, port * 100 % 255, port * 150 % 255))
        plot = graph.plot(
            self.time_data[-len(values):],
            values,
            pen=pen,
            name=name
        )
        
        # Store reference to the plot
        if 'plot' not in self.port_status[port]:
            self.port_status[port]['plot'] = {}
        self.port_status[port]['plot'][graph_type] = plot
        
        # Set Y range for availability graph
        if graph_type == 'availability':
            graph.setYRange(0, 1.1, padding=0)
    
    def check_port(self, host, port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex((host, port))
                return result == 0
        except Exception as e:
            return False

    def select_ssh_key(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите SSH ключ", "", "Все файлы (*)")
        if file_path:
            self.ssh_key_input.setText(file_path)

    def parse_ssh_servers(self):
        servers = []
        raw_servers = [item.strip() for item in self.ssh_servers_input.text().split(',') if item.strip()]
        for item in raw_servers:
            try:
                if '@' not in item:
                    raise ValueError("Не указан пользователь")
                user, host_port = item.split('@', 1)
                host, port = (host_port.split(':', 1) + ['22'])[:2]
                servers.append({'name': item, 'user': user, 'host': host, 'port': int(port)})
            except Exception:
                self.log_message(f"Некорректный формат сервера: {item}. Ожидается user@host:port")
        return servers

    def start_ssh_monitoring(self):
        servers = self.parse_ssh_servers()
        if not servers:
            QMessageBox.warning(self, "Ошибка", "Не удалось распознать список SSH серверов")
            return

        self.stop_ssh_monitoring(log=False)
        self.ssh_table.setRowCount(len(servers))
        self.ssh_clients = {}

        key_filename = self.ssh_key_input.text().strip() or None
        password = self.ssh_password_input.text() or None

        for row, server in enumerate(servers):
            self.ssh_table.setItem(row, 0, QTableWidgetItem(server['name']))
            self.ssh_table.setItem(row, 1, QTableWidgetItem("Подключение..."))
            self.ssh_table.setItem(row, 2, QTableWidgetItem("Неизвестно"))

            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=server['host'],
                    port=server['port'],
                    username=server['user'],
                    password=password,
                    key_filename=key_filename,
                    timeout=5,
                    banner_timeout=5,
                    auth_timeout=5
                )
                self.ssh_clients[server['name']] = client
                self.ssh_table.setItem(row, 1, QTableWidgetItem("Подключено"))
                self.log_message(f"SSH подключение установлено: {server['name']}")
            except Exception as e:
                self.ssh_table.setItem(row, 1, QTableWidgetItem("Ошибка"))
                self.ssh_table.setItem(row, 2, QTableWidgetItem("Offline"))
                self.ssh_table.setItem(row, 7, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
                self.log_message(f"Ошибка SSH подключения к {server['name']}: {str(e)}")

        if not self.ssh_clients:
            QMessageBox.warning(self, "SSH", "Не удалось подключиться ни к одному серверу")
            self.ssh_status_label.setText("SSH мониторинг не запущен")
            return

        self.ssh_connect_button.setEnabled(False)
        self.ssh_disconnect_button.setEnabled(True)
        self.ssh_refresh_button.setEnabled(True)
        self.ssh_timer.start(self.ssh_interval_input.value() * 1000)
        self.ssh_status_label.setText(f"SSH мониторинг активен: {len(self.ssh_clients)} сервер(ов)")
        self.check_ssh_servers()

    def stop_ssh_monitoring(self, log=True):
        self.ssh_timer.stop()
        for client in self.ssh_clients.values():
            try:
                client.close()
            except Exception:
                pass
        self.ssh_clients = {}

        self.ssh_connect_button.setEnabled(True)
        self.ssh_disconnect_button.setEnabled(False)
        self.ssh_refresh_button.setEnabled(False)
        self.ssh_status_label.setText("SSH мониторинг не запущен")
        if log:
            self.log_message("SSH мониторинг остановлен")

    def read_ssh_resources(self, client):
        command = (
            "bash -lc \""
            "uptime -p 2>/dev/null || echo unknown;"
            "cat /proc/loadavg | awk '{print $1}' 2>/dev/null || echo n/a;"
            "free | awk '/Mem:/ {printf \\\"%.1f\\\", $3/$2*100}' 2>/dev/null || echo n/a;"
            "echo;"
            "df / | awk 'NR==2 {gsub(/%/,\\\"\\\",$5); print $5}' 2>/dev/null || echo n/a"
            "\""
        )
        stdin, stdout, stderr = client.exec_command(command, timeout=6)
        lines = stdout.read().decode(errors='ignore').strip().splitlines()
        if len(lines) < 4:
            raise RuntimeError(stderr.read().decode(errors='ignore').strip() or "Недостаточно данных")
        return {
            'uptime': lines[0],
            'load': lines[1],
            'ram': lines[2],
            'disk': lines[3]
        }

    def check_ssh_servers(self):
        if not self.ssh_clients:
            return

        for row in range(self.ssh_table.rowCount()):
            server_item = self.ssh_table.item(row, 0)
            if not server_item:
                continue

            server_name = server_item.text()
            client = self.ssh_clients.get(server_name)
            if client is None:
                continue

            try:
                data = self.read_ssh_resources(client)
                self.ssh_table.setItem(row, 1, QTableWidgetItem("Подключено"))
                self.ssh_table.setItem(row, 2, QTableWidgetItem("Online"))
                self.ssh_table.setItem(row, 3, QTableWidgetItem(data['uptime']))
                self.ssh_table.setItem(row, 4, QTableWidgetItem(data['load']))
                self.ssh_table.setItem(row, 5, QTableWidgetItem(data['ram']))
                self.ssh_table.setItem(row, 6, QTableWidgetItem(data['disk']))
                self.ssh_table.setItem(row, 7, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
            except Exception as e:
                self.ssh_table.setItem(row, 1, QTableWidgetItem("Ошибка"))
                self.ssh_table.setItem(row, 2, QTableWidgetItem("Offline"))
                self.ssh_table.setItem(row, 7, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
                self.log_message(f"Ошибка чтения ресурсов {server_name}: {str(e)}")
            
    
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {message}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        
    def export_graph(self, graph_type):
        """Экспортирует график в файл изображения.
        
        Args:
            graph_type: 'response' for response time graph, 'availability' for availability graph
        """
        if not self.time_data or not any(data['response_times'] for data in self.port_status.values()):
            QMessageBox.warning(self, "Нет данных", "Нет данных для экспорта графика")
            return
        
        graph = self.response_graph if graph_type == 'response' else self.availability_graph
        graph_type_name = "отклика" if graph_type == 'response' else 'доступности'
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Экспорт графика {graph_type_name}",
            f"port_monitor_{graph_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;PDF (*.pdf)"
        )

        if not file_path:
            return

        try:
            if file_path.lower().endswith('.pdf'):
                # Export as PDF
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(file_path)
                
                # Adjust page size to match the graph size
                rect = graph.sceneRect()
                printer.setPageSizeMM(QSizeF(rect.width() / 3.78, rect.height() / 3.78))
                
                # Render the graph to PDF
                painter = QPainter()
                if not painter.begin(printer):
                    raise Exception("Не удалось инициализировать принтер")
                    
                # Scale the painter to fit the graph on the page
                x_scale = printer.pageRect().width() / rect.width()
                y_scale = printer.pageRect().height() / rect.height()
                scale = min(x_scale, y_scale) * 0.9  # 90% of the page to add margins
                painter.scale(scale, scale)
                
                # Center the graph on the page
                x_offset = (printer.pageRect().width() / scale - rect.width()) / 2
                y_offset = (printer.pageRect().height() / scale - rect.height()) / 2
                painter.translate(x_offset, y_offset)
                
                # Render the graph
                graph.render(painter)
                painter.end()
                
            else:
                # Export as image (PNG, JPG, BMP)
                # Create a pixmap of the graph widget
                pixmap = QPixmap(graph.size())
                pixmap.fill(Qt.white)
                
                # Create a painter to render the graph onto the pixmap
                painter = QPainter(pixmap)
                graph.render(painter)
                painter.end()
                
                # Save the pixmap to file
                if not pixmap.save(file_path):
                    raise Exception("Не удалось сохранить изображение")
                
            QMessageBox.information(self, "Успех", 
                                  f"График {graph_type_name} успешно сохранен в файл:\n{file_path}")
            self.log_message(f"График {graph_type_name} экспортирован: {file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", 
                               f"Не удалось экспортировать график {graph_type_name}: {str(e)}")
            self.log_message(f"Ошибка при экспорте графика {graph_type_name}: {str(e)}")
    
    def zoom_in(self):
        """Увеличивает масштаб графика."""
        current_graph = self.response_graph if self.tabs.currentIndex() == 0 else self.availability_graph
        current_graph.getViewBox().scaleBy((0.8, 0.8))
        
    def zoom_out(self):
        """Уменьшает масштаб графика."""
        current_graph = self.response_graph if self.tabs.currentIndex() == 0 else self.availability_graph
        current_graph.getViewBox().scaleBy((1.25, 1.25))
        
    def reset_zoom(self):
        """Сбрасывает масштаб графика к исходному виду."""
        if not self.time_data:
            return
            
        current_graph = self.response_graph if self.tabs.currentIndex() == 0 else self.availability_graph
        
        if self.tabs.currentIndex() == 0:  # Response time graph
            x_range = max(1, max(self.time_data) - min(self.time_data))
            y_values = []
            for port_data in self.port_status.values():
                if port_data['response_times']:
                    y_values.extend(port_data['response_times'])
            y_range = max(1, max(y_values) if y_values else 1)
            
            current_graph.getViewBox().setRange(
                xRange=[min(self.time_data) - x_range * 0.1, max(self.time_data) + x_range * 0.1],
                yRange=[-y_range * 0.1, y_range * 1.1]
            )
        else:  # Availability graph
            current_graph.getViewBox().setRange(
                xRange=[min(self.time_data), max(self.time_data) + 1],
                yRange=[-0.1, 1.1]
            )
    
    def export_data(self):
        if not self.time_data or not any(data['response_times'] for data in self.port_status.values()):
            QMessageBox.warning(self, "Нет данных", "Нет данных для экспорта")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт данных",
            f"port_monitor_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV файлы (*.csv)"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                
                # Write header
                headers = ['Время (сек)']
                ports = list(self.port_status.keys())
                headers.extend([f"Порт {p} (мс)" for p in ports])
                writer.writerow(headers)
                
                # Write data
                max_length = max(len(self.time_data), max(len(data['response_times']) for data in self.port_status.values()))
                
                for i in range(max_length):
                    row = []
                    row.append(f"{self.time_data[i]:.2f}" if i < len(self.time_data) else "")
                    
                    for port in ports:
                        if i < len(self.port_status[port]['response_times']):
                            row.append(f"{self.port_status[port]['response_times'][i]:.2f}")
                        else:
                            row.append("")
                    
                    writer.writerow(row)
                    
            self.log_message(f"Данные экспортированы в файл: {file_path}")
            QMessageBox.information(self, "Экспорт завершен", f"Данные успешно сохранены в файл:\n{file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось экспортировать данные: {str(e)}")
            self.log_message(f"Ошибка при экспорте: {str(e)}")

def main():
    app = QApplication(sys.argv)
    window = PortMonitorApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    # Set application style
    QApplication.setStyle('Fusion')
    
    # Set application font that supports Russian
    app = QApplication(sys.argv)
    font = app.font()
    font.setPointSize(9)
    app.setFont(font)
    
    # Set application name and version
    app.setApplicationName("Мониторинг портов")
    app.setApplicationVersion("1.0")
    
    # Set window icon (optional)
    # app.setWindowIcon(QIcon('icon.png'))
    
    window = PortMonitorApp()
    window.show()
    sys.exit(app.exec_())
