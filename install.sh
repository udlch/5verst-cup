#!/bin/bash

# Скрипт для автоматической установки и настройки проекта verst_analyzer
# Убедитесь, что вы запускаете его из директории, в которой лежит папка проекта.

# --- Переменные --- #
# Определяем абсолютный путь к директории, где находится сам скрипт
PROJECT_DIR=$(cd "$(dirname "$0")" && pwd)
# Определяем имя пользователя, от которого запускается скрипт
RUN_USER=$(whoami)

# --- Функции --- #

echo_green() {
    echo -e "\033[0;32m$1\033[0m"
}

echo_red() {
    echo -e "\033[0;31m$1\033[0m"
}

# --- Начало --- #

echo_green "Начинаем установку анализатора 5 вёрст..."

# Остановка существующего сервиса, чтобы освободить файлы
echo "Останавливаем возможный запущенный сервис..."
sudo systemctl stop verst_analyzer.service

# Шаг 1: Создание виртуального окружения
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo_green "\nШаг 1: Создание виртуального окружения..."
    python3 -m venv --copies "$PROJECT_DIR/venv"
    if [ $? -ne 0 ]; then
        echo_red "Не удалось создать виртуальное окружение. Убедитесь, что у вас установлен пакет python3-venv."
        exit 1
    fi
else
    echo_green "\nШаг 1: Виртуальное окружение уже существует, пропускаем."
fi

# Шаг 2: Установка зависимостей
echo_green "\nШаг 2: Установка зависимостей..."
"$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo_red "Не удалось установить зависимости. Проверьте файл requirements.txt и доступ к интернету."
    exit 1
fi



# Шаг 4: Настройка systemd
echo_green "\nШаг 4: Настройка системного сервиса (systemd)..."

# Используем Heredoc для надежного формирования файла
SERVICE_FILE_CONTENT=$(cat <<EOF
[Unit]
Description=Gunicorn instance to serve verst_analyzer
After=network.target

[Service]
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8001 app:app

[Install]
WantedBy=multi-user.target
EOF
)

echo "$SERVICE_FILE_CONTENT" | sudo tee /etc/systemd/system/verst_analyzer.service > /dev/null

echo "Перезагрузка и запуск сервиса..."
sudo systemctl daemon-reload
sudo systemctl enable verst_analyzer
sudo systemctl start verst_analyzer

# Даем сервису время на запуск
sleep 2

sudo systemctl status verst_analyzer --no-pager
if [ $? -ne 0 ]; then
    echo_red "Сервис systemd не запустился. Проверьте лог выше."
    exit 1
fi
echo_green "Сервис успешно запущен."



echo_green "\nУстановка завершена!"
echo "- Ваше приложение работает в фоновом режиме."
echo "- Данные будут автоматически обновляться каждый час."
echo "- Вам осталось настроить веб-сервер (Nginx) для доступа к приложению, если это необходимо."
